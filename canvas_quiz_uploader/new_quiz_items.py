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
        txt = re.sub(r"(?s)<[^>]+>", "", p).strip()
        if txt:
            out.append(txt)
    return out

def _split_prompt_and_inline_options(prompt_html: str) -> Tuple[str, List[str]]:
    """
    First <p> = question. Remaining <p> blocks are potential options.
    Trim inline feedback like '3  Off by one' -> '3'.
    """
    paras = _extract_paragraph_texts(prompt_html)
    if not paras:
        return prompt_html or "", []

    q_text = paras[0]
    opts = []
    for raw in paras[1:]:
        s = raw.lstrip("*").strip()
        if "  " in s:  # two+ spaces separates option from feedback in your examples
            s = s.split("  ", 1)[0].strip()
        if s:
            opts.append(s)

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

        # ---------- Multiple Choice ----------
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in (q.get("answers") or []):
                label = (ans.get("text") or "").strip()
                if not label:
                    continue
                cid = _uuid()
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"):
                    correct_id = cid
                if ans.get("feedback_html"):
                    per_ans_fb[cid] = ans["feedback_html"]

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

        # ---------- Multiple Answer ----------
        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in (q.get("answers") or []):
                label = (ans.get("text") or "").strip()
                if not label:
                    continue
                cid = _uuid()
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"):
                    correct_ids.append(cid)

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

        # ---------- True / False ----------
        elif t == "true_false":
            item["entry"]["interaction_type_slug"] = "true-false"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            item["entry"]["scoring_algorithm"] = "Equivalence"

        # ---------- Fill-in-Blank (rich) ----------
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

        # ---------- Short Answer ----------
        elif t == "short_answer":
            answers = [a.get("text", "") for a in (q.get("answers") or []) if a.get("text")]
            twb = (q.get("prompt_html") or q.get("prompt") or "") + " {{b1}}"
            alts = [{"id": _uuid(), **_label(s)} for s in answers]
            item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            item["entry"]["interaction_data"] = {"text_with_blanks": twb, "blanks": {"b1": alts}}
            item["entry"]["scoring_data"] = {"value": {"blank_to_correct_answer_ids": {"b1": [a["id"] for a in alts]}}}
            item["entry"]["scoring_algorithm"] = "MultipleMethods"

        # ---------- Essay ----------
        elif t == "essay":
            item["entry"]["interaction_type_slug"] = "essay"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        # ---------- Numeric ----------
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

        # ---------- Matching ----------
        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in (q.get("pairs") or []):
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

        # ---------- Ordering ----------
        elif t == "ordering":
            items = [{"id": _uuid(), **_label(x)} for x in (q.get("order") or [])]
            item["entry"]["interaction_type_slug"] = "ordering"
            item["entry"]["interaction_data"] = {"choices": items}
            item["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
            item["entry"]["scoring_algorithm"] = "DeepEquals"

        # ---------- Categorization ----------
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
                for label in (cat.get("items") or []):
                    choice_id = _uuid()
                    choices.append({"id": choice_id, **_label(label), "category_id": cid})

            item["entry"]["interaction_type_slug"] = "categorization"
            item["entry"]["interaction_data"] = {"categories": categories, "choices": choices}
            item["entry"]["scoring_data"] = {"value": {c["id"]: c["category_id"] for c in choices}}
            item["entry"]["scoring_algorithm"] = "Categorization"
            item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}

        # ---------- File Upload ----------
        elif t == "file_upload":
            item["entry"]["interaction_type_slug"] = "file-upload"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        # ---------- Hot Spot ----------
        elif t == "hot_spot":
            item["entry"]["interaction_type_slug"] = "hot-spot"
            item["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            item["entry"]["scoring_data"] = {"value": [hs.get("id") for hs in q.get("hotspots", [])]}
            item["entry"]["scoring_algorithm"] = "HotSpot"

        # ---------- Formula ----------
        elif t == "formula":
            item["entry"]["interaction_type_slug"] = "formula"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": []}
            item["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": item}

# ------------------ pre-flight repair for MC / MA ------------------

def _repair_mc_like(item: Dict[str, Any]) -> None:
    entry = item.get("entry") or {}
    slug = (entry.get("interaction_type_slug") or "").strip()
    if slug not in ("choice", "multi-answer"):
        return

    ia = entry.get("interaction_data") or {}
    choices = ia.get("choices") or []
    # If fewer than 2 choices, mine more from the prompt paragraphs
    if len(choices) < 2:
        clean_prompt, inline_opts = _split_prompt_and_inline_options(entry.get("item_body") or "")
        existing = { (c.get("text") or "").strip() for c in choices if c.get("text") }
        for opt in inline_opts:
            if opt and opt not in existing:
                choices.append({"id": _uuid(), **_label(opt)})
        if len(choices) < 2:
            choices.append({"id": _uuid(), **_label("None of the above")})  # <-- fixed line
        entry["item_body"] = clean_prompt
        ia["choices"] = choices
        entry["interaction_data"] = ia

    # Make sure MC has a valid single 'value'
    if slug == "choice":
        ids = [c["id"] for c in choices]
        val = ((entry.get("scoring_data") or {}).get("value"))
        if val not in ids and ids:
            entry["scoring_data"] = {"value": ids[0]}
    else:
        # For MA — ensure 'value' is a list subset of the current choice IDs
        ids = {c["id"] for c in choices}
        val = ((entry.get("scoring_data") or {}).get("value")) or []
        val = [v for v in val if v in ids]
        entry["scoring_data"] = {"value": val}

# ---------- Posting (form first, then JSON fallback) ----------

def _post_form(url: str, token: str, payload: dict):
    return requests.post(url, headers=H(token), data={"item": json.dumps(payload["item"])}, timeout=60)

def _post_json(url: str, token: str, payload: dict):
    return requests.post(
        url, headers={**H(token), "Content-Type": "application/json"},
        json={"item": payload["item"]}, timeout=60
    )

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)

    # PRE-FLIGHT REPAIR (stops Build spinner when parser missed options)
    try:
        _repair_mc_like(item_payload["item"])
    except Exception:
        pass

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    delays = [1, 2, 4, 6]
    for i, d in enumerate([0] + delays):
        if d: time.sleep(d)
        r = _post_form(url, token, item_payload)
        if r.status_code in (200, 201): return r
        if 500 <= r.status_code < 600:
            continue
        r2 = _post_json(url, token, item_payload)
        if r2.status_code in (200, 201): return r2
        if 500 <= r2.status_code < 600:
            continue
        return r2
    return r
