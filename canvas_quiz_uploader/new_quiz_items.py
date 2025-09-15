# new_quiz_items.py
import uuid, json, requests, time, re
from typing import Dict, Any, List, Tuple
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice","multiple_answer","true_false","fill_in_blank",
    "short_answer","essay","numeric","matching","ordering","categorization",
    "file_upload","hot_spot","formula"
]

def _label(s: str) -> Dict[str, str]:
    s = (s or "").strip()
    return {"text": s, "item_body": s}

def _extract_paragraph_texts(html: str) -> List[str]:
    """Return inner text of <p>...</p> blocks, stripped of tags/whitespace."""
    if not html:
        return []
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    out = []
    for p in paras:
        # strip any tag remnants
        txt = re.sub(r"(?s)<[^>]+>", "", p).strip()
        if txt:
            out.append(txt)
    return out

def _split_prompt_and_inline_options(prompt_html: str) -> Tuple[str, List[str]]:
    """
    If the author pasted options into the body (your example shows that),
    treat the first paragraph as the question and subsequent <p>...</p> as option texts.
    Also trim trailing feedback fragments like '3  Off by one' -> '3'.
    """
    paras = _extract_paragraph_texts(prompt_html)
    if not paras:
        return prompt_html or "", []

    q_text = paras[0]

    opts = []
    for raw in paras[1:]:
        # remove leading '*', used sometimes to mark the correct option in raw text
        s = raw.lstrip("*").strip()
        # if feedback got appended with two or more spaces, keep the left token
        if "  " in s:
            s = s.split("  ", 1)[0].strip()
        # drop empty remnants
        if s:
            opts.append(s)
    # rebuild a clean prompt containing only the first paragraph
    clean_prompt = f"<p>{q_text}</p>"
    return clean_prompt, opts

class NewQuizItemBuilder:
    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t = (q.get("type") or "").lower().strip()

        item = {
            "position": None,
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or (q.get("name") or ""),
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": "none",
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,
                "scoring_algorithm": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
                "answer_feedback": None,
            }
        }

        # ------------------ Multiple Choice ------------------
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}

            # primary: use parser-provided answers
            for ans in q.get("answers", []) or []:
                cid = _uuid()
                label = (ans.get("text") or "").strip()
                if not label:
                    continue
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"):
                    correct_id = cid
                if ans.get("feedback_html"):
                    per_ans_fb[cid] = ans["feedback_html"]

            # fallback: if we have <2 choices, try to recover from inline <p>…</p> options
            if len(choices) < 2:
                clean_prompt, inline_opts = _split_prompt_and_inline_options(item["entry"]["item_body"])
                if inline_opts:
                    # keep existing correct if present, and add recovered options not already present
                    existing_texts = {c["text"] for c in choices}
                    for opt in inline_opts:
                        if opt not in existing_texts:
                            choices.append({"id": _uuid(), **_label(opt)})
                    # set clean prompt
                    item["entry"]["item_body"] = clean_prompt

            # last resort: ensure >=2 choices to avoid UI spinner
            if len(choices) < 2:
                # create a safe distractor that won't accidentally be correct
                distractor = "None of the above"
                if not any(c["text"] == distractor for c in choices):
                    choices.append({"id": _uuid(), **_label(distractor)})

            # if still no correct_id, pick the first one from parser if it flagged it, else None
            if correct_id is None and choices:
                # try to infer from an asterisked inline option if parser missed it
                inline_marked = [s for s in _extract_paragraph_texts(q.get("prompt_html") or "") if s.lstrip().startswith("*")]
                if inline_marked:
                    marked = inline_marked[0].lstrip("*").strip()
                    for c in choices:
                        if c["text"] == marked:
                            correct_id = c["id"]; break
                # if still None, default to the first (better than an invalid item)
                if correct_id is None:
                    correct_id = choices[0]["id"]

            item["entry"]["interaction_type_slug"] = "choice"
            item["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}},
                "vary_points_by_answer": False
            }
            item["entry"]["scoring_data"] = {"value": correct_id}
            item["entry"]["scoring_algorithm"] = "Equivalence"
            item["entry"]["answer_feedback"] = per_ans_fb or None

        # ------------------ Multiple Answer ------------------
        elif t == "multiple_answer":
            choices, correct_ids = [], []

            for ans in q.get("answers", []) or []:
                cid = _uuid()
                label = (ans.get("text") or "").strip()
                if not label:
                    continue
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"):
                    correct_ids.append(cid)

            # fallback from inline paragraphs if needed
            if len(choices) < 2:
                clean_prompt, inline_opts = _split_prompt_and_inline_options(item["entry"]["item_body"])
                if inline_opts:
                    existing_texts = {c["text"] for c in choices}
                    for opt in inline_opts:
                        if opt not in existing_texts:
                            choices.append({"id": _uuid(), **_label(opt)})
                    item["entry"]["item_body"] = clean_prompt

            if len(choices) < 2:
                choices.append({"id": _uuid(), **_label("None of the above")})

            item["entry"]["interaction_type_slug"] = "multi-answer"
            item["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}}
            }
            item["entry"]["scoring_data"] = {"value": correct_ids}
            item["entry"]["scoring_algorithm"] = "PartialScore"

        # ------------------ True / False ------------------
        elif t == "true_false":
            item["entry"]["interaction_type_slug"] = "true-false"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            item["entry"]["scoring_algorithm"] = "Equivalence"

        # ------------------ Fill-in-Blank (rich) ------------------
        elif t == "fill_in_blank":
            blanks = q.get("blanks") or []
            twb = q.get("text_with_blanks") or q.get("prompt_html") or q.get("prompt") or ""
            if not blanks:
                twb = twb + " {{b1}}"
                answers = [a.get("text") for a in (q.get("answers") or []) if a.get("text")]
                blanks = [{"id": "b1", "correct": answers}]

            blanks_map = {}
            for b in blanks:
                alts = [{"id": _uuid(), **_label(v)} for v in (b.get("correct") or [])]
                blanks_map[b["id"]] = alts

            item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            item["entry"]["interaction_data"] = {"text_with_blanks": twb, "blanks": blanks_map}
            item["entry"]["scoring_data"] = {
                "value": {"blank_to_correct_answer_ids": {bid: [a["id"] for a in alts] for bid, alts in blanks_map.items()}}
            }
            item["entry"]["scoring_algorithm"] = "MultipleMethods"

        # ------------------ Short Answer -> single blank ------------------
        elif t == "short_answer":
            answers = [a.get("text", "") for a in q.get("answers", []) if a.get("text")]
            twb = (q.get("prompt_html") or q.get("prompt") or "") + " {{b1}}"
            alts = [{"id": _uuid(), **_label(s)} for s in answers]
            item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            item["entry"]["interaction_data"] = {"text_with_blanks": twb, "blanks": {"b1": alts}}
            item["entry"]["scoring_data"] = {"value": {"blank_to_correct_answer_ids": {"b1": [a["id"] for a in alts]}}}
            item["entry"]["scoring_algorithm"] = "MultipleMethods"

        # ------------------ Essay ------------------
        elif t == "essay":
            item["entry"]["interaction_type_slug"] = "essay"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        # ------------------ Numeric ------------------
        elif t == "numeric":
            spec = q.get("numeric") or {}
            exact = spec.get("exact")
            tol = float(spec.get("tolerance", 0) or 0)
            item["entry"]["interaction_type_slug"] = "numeric"
            item["entry"]["interaction_data"] = {}
            if exact is not None and tol > 0:
                item["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "marginOfError",
                        "value": str(exact),
                        "margin": str(tol),
                        "margin_type": "absolute"
                    }]
                }
            else:
                item["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "exactResponse",
                        "value": str(exact if exact is not None else "")
                    }]
                }
            item["entry"]["scoring_algorithm"] = "Numeric"

        # ------------------ Matching ------------------
        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in q.get("pairs", []) or []:
                right = pair["match"]
                rcid = right_ids.get(right)
                if not rcid:
                    rcid = _uuid()
                    right_ids[right] = rcid
                    choices.append({"id": rcid, **_label(right)})
                prompts.append({"id": _uuid(), **_label(pair["prompt"]), "answer_choice_id": rcid})

            item["entry"]["interaction_type_slug"] = "matching"
            item["entry"]["interaction_data"] = {"choices": choices, "prompts": prompts}
            item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
            item["entry"]["scoring_data"] = {"value": {p["id"]: p["answer_choice_id"] for p in prompts}}
            item["entry"]["scoring_algorithm"] = "DeepEquals"

        # ------------------ Ordering ------------------
        elif t == "ordering":
            items = [{"id": _uuid(), **_label(x)} for x in q.get("order", []) or []]
            item["entry"]["interaction_type_slug"] = "ordering"
            item["entry"]["interaction_data"] = {"choices": items}
            item["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
            item["entry"]["scoring_algorithm"] = "DeepEquals"

        # ------------------ Categorization ------------------
        elif t == "categorization":
            src = q.get("categories", []) or []
            categories, by_name = [], {}
            for cat in src:
                cid = _uuid()
                by_name[cat["name"]] = cid
                categories.append({"id": cid, **_label(cat["name"])})
            choices = []
            for cat in src:
                cid = by_name[cat["name"]]
                for label in cat.get("items", []) or []:
                    choice_id = _uuid()
                    choices.append({"id": choice_id, **_label(label), "category_id": cid})

            item["entry"]["interaction_type_slug"] = "categorization"
            item["entry"]["interaction_data"] = {"categories": categories, "choices": choices}
            item["entry"]["scoring_data"] = {"value": {c["id"]: c["category_id"] for c in choices}}
            item["entry"]["scoring_algorithm"] = "Categorization"
            item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}

        # ------------------ File Upload ------------------
        elif t == "file_upload":
            item["entry"]["interaction_type_slug"] = "file-upload"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        # ------------------ Hot Spot ------------------
        elif t == "hot_spot":
            item["entry"]["interaction_type_slug"] = "hot-spot"
            item["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            item["entry"]["scoring_data"] = {"value": [hs.get("id") for hs in q.get("hotspots", [])]}
            item["entry"]["scoring_algorithm"] = "HotSpot"

        # ------------------ Formula (shell) ------------------
        elif t == "formula":
            item["entry"]["interaction_type_slug"] = "formula"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": []}
            item["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": item}

# --------------- Posting (form first, then JSON fallback) ---------------
def _post_form(url: str, token: str, payload: dict):
    return requests.post(url, headers=H(token), data={"item": json.dumps(payload["item"])}, timeout=60)

def _post_json(url: str, token: str, payload: dict):
    return requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json={"item": payload["item"]}, timeout=60)

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    delays = [1, 2, 4, 6]
    for i, d in enumerate([0] + delays):
        if d: time.sleep(d)
        r = _post_form(url, token, item_payload)
        if r.status_code in (200, 201): return r
        if 500 <= r.status_code < 600:  # retry on server errors
            continue
        r2 = _post_json(url, token, item_payload)
        if r2.status_code in (200, 201): return r2
        if 500 <= r2.status_code < 600:
            continue
        return r2  # 4xx — stop immediately
    return r
