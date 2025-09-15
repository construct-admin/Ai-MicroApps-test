# new_quiz_items.py
import uuid, time, json, requests
from typing import Dict, Any, List
from canvas_api import BASE, H

def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice","multiple_answer","true_false","essay","numeric",
    "matching","ordering","categorization","fill_in_blank",
    "file_upload","hot_spot","formula"
]

class NewQuizItemBuilder:
    """
    Builds request bodies for the New Quiz Items API.
    Each payload returns {"item": {...}} and includes entry.scoring_data with a top-level 'value'.
    """

    def _base(self, q: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "position": None,
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or q.get("short_title") or "",
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": q.get("calculator_type", "none"),
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,   # will be {"value": ...}
                "scoring_algorithm": None,
                "answer_feedback": None,  # only for 'choice'
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
            },
        }

    # ---------- true/false ----------
    def _true_false(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "true-false"
        b["entry"]["interaction_data"] = {
            "true_choice": q.get("true_label", "True"),
            "false_choice": q.get("false_label", "False"),
        }
        b["entry"]["scoring_data"] = {"value": bool(q.get("correct", True))}
        b["entry"]["scoring_algorithm"] = "Equivalence"
        return {"item": b}

    # ---------- multiple choice ----------
    def _multiple_choice(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "choice"

        choices, correct_id, answers_feedback = [], None, {}
        shuffle = bool(q.get("shuffle", False))
        vary_points = bool(q.get("vary_points_by_answer", False))
        per_points = q.get("per_answer_points") or {}

        for idx, ans in enumerate(q.get("answers", []), start=1):
            cid = _uuid()
            label = ans.get("html") or ans.get("text") or ""
            choices.append({"id": cid, "position": idx, "item_body": label})
            if ans.get("is_correct"):
                correct_id = cid
            if ans.get("feedback_html"):
                answers_feedback[cid] = ans["feedback_html"]

        b["entry"]["interaction_data"] = {"choices": choices}
        b["entry"]["properties"] = {
            "shuffle_rules": {"choices": {"shuffled": shuffle}},
            "vary_points_by_answer": vary_points,
        }
        if vary_points:
            values = [{"value": c["id"], "points": float(per_points.get(c["position"], 0))} for c in choices]
            b["entry"]["scoring_data"] = {"value": correct_id, "values": values}
            b["entry"]["scoring_algorithm"] = "VaryPointsByAnswer"
        else:
            b["entry"]["scoring_data"] = {"value": correct_id}
            b["entry"]["scoring_algorithm"] = "Equivalence"

        b["entry"]["answer_feedback"] = answers_feedback or None  # only valid for 'choice' per docs. :contentReference[oaicite:6]{index=6}
        return {"item": b}

    # ---------- multiple answer ----------
    def _multiple_answer(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "multi-answer"

        choices, correct_ids = [], []
        shuffle = bool(q.get("shuffle", False))
        algo = "PartialScore" if q.get("partial_credit", True) else "AllOrNothing"

        for idx, ans in enumerate(q.get("answers", []), start=1):
            cid = _uuid()
            label = ans.get("html") or ans.get("text") or ""
            choices.append({"id": cid, "position": idx, "item_body": label})
            if ans.get("is_correct"):
                correct_ids.append(cid)

        b["entry"]["interaction_data"] = {"choices": choices}
        b["entry"]["properties"] = {"shuffle_rules": {"choices": {"shuffled": shuffle}}}
        b["entry"]["scoring_data"] = {"value": correct_ids}
        b["entry"]["scoring_algorithm"] = algo
        return {"item": b}

    # ---------- essay ----------
    def _essay(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "essay"
        b["entry"]["interaction_data"] = {}
        b["entry"]["scoring_data"] = {"value": q.get("grading_notes") or ""}
        b["entry"]["scoring_algorithm"] = "None"
        return {"item": b}

    # ---------- numeric ----------
    # value is a LIST of numeric specs: exactResponse | marginOfError | withinARange | preciseResponse. :contentReference[oaicite:7]{index=7}
    def _numeric(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "numeric"
        spec = q.get("numeric") or {}
        answers = []

        if "min" in spec and "max" in spec:
            answers.append({"type": "withinARange", "min": str(spec["min"]), "max": str(spec["max"])})
        elif "exact" in spec and spec.get("tolerance"):
            answers.append({
                "type": "marginOfError",
                "value": str(spec["exact"]),
                "margin": str(spec["tolerance"]),
                "margin_type": spec.get("margin_type", "absolute"),
            })
        elif "exact" in spec and spec.get("precision"):
            answers.append({
                "type": "preciseResponse",
                "value": str(spec["exact"]),
                "precision": str(spec["precision"]),
                "precision_type": spec.get("precision_type", "decimalPlaces"),
            })
        elif "exact" in spec:
            answers.append({"type": "exactResponse", "value": str(spec["exact"])})
        else:
            answers.append({"type": "exactResponse", "value": ""})

        b["entry"]["interaction_data"] = {}
        b["entry"]["scoring_data"] = {"value": answers}
        b["entry"]["scoring_algorithm"] = "Numeric"
        return {"item": b}

    # ---------- ordering ----------
    def _ordering(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "ordering"
        items = [{"id": _uuid(), "position": i, "item_body": text} for i, text in enumerate(q.get("order", []), start=1)]
        b["entry"]["interaction_data"] = {"choices": items}
        b["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
        b["entry"]["scoring_algorithm"] = "DeepEquals"
        return {"item": b}

    # ---------- matching ----------
    # Uses questions[] + answers[]; scoring_data.value maps question_id -> answer string.
    def _matching(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "matching"

        questions, answers, value_map, matches = [], [], {}, []
        distractors = q.get("distractors", [])

        for pair in q.get("pairs", []):
            qid = _uuid()
            questions.append({"id": qid, "item_body": pair["prompt"]})
            answers.append(pair["answer"])
            value_map[qid] = pair["answer"]
            matches.append({"question_id": qid, "question_body": pair["prompt"], "answer_body": pair["answer"]})

        for d in distractors:
            answers.append(d)

        b["entry"]["interaction_data"] = {"questions": questions, "answers": answers, "distractors": distractors}
        b["entry"]["scoring_data"] = {"value": value_map}
        b["entry"]["scoring_algorithm"] = "DeepEquals"
        b["entry"]["edit_data"] = {"matches": matches, "distractors": distractors}
        return {"item": b}

    # ---------- categorization ----------
    # categories & distractors as OBJECTS keyed by UUID; include category_order and score_method. :contentReference[oaicite:8]{index=8}
    def _categorization(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "categorization"

        cat_objs, cat_order = {}, []
        for cat in q.get("categories", []):
            cid = _uuid()
            cat_objs[cid] = {"id": cid, "item_body": cat["name"]}
            cat_order.append(cid)

        distractors = {}
        idx_to_cat_uuid = {i: list(cat_objs.keys())[i] for i in range(len(cat_objs))}
        scoring_value = []

        if q.get("categories"):
            for i, cat in enumerate(q["categories"]):
                cat_uuid = idx_to_cat_uuid[i]
                correct_ids = []
                for text in cat.get("items", []):
                    aid = _uuid()
                    distractors[aid] = {"id": aid, "item_body": text}
                    correct_ids.append(aid)
                scoring_value.append({
                    "id": cat_uuid,
                    "scoring_data": {"value": correct_ids},
                    "scoring_algorithm": "AllOrNothing",
                })
        for extra in q.get("distractors", []):
            aid = _uuid()
            distractors[aid] = {"id": aid, "item_body": extra}

        b["entry"]["interaction_data"] = {
            "categories": cat_objs,
            "distractors": distractors,
            "category_order": cat_order,
        }
        b["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
        b["entry"]["scoring_data"] = {"value": scoring_value, "score_method": "all_or_nothing"}
        b["entry"]["scoring_algorithm"] = "Categorization"
        return {"item": b}

    # ---------- fill in the blank (rich) ----------
    # interaction_data.answers.blanks + value.blank_to_correct_answer (canonical). :contentReference[oaicite:9]{index=9}
    def _fill_in_blank(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "rich-fill-blank"

        text = q.get("text_with_blanks") or q.get("prompt_html") or ""
        blanks_in = q.get("blanks") or []  # [{'id':'b1','alternatives':[...]}]
        blanks_out, blank_to_correct = [], {}

        for blk in blanks_in:
            bid = blk["id"]
            alts = blk.get("alternatives") or blk.get("correct") or blk.get("answers") or []
            if not alts:
                alts = [""]
            blanks_out.append({"id": bid, "alternatives": alts})
            blank_to_correct[bid] = alts[0]

        b["entry"]["interaction_data"] = {"text_with_blanks": text, "answers": {"blanks": blanks_out}}
        b["entry"]["scoring_data"] = {"value": {"blank_to_correct_answer": blank_to_correct}}
        b["entry"]["scoring_algorithm"] = "MultipleMethods"
        return {"item": b}

    # ---------- file upload ----------
    def _file_upload(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "file-upload"
        files_count = int(q.get("files_count", 1))
        b["entry"]["interaction_data"] = {
            "files_count": str(files_count),
            "restrict_count": bool(q.get("restrict_count", False)),
        }
        b["entry"]["properties"] = {
            "allowed_types": q.get("allowed_types", ""),
            "restrict_types": bool(q.get("restrict_types", False)),
        }
        b["entry"]["scoring_data"] = {"value": ""}  # nothing to autograde
        b["entry"]["scoring_algorithm"] = "None"
        return {"item": b}

    # ---------- hot spot ----------
    # Include 'image_url' after uploading via media_upload_url (see canvas_api.get_items_media_upload_url). :contentReference[oaicite:10]{index=10}
    def _hot_spot(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "hot-spot"
        b["entry"]["interaction_data"] = {"image_url": q.get("image_url", "")}
        b["entry"]["scoring_data"] = {"value": []}  # regions are typically configured in UI
        b["entry"]["scoring_algorithm"] = "HotSpot"
        return {"item": b}

    # ---------- formula ----------
    def _formula(self, q: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "formula"
        b["entry"]["interaction_data"] = {}
        b["entry"]["scoring_data"] = {"value": []}
        b["entry"]["scoring_algorithm"] = "Numeric"
        return {"item": b}

    # ---------- public entry ----------
    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t = (q.get("type") or "").lower()
        if t == "true_false":         return self._true_false(q)
        if t == "multiple_choice":    return self._multiple_choice(q)
        if t == "multiple_answer":    return self._multiple_answer(q)
        if t == "essay":              return self._essay(q)
        if t == "numeric":            return self._numeric(q)
        if t == "ordering":           return self._ordering(q)
        if t == "matching":           return self._matching(q)
        if t == "categorization":     return self._categorization(q)
        if t == "fill_in_blank":      return self._fill_in_blank(q)
        if t == "file_upload":        return self._file_upload(q)
        if t == "hot_spot":           return self._hot_spot(q)
        if t == "formula":            return self._formula(q)
        raise ValueError(f"Unsupported question type: {t}")

# ---------- resilient poster (handles occasional 5xx) ----------
def _try_post_form(url, token, payload):
    return requests.post(url, headers=H(token), data={"item": json.dumps(payload["item"])}, timeout=60)

def _try_post_json(url, token, payload):
    return requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    delays = [1, 2, 3, 5, 8]  # mild backoff for flaky saves
    attempts = len(delays) + 1
    for i in range(attempts):
        r = _try_post_json(url, token, item_payload)
        if r.status_code in (200, 201):
            return r
        if 500 <= r.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue
        # try form encoding as fallback
        r2 = _try_post_form(url, token, item_payload)
        if r2.status_code in (200, 201):
            return r2
        if 500 <= r2.status_code < 600 and i < len(delays):
            time.sleep(delays[i]); continue
        return r2
    return r
