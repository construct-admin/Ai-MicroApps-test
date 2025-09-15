# new_quiz_items.py
import uuid, time, json, requests
from typing import Dict, Any, List
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice", "multiple_answer", "true_false", "short_answer",
    "essay", "numeric", "matching", "ordering", "categorization", "fill_in_blank",
    "file_upload", "hot_spot", "formula"
]

def _label_triplet(s: str) -> Dict[str, str]:
    """Return a dict that includes every label key the UI/API might read."""
    return {"text": s, "item_body": s, "itemBody": s}

class NewQuizItemBuilder:
    """Builds New Quizzes Item payloads. Ensures entry.scoring_data has a top-level 'value'."""

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
                "scoring_data": None,          # always becomes {"value": ...}
                "scoring_algorithm": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
                "answer_feedback": None,
            }
        }
        t = (q.get("type") or "").lower()

        # ---------- Multiple Choice ----------
        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in q.get("answers", []):
                cid = _uuid()
                label = ans.get("text", "")
                trip = _label_triplet(label)
                choices.append({"id": cid, **trip})
                if ans.get("is_correct"):
                    correct_id = cid
                if ans.get("feedback_html"):
                    per_ans_fb[cid] = ans["feedback_html"]

            base["entry"]["interaction_type_slug"] = "choice"
            base["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}},
                "vary_points_by_answer": False
            }
            base["entry"]["scoring_data"] = {"value": correct_id}
            base["entry"]["scoring_algorithm"] = "Equivalence"
            base["entry"]["answer_feedback"] = per_ans_fb or None

        # ---------- Multiple Answer ----------
        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in q.get("answers", []):
                cid = _uuid()
                label = ans.get("text", "")
                choices.append({"id": cid, **_label_triplet(label)})
                if ans.get("is_correct"):
                    correct_ids.append(cid)

            base["entry"]["interaction_type_slug"] = "multi-answer"
            base["entry"]["interaction_data"] = {
                "choices": choices,
                "shuffle_answers": bool(q.get("shuffle", True))
            }
            base["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}}
            }
            base["entry"]["scoring_data"] = {"value": correct_ids}
            base["entry"]["scoring_algorithm"] = "PartialScore"

        # ---------- True / False ----------
        elif t == "true_false":
            base["entry"]["interaction_type_slug"] = "true-false"
            base["entry"]["interaction_data"] = {
                **_label_triplet(q.get("true_label", "True")),
                **{"false_choice": q.get("false_label", "False")}
            }
            # UI ignores labels above; correctness drives scoring
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            base["entry"]["scoring_algorithm"] = "Equivalence"

        # ---------- Short Answer -> rich-fill-blank (single blank) ----------
        elif t == "short_answer":
            acc = [a.get("text", "") for a in q.get("answers", []) if a.get("text")]
            blank_id = "b1"
            alts = [{"id": _uuid(), **_label_triplet(s)} for s in acc]
            base["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base["entry"]["interaction_data"] = {
                "text_with_blanks": (q.get("prompt_html") or "") + " {{b1}}",
                "blanks": {blank_id: alts}
            }
            base["entry"]["scoring_data"] = {
                "value": {
                    "blank_to_correct_answer_ids": {blank_id: [a["id"] for a in alts]}
                }
            }
            base["entry"]["scoring_algorithm"] = "MultipleMethods"

        # ---------- Essay ----------
        elif t == "essay":
            base["entry"]["interaction_type_slug"] = "essay"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": None}
            base["entry"]["scoring_algorithm"] = "None"

        # ---------- Numeric ----------
        elif t == "numeric":
            spec = q.get("numeric") or {}
            exact = spec.get("exact")
            tol = float(spec.get("tolerance", 0) or 0)
            base["entry"]["interaction_type_slug"] = "numeric"
            base["entry"]["interaction_data"] = {}

            if exact is not None and tol > 0:
                base["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "marginOfError",
                        "value": str(exact),
                        "margin": str(tol),
                        "margin_type": "absolute"
                    }]
                }
            elif exact is not None:
                base["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "exactResponse",
                        "value": str(exact)
                    }]
                }
            else:
                base["entry"]["scoring_data"] = {
                    "value": [{
                        "id": _uuid(),
                        "type": "exactResponse",
                        "value": ""
                    }]
                }
            base["entry"]["scoring_algorithm"] = "Numeric"

        # ---------- Matching ----------
        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in q.get("pairs", []):
                right = pair["match"]
                rcid = right_ids.get(right)
                if not rcid:
                    rcid = _uuid()
                    right_ids[right] = rcid
                    choices.append({"id": rcid, **_label_triplet(right)})
                prompts.append({"id": _uuid(), **_label_triplet(pair["prompt"]), "answer_choice_id": rcid})

            base["entry"]["interaction_type_slug"] = "matching"
            base["entry"]["interaction_data"] = {"choices": choices, "prompts": prompts}
            base["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
            base["entry"]["scoring_data"] = {
                "value": {p["id"]: p["answer_choice_id"] for p in prompts}
            }
            base["entry"]["scoring_algorithm"] = "DeepEquals"

        # ---------- Ordering ----------
        elif t == "ordering":
            items = [{"id": _uuid(), **_label_triplet(x)} for x in q.get("order", [])]
            base["entry"]["interaction_type_slug"] = "ordering"
            base["entry"]["interaction_data"] = {"choices": items}
            base["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
            base["entry"]["scoring_algorithm"] = "DeepEquals"

        # ---------- Categorization ----------
        elif t == "categorization":
            # Canvas UI for Categorization reads itemBody on BOTH categories and items.
            # Build categories as an object map, distractors as an object map, and include category_order.
            cat_map: Dict[str, Dict[str, Any]] = {}
            cat_order: List[str] = []
            scoring_value: List[Dict[str, Any]] = []
            distractors: Dict[str, Dict[str, Any]] = {}

            # Build categories and their items
            for cat in q.get("categories", []):
                cid = _uuid()
                cat_map[cid] = {"id": cid, **_label_triplet(cat["name"])}
                cat_order.append(cid)

                correct_ids_for_cat: List[str] = []
                for text in cat.get("items", []):
                    aid = _uuid()
                    distractors[aid] = {"id": aid, **_label_triplet(text)}
                    correct_ids_for_cat.append(aid)

                scoring_value.append({
                    "id": cid,
                    "scoring_data": {"value": correct_ids_for_cat},
                    "scoring_algorithm": "AllOrNothing",
                })

            # Add any global distractors
            for extra in q.get("distractors", []):
                aid = _uuid()
                distractors[aid] = {"id": aid, **_label_triplet(extra)}

            base["entry"]["interaction_type_slug"] = "categorization"
            base["entry"]["interaction_data"] = {
                "categories": cat_map,         # {id: {id, item_body/itemBody}}
                "distractors": distractors,    # {id: {id, item_body/itemBody}}
                "category_order": cat_order
            }
            base["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
            base["entry"]["scoring_data"] = {"value": scoring_value, "score_method": "all_or_nothing"}
            base["entry"]["scoring_algorithm"] = "Categorization"

        # ---------- Fill-in-Blank (rich) ----------
        elif t == "fill_in_blank":
            blanks = q.get("blanks", [])
            blanks_map = {
                b["id"]: [{"id": _uuid(), **_label_triplet(alt)} for alt in b.get("correct", [])]
                for b in blanks
            }
            base["entry"]["interaction_type_slug"] = "rich-fill-blank"
            base["entry"]["interaction_data"] = {
                "text_with_blanks": q.get("prompt_html") or "",
                "blanks": blanks_map
            }
            base["entry"]["scoring_data"] = {
                "value": {
                    "blank_to_correct_answer_ids": {
                        bid: [a["id"] for a in alts] for bid, alts in blanks_map.items()
                    }
                }
            }
            base["entry"]["scoring_algorithm"] = "MultipleMethods"

        # ---------- File Upload ----------
        elif t == "file_upload":
            base["entry"]["interaction_type_slug"] = "file-upload"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": None}
            base["entry"]["scoring_algorithm"] = "None"

        # ---------- Hot Spot ----------
        elif t == "hot_spot":
            base["entry"]["interaction_type_slug"] = "hot-spot"
            base["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            base["entry"]["scoring_data"] = {"value": [hs.get("id") for hs in q.get("hotspots", [])]}
            base["entry"]["scoring_algorithm"] = "HotSpot"

        # ---------- Formula ----------
        elif t == "formula":
            base["entry"]["interaction_type_slug"] = "formula"
            base["entry"]["interaction_data"] = {}
            base["entry"]["scoring_data"] = {"value": []}  # minimal
            base["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": base}

# ---------- resilient poster with 5xx retries ----------
def _try_post_form(url, token, payload):
    return requests.post(url, headers=H(token), data={"item": json.dumps(payload["item"])}, timeout=60)

def _try_post_json(url, token, payload):
    return requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    delays = [1, 2, 3, 5, 8]
    attempts = len(delays) + 1
    for i in range(attempts):
        r = _try_post_json(url, token, item_payload)
        if r.status_code in (200, 201):
            return r
        if 500 <= r.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue
        r2 = _try_post_form(url, token, item_payload)
        if r2.status_code in (200, 201):
            return r2
        if 500 <= r2.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue
        return r2
    return r
