# new_quiz_items.py
import uuid, time, json, requests
from typing import Dict, Any, List
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

# Start with the 4 you asked to prioritize; the rest are supported too.
SUPPORTED_TYPES = [
    "multiple_choice", "multiple_answer", "true_false", "fill_in_blank",
    "short_answer", "essay", "numeric", "matching", "ordering",
    "categorization", "file_upload", "hot_spot", "formula"
]

def _triplet(label: str) -> Dict[str, str]:
    """Return label in all shapes the UI/API sometimes read."""
    s = label or ""
    return {"text": s, "item_body": s, "itemBody": s}

class NewQuizItemBuilder:
    """
    Builds Canvas New Quizzes 'item' payloads from normalized question dicts.
    - Always returns {"item": {...}} so the Items API accepts it.
    - Always sets entry.scoring_data with a top-level "value".
    """

    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t = (q.get("type") or "").lower().strip()

        base_item = {
            "position": None,                           # set by caller (we also set in post fn)
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or (q.get("name") or ""),
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": "none",
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,                  # will become {"value": ...}
                "scoring_algorithm": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
                "answer_feedback": None,               # per-answer feedback for MC, etc.
            }
        }

        # --------------------------
        # Multiple Choice
        # q: { type, shuffle?, answers: [{text, is_correct, feedback_html?}] }
        # --------------------------
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in q.get("answers", []):
                cid = _uuid()
                choices.append({"id": cid, **_triplet(ans.get("text", ""))})
                if ans.get("is_correct"):
                    correct_id = cid
                if ans.get("feedback_html"):
                    per_ans_fb[cid] = ans["feedback_html"]

            base_item["entry"]["interaction_type_slug"] = "choice"
            base_item["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base_item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}},
                "vary_points_by_answer": False
            }
            base_item["entry"]["scoring_data"] = {"value": correct_id}
            base_item["entry"]["scoring_algorithm"] = "Equivalence"
            base_item["entry"]["answer_feedback"] = per_ans_fb or None

        # --------------------------
        # Multiple Answers
        # q: { answers: [{text, is_correct}], shuffle? }
        # --------------------------
        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in q.get("answers", []):
                cid = _uuid()
                choices.append({"id": cid, **_triplet(ans.get("text", ""))})
                if ans.get("is_correct"):
                    correct_ids.append(cid)

            base_item["entry"]["interaction_type_slug"] = "multi-answer"
            base_item["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base_item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}}
            }
            base_item["entry"]["scoring_data"] = {"value": correct_ids}  # list of correct ids
            base_item["entry"]["scoring_algorithm"] = "PartialScore"

        # --------------------------
        # True / False
        # q: { correct: True|False }
        # --------------------------
        elif t == "true_false":
            base_item["entry"]["interaction_type_slug"] = "true-false"
            base_item["entry"]["interaction_data"] = {}
            base_item["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            base_item["entry"]["scoring_algorithm"] = "Equivalence"

        # --------------------------
        # Fill in the Blank (rich)
        # Accepts either:
        #   q["text_with_blanks"] + q["blanks"] (list of {"id": "b1", "correct":[...]}),
        # or build a single blank after the prompt if parser only provided answers.
        # --------------------------
        elif t == "fill_in_blank":
            blanks: List[Dict[str, Any]] = q.get("blanks") or []
            text_with_blanks = q.get("text_with_blanks") or q.get("prompt_html") or ""
            # If no {{bX}} markers provided, make a single blank at the end.
            if not blanks:
                text_with_blanks = (q.get("prompt_html") or q.get("prompt") or "") + " {{b1}}"
                answers = [a.get("text") for a in (q.get("answers") or []) if a.get("text")]
                blanks = [{"id": "b1", "correct": answers}]

            # Build interaction_data.blanks as { "b1": [{"id":.., label..}, ...], ... }
            blanks_map = {}
            for b in blanks:
                alts = [{"id": _uuid(), **_triplet(alt)} for alt in (b.get("correct") or [])]
                blanks_map[b["id"]] = alts

            base_item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base_item["entry"]["interaction_data"] = {
                "text_with_blanks": text_with_blanks,
                "blanks": blanks_map
            }
            base_item["entry"]["scoring_data"] = {
                "value": {
                    "blank_to_correct_answer_ids": {
                        bid: [a["id"] for a in alts] for bid, alts in blanks_map.items()
                    }
                }
            }
            base_item["entry"]["scoring_algorithm"] = "MultipleMethods"

        # --------------------------
        # Short Answer (map to single-blank rich-fill-blank)
        # --------------------------
        elif t == "short_answer":
            answers = [a.get("text", "") for a in q.get("answers", []) if a.get("text")]
            text_with_blanks = (q.get("prompt_html") or q.get("prompt") or "") + " {{b1}}"
            alts = [{"id": _uuid(), **_triplet(s)} for s in answers]
            base_item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base_item["entry"]["interaction_data"] = {"text_with_blanks": text_with_blanks, "blanks": {"b1": alts}}
            base_item["entry"]["scoring_data"] = {
                "value": {"blank_to_correct_answer_ids": {"b1": [a["id"] for a in alts]}}
            }
            base_item["entry"]["scoring_algorithm"] = "MultipleMethods"

        # --------------------------
        # Essay (manually graded)
        # --------------------------
        elif t == "essay":
            base_item["entry"]["interaction_type_slug"] = "essay"
            base_item["entry"]["interaction_data"] = {}
            base_item["entry"]["scoring_data"] = {"value": None}
            base_item["entry"]["scoring_algorithm"] = "None"

        # --------------------------
        # Numeric (exact or margin of error)
        # q.numeric: { exact: <num|string>, tolerance?: <num> }
        # --------------------------
        elif t == "numeric":
            spec = q.get("numeric") or {}
            exact = spec.get("exact")
            tol = float(spec.get("tolerance", 0) or 0)
            base_item["entry"]["interaction_type_slug"] = "numeric"
            base_item["entry"]["interaction_data"] = {}
            if exact is not None and tol > 0:
                base_item["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "marginOfError",
                        "value": str(exact),
                        "margin": str(tol),
                        "margin_type": "absolute"
                    }]
                }
            else:
                base_item["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "exactResponse",
                        "value": str(exact if exact is not None else "")
                    }]
                }
            base_item["entry"]["scoring_algorithm"] = "Numeric"

        # --------------------------
        # Matching
        # q.pairs: [{prompt: "H2O", match: "Water"}, ...]
        # --------------------------
        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in q.get("pairs", []):
                right = pair["match"]
                rcid = right_ids.get(right)
                if not rcid:
                    rcid = _uuid()
                    right_ids[right] = rcid
                    choices.append({"id": rcid, **_triplet(right)})
                prompts.append({"id": _uuid(), **_triplet(pair["prompt"]), "answer_choice_id": rcid})

            base_item["entry"]["interaction_type_slug"] = "matching"
            base_item["entry"]["interaction_data"] = {"choices": choices, "prompts": prompts}
            base_item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
            base_item["entry"]["scoring_data"] = {"value": {p["id"]: p["answer_choice_id"] for p in prompts}}
            base_item["entry"]["scoring_algorithm"] = "DeepEquals"

        # --------------------------
        # Ordering
        # q.order: ["First", "Second", ...]
        # --------------------------
        elif t == "ordering":
            items = [{"id": _uuid(), **_triplet(x)} for x in q.get("order", [])]
            base_item["entry"]["interaction_type_slug"] = "ordering"
            base_item["entry"]["interaction_data"] = {"choices": items}
            base_item["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
            base_item["entry"]["scoring_algorithm"] = "DeepEquals"

        # --------------------------
        # Categorization
        # q.categories: [{name: "Mammals", items:["Dog","Cat"]}, ...]
        # --------------------------
        elif t == "categorization":
            categories_src = q.get("categories", []) or []
            categories = []
            cat_id_by_name = {}
            for cat in categories_src:
                cid = _uuid()
                cat_id_by_name[cat["name"]] = cid
                categories.append({"id": cid, **_triplet(cat["name"])})
            choices = []
            for cat in categories_src:
                cid = cat_id_by_name[cat["name"]]
                for label in cat.get("items", []) or []:
                    choice_id = _uuid()
                    choices.append({"id": choice_id, **_triplet(label), "category_id": cid})

            base_item["entry"]["interaction_type_slug"] = "categorization"
            base_item["entry"]["interaction_data"] = {"categories": categories, "choices": choices}
            base_item["entry"]["scoring_data"] = {"value": {c["id"]: c["category_id"] for c in choices}}
            base_item["entry"]["scoring_algorithm"] = "Categorization"
            base_item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}

        # --------------------------
        # File Upload (manual grade)
        # --------------------------
        elif t == "file_upload":
            base_item["entry"]["interaction_type_slug"] = "file-upload"
            base_item["entry"]["interaction_data"] = {}
            base_item["entry"]["scoring_data"] = {"value": None}
            base_item["entry"]["scoring_algorithm"] = "None"

        # --------------------------
        # Hot Spot (minimal shell)
        # --------------------------
        elif t == "hot_spot":
            base_item["entry"]["interaction_type_slug"] = "hot-spot"
            base_item["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            base_item["entry"]["scoring_data"] = {"value": [hs.get("id") for hs in q.get("hotspots", [])]}
            base_item["entry"]["scoring_algorithm"] = "HotSpot"

        # --------------------------
        # Formula (treated like numeric shell)
        # --------------------------
        elif t == "formula":
            base_item["entry"]["interaction_type_slug"] = "formula"
            base_item["entry"]["interaction_data"] = {}
            base_item["entry"]["scoring_data"] = {"value": []}
            base_item["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": base_item}

# --------------------------
# Poster with strong form-first behavior
# --------------------------

def _post_form(url: str, token: str, payload: dict):
    # This is the most reliable path Canvas expects: form field 'item' containing JSON string.
    return requests.post(
        url,
        headers={**H(token), "Content-Type": "application/x-www-form-urlencoded"},
        data={"item": json.dumps(payload["item"])},
        timeout=60,
    )

def _post_json(url: str, token: str, payload: dict):
    # Some tenants accept JSON; when they do, it must be {"item": {...}}.
    return requests.post(
        url,
        headers={**H(token), "Content-Type": "application/json"},
        json={"item": payload["item"]},
        timeout=60,
    )

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    """
    Posts one item. We prefer FORM first (to avoid "Expected `item` object"),
    then fallback to JSON. Retries on 5xx.
    """
    if position is not None:
        item_payload["item"]["position"] = int(position)

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    delays = [1, 2, 4, 6]
    attempts = len(delays) + 1

    for i in range(attempts):
        r = _post_form(url, token, item_payload)
        if r.status_code in (200, 201):
            return r
        if 500 <= r.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue

        r2 = _post_json(url, token, item_payload)
        if r2.status_code in (200, 201):
            return r2
        if 500 <= r2.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue

        # Non-5xx error (e.g., 400 "Expected `item` object") — return immediately with that body.
        return r2

    return r  # last response
