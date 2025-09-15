# new_quiz_items.py
import uuid, json, requests, time
from typing import Dict, Any, List
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

# Start with the 4 you asked to prioritize; you can add the others back after this is solid.
SUPPORTED_TYPES = ["multiple_choice", "multiple_answer", "true_false", "fill_in_blank"]

def _label(s: str) -> Dict[str, str]:
    """Labels in all shapes the UI/API sometimes read."""
    s = s or ""
    return {"text": s, "item_body": s}   # keep it minimal; 'itemBody' not required everywhere

class NewQuizItemBuilder:
    """
    Build Canvas New Quizzes Items payloads from your normalized question dicts.
    ALWAYS returns {"item": {...}} so the Items API accepts it.
    """

    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t = (q.get("type") or "").lower().strip()

        # base Item
        item = {
            "position": None,                                # set by caller
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or (q.get("name") or ""),
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": "none",
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,                        # will become {"value": ...}
                "scoring_algorithm": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
                "answer_feedback": None,
            }
        }

        # ----------------------------
        # MULTIPLE CHOICE
        # ----------------------------
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in q.get("answers", []):
                cid = _uuid()
                choices.append({"id": cid, **_label(ans.get("text", ""))})
                if ans.get("is_correct"): correct_id = cid
                if ans.get("feedback_html"): per_ans_fb[cid] = ans["feedback_html"]

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

        # ----------------------------
        # MULTIPLE ANSWERS
        # ----------------------------
        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in q.get("answers", []):
                cid = _uuid()
                choices.append({"id": cid, **_label(ans.get("text", ""))})
                if ans.get("is_correct"): correct_ids.append(cid)

            item["entry"]["interaction_type_slug"] = "multi-answer"
            item["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}}
            }
            item["entry"]["scoring_data"] = {"value": correct_ids}  # list of correct IDs
            item["entry"]["scoring_algorithm"] = "PartialScore"

        # ----------------------------
        # TRUE / FALSE
        # ----------------------------
        elif t == "true_false":
            item["entry"]["interaction_type_slug"] = "true-false"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            item["entry"]["scoring_algorithm"] = "Equivalence"

        # ----------------------------
        # FILL IN THE BLANK (Rich)
        # Accepts either:
        #    q["text_with_blanks"] + q["blanks"] (list of {"id":"b1","correct":[..]})
        # OR builds a single {{b1}} blank after the prompt from q["answers"].
        # ----------------------------
        elif t == "fill_in_blank":
            blanks = q.get("blanks") or []
            twb = q.get("text_with_blanks") or q.get("prompt_html") or q.get("prompt") or ""
            if not blanks:
                # single-blank fallback
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

        else:
            raise ValueError(f"Unsupported question type in this baseline: {t}")

        return {"item": item}

# ---------- Posting (form first, then JSON) ----------

def _post_form(url: str, token: str, payload: dict):
    # Canvas is happiest when 'item' is a form field containing the item JSON string.
    return requests.post(
        url,
        headers=H(token),
        data={"item": json.dumps(payload["item"])},
        timeout=60,
    )

def _post_json(url: str, token: str, payload: dict):
    # Some tenants accept JSON; keep the same shape.
    return requests.post(
        url,
        headers={**H(token), "Content-Type": "application/json"},
        json={"item": payload["item"]},
        timeout=60,
    )

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    # Form first (matches the working MC path in your repo), then JSON fallback, retry 5xx.
    delays = [1, 2, 4, 6]
    for i, d in enumerate([0] + delays):
        if d: time.sleep(d)
        r = _post_form(url, token, item_payload)
        if r.status_code in (200, 201): return r
        if 500 <= r.status_code < 600:  # retry on server errors
            continue

        r2 = _post_json(url, token, item_payload)
        if r2.status_code in (200, 201): return r2
        if 500 <= r2.status_code < 600:  # try next retry step
            continue
        return r2  # 4xx — stop immediately

    return r
