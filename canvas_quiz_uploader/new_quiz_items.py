
import uuid, json, requests
from typing import Dict, Any, List
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice","multiple_answer","true_false","short_answer",
    "essay","numeric","matching","ordering","categorization","fill_in_blank",
    "file_upload","hot_spot","formula"
]

class NewQuizItemBuilder:
    """
    Builds Canvas New Quizzes Items payloads for the supported normalized schema.
    """
    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        base = {
            "position": None,
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or "",
                "item_body": q.get("prompt_html") or "",
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
        t = (q.get("type") or "").lower()

        # Multiple Choice
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in q.get("answers", []):
                cid = _uuid()
                # New Quizzes uses "text" (plain) or "item_body" (html). We'll use text.
                choices.append({"id": cid, "text": ans.get("text", "")})
                if ans.get("is_correct"):
                    correct_id = cid
                if ans.get("feedback_html"):
                    per_ans_fb[cid] = ans["feedback_html"]

            base["entry"]["interaction_type_slug"] = "choice"
            base["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base["entry"]["scoring_data"] = {"value": correct_id}
            base["entry"]["scoring_algorithm"] = "Equivalence"
            base["entry"]["answer_feedback"] = per_ans_fb or None

        # Multiple Answer
        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in q.get("answers", []):
                cid = _uuid()
                choices.append({"id": cid, "text": ans.get("text","")})
                if ans.get("is_correct"):
                    correct_ids.append(cid)

            base["entry"]["interaction_type_slug"] = "multi-answer"
            base["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base["entry"]["scoring_data"] = {"values": correct_ids}
            base["entry"]["scoring_algorithm"] = "PartialScore"  # or AllOrNothing

        # True/False
        elif t == "true_false":
            base["entry"]["interaction_type_slug"] = "true-false"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            base["entry"]["scoring_algorithm"] = "Equivalence"

        # Short Answer -> rich-fill-blank (single blank with accepted answers)
        elif t == "short_answer":
            acc = [a.get("text","") for a in q.get("answers", []) if a.get("text")]
            blank_id = "b1"
            alts = [{"id": _uuid(), "text": s} for s in acc]
            base["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base["entry"]["interaction_data"] = {
                "text_with_blanks": q["prompt_html"] + f" {{$${blank_id}}}",
                "blanks": {blank_id: alts}
            }
            base["entry"]["scoring_data"] = {
                "blank_to_correct_answer_ids": {blank_id: [a["id"] for a in alts]}
            }
            base["entry"]["scoring_algorithm"] = "MultipleMethods"

        # Essay
        elif t == "essay":
            base["entry"]["interaction_type_slug"] = "essay"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": None}
            base["entry"]["scoring_algorithm"] = "None"

        # Numeric
        elif t == "numeric":
            spec = q.get("numeric") or {}
            base["entry"]["interaction_type_slug"] = "numeric"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {
                "answers": [{
                    "exact": float(spec.get("exact")) if spec.get("exact") is not None else 0.0,
                    "tolerance": float(spec.get("tolerance", 0))
                }]
            }
            base["entry"]["scoring_algorithm"] = "Numeric"

        # Matching
        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in q.get("pairs", []):
                right = pair["match"]
                rcid = right_ids.get(right)
                if not rcid:
                    rcid = _uuid()
                    right_ids[right] = rcid
                    choices.append({"id": rcid, "text": right})
                prompts.append({"id": _uuid(), "text": pair["prompt"], "answer_choice_id": rcid})

            base["entry"]["interaction_type_slug"] = "matching"
            base["entry"]["interaction_data"] = {"choices": choices, "prompts": prompts}
            base["entry"]["scoring_data"] = {
                "prompts_to_choice_ids": {p["id"]: p["answer_choice_id"] for p in prompts}
            }
            base["entry"]["scoring_algorithm"] = "DeepEquals"

        # Ordering
        elif t == "ordering":
            items = [{"id": _uuid(), "text": x} for x in q.get("order", [])]
            base["entry"]["interaction_type_slug"] = "ordering"
            base["entry"]["interaction_data"] = {"choices": items}
            base["entry"]["scoring_data"] = {"ordered_choice_ids": [c["id"] for c in items]}
            base["entry"]["scoring_algorithm"] = "DeepEquals"

        # Categorization
        elif t == "categorization":
            cats = [{"id": _uuid(), "name": c["name"]} for c in q.get("categories", [])]
            id_by_name = {c["name"]: cats[i]["id"] for i, c in enumerate(q.get("categories", []))}
            choices = []
            for c in q.get("categories", []):
                for item in c.get("items", []):
                    choices.append({"id": _uuid(), "text": item, "category_id": id_by_name[c["name"]]})

            base["entry"]["interaction_type_slug"] = "categorization"
            base["entry"]["interaction_data"] = {"categories": cats, "choices": choices}
            base["entry"]["scoring_data"] = {
                "choice_to_category_id": {c["id"]: c["category_id"] for c in choices}
            }
            base["entry"]["scoring_algorithm"] = "Categorization"

        # Fill-in-Blank (rich)
        elif t == "fill_in_blank":
            blanks = q.get("blanks", [])
            blanks_map = {b["id"]: [{"id": _uuid(), "text": alt} for alt in b.get("correct", [])] for b in blanks}

            base["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base["entry"]["interaction_data"] = {
                "text_with_blanks": q["prompt_html"],  # contains {{b1}} etc.
                "blanks": blanks_map
            }
            base["entry"]["scoring_data"] = {
                "blank_to_correct_answer_ids": {bid: [a["id"] for a in alts] for bid, alts in blanks_map.items()}
            }
            base["entry"]["scoring_algorithm"] = "MultipleMethods"

        # File Upload (manual grading)
        elif t == "file_upload":
            base["entry"]["interaction_type_slug"] = "file-upload"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": None}
            base["entry"]["scoring_algorithm"] = "None"

        # Hot Spot (requires pre-uploaded image URL)
        elif t == "hot_spot":
            base["entry"]["interaction_type_slug"] = "hot-spot"
            base["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            base["entry"]["scoring_data"] = {"hotspot_ids": [hs.get("id") or _uuid() for hs in q.get("hotspots", [])]}
            base["entry"]["scoring_algorithm"] = "HotSpot"

        # Formula (stub -> Numeric rules)
        elif t == "formula":
            base["entry"]["interaction_type_slug"] = "formula"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {}
            base["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": base}

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: Dict[str, Any], token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    # Items API accepts "item" as form-encoded JSON, but JSON body works on most sites.
    r = requests.post(url, headers=H(token), data={"item": json.dumps(item_payload["item"])}, timeout=60)
    return r
