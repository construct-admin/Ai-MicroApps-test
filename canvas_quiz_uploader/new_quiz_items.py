# --- new_quiz_items.py (complete) ---

import uuid
from typing import Dict, Any, List

def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice", "multiple_answer", "true_false", "essay",
    "numeric", "matching", "ordering", "categorization",
    "fill_in_blank",  # rich-fill-blank
    "file_upload", "hot_spot", "formula"
]

class NewQuizItemBuilder:
    """
    Builds request bodies that match the official New Quiz Items API.
    Every payload returns: {"item": {...}} and includes entry.scoring_data.value.
    """

    def _base(self, q: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "position": None,  # caller can set
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or (q.get("short_title") or ""),
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": q.get("calculator_type", "none"),
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,   # <-- will always be {"value": ...}
                "scoring_algorithm": None,
                # Only 'choice' supports per-answer feedback
                "answer_feedback": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v}
            }
        }

    # ------------- builders for each type -------------

    def _true_false(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: interaction_data has true_choice/false_choice, scoring_data.value is boolean
        # Scoring algorithm: Equivalence
        # Ref: True/False sections. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "true-false"
        b["entry"]["interaction_data"] = {
            "true_choice": q.get("true_label", "True"),
            "false_choice": q.get("false_label", "False")
        }
        b["entry"]["scoring_data"] = {"value": bool(q.get("correct", True))}
        b["entry"]["scoring_algorithm"] = "Equivalence"
        return {"item": b}

    def _multiple_choice(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: choices are a list of {id, position, item_body}; algorithm Equivalence or VaryPointsByAnswer
        # Only 'choice' supports answer_feedback. 
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
            fb = ans.get("feedback_html")
            if fb:
                answers_feedback[cid] = fb

        b["entry"]["interaction_data"] = {"choices": choices}
        b["entry"]["properties"] = {
            "shuffle_rules": {"choices": {"shuffled": shuffle}},
            "vary_points_by_answer": vary_points
        }
        if vary_points:
            # if per-answer points specified, include values; docs permit VaryPointsByAnswer
            values = [{"value": c["id"], "points": float(per_points.get(c["position"], 0))} for c in choices]
            b["entry"]["scoring_data"] = {"value": correct_id, "values": values}
            b["entry"]["scoring_algorithm"] = "VaryPointsByAnswer"
        else:
            b["entry"]["scoring_data"] = {"value": correct_id}
            b["entry"]["scoring_algorithm"] = "Equivalence"

        b["entry"]["answer_feedback"] = answers_feedback or None
        return {"item": b}

    def _multiple_answer(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: choices list; scoring_data.value is list of UUIDs; algorithm PartialScore or AllOrNothing. 
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

    def _essay(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: algorithm None; scoring_data.value may contain grading notes (string). 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "essay"
        b["entry"]["interaction_data"] = {}  # UI options are optional; omit safely
        b["entry"]["scoring_data"] = {"value": q.get("grading_notes") or ""}
        b["entry"]["scoring_algorithm"] = "None"
        return {"item": b}

    def _numeric(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: value is a LIST with one or more numeric spec objects: exactResponse, marginOfError, withinARange, preciseResponse. 
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
                "margin_type": spec.get("margin_type", "absolute")
            })
        elif "exact" in spec and spec.get("precision"):
            answers.append({
                "type": "preciseResponse",
                "value": str(spec["exact"]),
                "precision": str(spec["precision"]),
                "precision_type": spec.get("precision_type", "decimalPlaces")
            })
        elif "exact" in spec:
            answers.append({"type": "exactResponse", "value": str(spec["exact"])})
        else:
            # last resort—allow blank exactResponse to satisfy required shape
            answers.append({"type": "exactResponse", "value": ""})

        b["entry"]["interaction_data"] = {}
        b["entry"]["scoring_data"] = {"value": answers}
        b["entry"]["scoring_algorithm"] = "Numeric"
        return {"item": b}

    def _ordering(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: choices list {id, position, item_body}; scoring_data.value = list of IDs in correct order. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "ordering"
        items = []
        for idx, text in enumerate(q.get("order", []), start=1):
            items.append({"id": _uuid(), "position": idx, "item_body": text})
        b["entry"]["interaction_data"] = {"choices": items}
        b["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
        b["entry"]["scoring_algorithm"] = "DeepEquals"
        return {"item": b}

    def _matching(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: interaction_data has 'questions' (with ids) and 'answers' (strings).
        # scoring_data.value maps question_id -> answer string.
        # edit_data may include matches/distractors to pre-populate UI. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "matching"

        questions, answers, value_map, matches = [], [], {}, []
        distractors = q.get("distractors", [])  # optional extra answers

        for pair in q.get("pairs", []):
            qid = _uuid()
            questions.append({"id": qid, "item_body": pair["prompt"]})
            answers.append(pair["answer"])
            value_map[qid] = pair["answer"]
            matches.append({"question_id": qid, "question_body": pair["prompt"], "answer_body": pair["answer"]})

        # add distractors to the answers list (docs: correct + incorrect live together in interaction_data.answers)
        for d in distractors:
            answers.append(d)

        b["entry"]["interaction_data"] = {"questions": questions, "answers": answers, "distractors": distractors}
        b["entry"]["scoring_data"] = {"value": value_map}
        b["entry"]["scoring_algorithm"] = "DeepEquals"
        # edit_data helps the UI reconstruct pairs
        b["entry"]["edit_data"] = {"matches": matches, "distractors": distractors}
        return {"item": b}

    def _categorization(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: categories and distractors are OBJECTS keyed by UUID; scoring_data.value is a list of
        # {id: <category_uuid>, scoring_data: {value: [answer_uuid,...]}, scoring_algorithm: "AllOrNothing"}
        # plus top-level score_method "all_or_nothing". Also include category_order. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "categorization"

        # Build categories
        cat_objs, cat_order = {}, []
        scoring_value = []

        for cat in q.get("categories", []):
            cid = _uuid()
            cat_objs[cid] = {"id": cid, "item_body": cat["name"]}
            cat_order.append(cid)

        # Build distractors/choices bucket (all answers — right & wrong — live under 'distractors')
        distractors = {}
        # Map category index -> list of answer UUIDs
        idx_to_cat_uuid = {i: list(cat_objs.keys())[i] for i in range(len(cat_objs))}

        # Accept input either as categories: [{name, items:[...]}] or as choices with category_name
        if q.get("categories"):
            for i, cat in enumerate(q["categories"]):
                cat_uuid = idx_to_cat_uuid[i]
                correct_answer_ids = []
                for text in cat.get("items", []):
                    aid = _uuid()
                    distractors[aid] = {"id": aid, "item_body": text}
                    correct_answer_ids.append(aid)
                scoring_value.append({
                    "id": cat_uuid,
                    "scoring_data": {"value": correct_answer_ids},
                    "scoring_algorithm": "AllOrNothing"
                })
        # optional extra wrong options:
        for extra in q.get("distractors", []):
            aid = _uuid()
            distractors[aid] = {"id": aid, "item_body": extra}

        b["entry"]["interaction_data"] = {
            "categories": cat_objs,
            "distractors": distractors,
            "category_order": cat_order
        }
        b["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
        b["entry"]["scoring_data"] = {"value": scoring_value, "score_method": "all_or_nothing"}
        b["entry"]["scoring_algorithm"] = "Categorization"
        return {"item": b}

    def _fill_in_blank(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs (current): rich-fill-blank uses 'text_with_blanks' and
        # interaction_data.answers.blanks: [{id, alternatives:[...]}]
        # scoring_data.value.blank_to_correct_answer maps blank -> ONE correct answer string. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "rich-fill-blank"

        text = q.get("text_with_blanks") or q.get("prompt_html") or ""
        blanks_in = q.get("blanks") or []  # [{'id': 'b1', 'alternatives':['a','b']}]

        blanks_out = []
        blank_to_correct = {}
        for blk in blanks_in:
            bid = blk["id"]
            alts = blk.get("alternatives") or blk.get("correct") or blk.get("answers") or []
            if not alts:
                alts = [""]
            blanks_out.append({"id": bid, "alternatives": alts})
            # pick first as canonical correct (others accepted)
            blank_to_correct[bid] = alts[0]

        b["entry"]["interaction_data"] = {"text_with_blanks": text, "answers": {"blanks": blanks_out}}
        b["entry"]["properties"] = {}
        b["entry"]["scoring_data"] = {"value": {"blank_to_correct_answer": blank_to_correct}}
        b["entry"]["scoring_algorithm"] = "MultipleMethods"
        return {"item": b}

    def _file_upload(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: interaction_data.files_count & restrict_count; properties.allowed_types, restrict_types. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "file-upload"
        files_count = int(q.get("files_count", 1))
        b["entry"]["interaction_data"] = {"files_count": str(files_count), "restrict_count": bool(q.get("restrict_count", False))}
        b["entry"]["properties"] = {
            "allowed_types": q.get("allowed_types", ""),
            "restrict_types": bool(q.get("restrict_types", False))
        }
        b["entry"]["scoring_data"] = {"value": ""}  # nothing to autograde
        b["entry"]["scoring_algorithm"] = "None"
        return {"item": b}

    def _hot_spot(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs: first GET media_upload_url, upload image to that URL, then include image URL here.
        # The API docs focus on image provisioning; correct regions are managed in UI.
        # We'll accept an already-hosted URL via q["image_url"]. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "hot-spot"
        b["entry"]["interaction_data"] = {"image_url": q.get("image_url", "")}
        b["entry"]["scoring_data"] = {"value": []}  # minimal valid shape; regions typically configured in UI
        b["entry"]["scoring_algorithm"] = "HotSpot"
        return {"item": b}

    def _formula(self, q: Dict[str, Any]) -> Dict[str, Any]:
        # Docs list 'formula' type but with minimal API surface; treat similar to numeric scaffold. 
        b = self._base(q)
        b["entry"]["interaction_type_slug"] = "formula"
        b["entry"]["interaction_data"] = {}
        b["entry"]["scoring_data"] = {"value": []}
        b["entry"]["scoring_algorithm"] = "Numeric"
        return {"item": b}

    # Public entry
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
        if t == "fill_in_blank":      return self._fill_in_blank(q)  # rich
        if t == "file_upload":        return self._file_upload(q)
        if t == "hot_spot":           return self._hot_spot(q)
        if t == "formula":            return self._formula(q)
        raise ValueError(f"Unsupported question type: {t}")
