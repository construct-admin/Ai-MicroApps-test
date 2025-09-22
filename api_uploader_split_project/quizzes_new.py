# quizzes_new.py
"""
New Quizzes helpers (Instructure LTI 1.3 New Quizzes API)

Exports
-------
add_new_quiz(canvas_domain, course_id, title, description, token)
add_item_for_question(canvas_domain, course_id, assignment_id, q, token, position=1)

The question object `q` is the one your GPT step returns (the JSON at the end of
a <canvas_page> 'quiz' block), e.g.:

{
  "question_type": "multiple_choice_question" | "multiple_answers_question" |
                   "true_false_question" | "essay_question" |
                   "short_answer_question" | "fill_in_multiple_blanks_question" |
                   "matching_question" | "numerical_question",
  "question_name": "...",
  "question_text": "<p>...</p>",
  "answers": [ {"text":"...", "is_correct":true, "feedback":"<p>...</p>"} ],
  "matches": [ {"prompt":"H2O","match":"water"} ],
  "numerical_answer": {"exact": 12.5, "tolerance": 0.5},
  "feedback": {"correct":"<p>...</p>","incorrect":"<p>...</p>","neutral":"<p>...</p>"},
  "shuffle": true
}

Implements the official shapes from:
- Create quiz: POST /api/quiz/v1/courses/:course_id/quizzes
- Create item: POST /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items
Docs: https://developerdocs.instructure.com/services/canvas/resources/new_quizzes
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Tuple, Optional

import requests


API_SCHEMA_VERSION = "new-quizzes-v1.0"


# ──────────────────────────────────────────────────────────────────────────────
# Low-level HTTP
# ──────────────────────────────────────────────────────────────────────────────

def _url(canvas_domain: str, path: str) -> str:
    base = canvas_domain.strip()
    if not base.startswith("http"):
        base = "https://" + base
    return f"{base}{path}"

def _auth_headers(token: str, json_payload: bool = True) -> Dict[str, str]:
    h = {
        "Authorization": f"Bearer {token.strip()}",
    }
    if json_payload:
        h["Content-Type"] = "application/json"
    return h

def _post_json(url: str, token: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int, str]:
    try:
        resp = requests.post(url, headers=_auth_headers(token, json_payload=True), data=json.dumps(payload))
    except Exception as e:
        return False, {"error": str(e)}, 0, ""
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    ok = 200 <= resp.status_code < 300
    return ok, data, resp.status_code, resp.text


# ──────────────────────────────────────────────────────────────────────────────
# Public: create a New Quiz (gets assignment_id)
# ──────────────────────────────────────────────────────────────────────────────

def add_new_quiz(
    canvas_domain: str,
    course_id: str,
    title: str,
    description_html: str,
    token: str,
) -> Tuple[Optional[int], Optional[str], int, str]:
    """
    Returns (assignment_id, error_message, status_code, raw_text)
    """
    url = _url(canvas_domain, f"/api/quiz/v1/courses/{course_id}/quizzes")

    # The create endpoint accepts form-style nested keys OR JSON; JSON is safer for
    # complex item creation later, so we stick to JSON consistently.
    payload = {
        "quiz": {
            "title": title or "New Quiz",
            # 'instructions' is the description HTML
            "instructions": description_html or "",
            # points_possible is optional here; items carry points.
        }
    }

    ok, data, status, raw = _post_json(url, token, payload)
    if not ok:
        return None, data.get("error") or data.get("message") or "create failed", status, raw

    # The New Quiz object returns `assignment_id` which is used for /items
    assignment_id = data.get("assignment_id") or data.get("id")  # fallback just in case
    if not assignment_id:
        return None, "No assignment_id returned by New Quizzes API", status, raw
    return int(assignment_id), None, status, raw


# ──────────────────────────────────────────────────────────────────────────────
# Public: add a question item to a New Quiz
# ──────────────────────────────────────────────────────────────────────────────

def add_item_for_question(
    canvas_domain: str,
    course_id: str,
    assignment_id: int,
    q: Dict[str, Any],
    token: str,
    position: int = 1,
    default_points: float = 1.0,
) -> Tuple[bool, str]:
    """
    Map your GPT JSON to a New Quizzes item and POST it.

    Returns (ok, debug_message)
    """
    try:
        item_payload = _build_item_payload(q, position=position, default_points=default_points)
    except Exception as e:
        return False, f"build payload error: {e}"

    url = _url(canvas_domain, f"/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items")
    ok, data, status, raw = _post_json(url, token, {"item": item_payload})
    if not ok:
        # surface Canvas validation errors to the UI
        err = data.get("errors") or data.get("error") or data.get("message") or raw
        return False, f"Canvas error [{status}]: {err}"
    return True, f"created item id={data.get('id') or '?'}"


# ──────────────────────────────────────────────────────────────────────────────
# Mapping from our storyboard JSON to New Quizzes "item" payload
# ──────────────────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())

def _as_html(s: Optional[str]) -> str:
    return (s or "").strip() or "<p></p>"

def _first_html(*candidates: Optional[str]) -> str:
    for c in candidates:
        if (c or "").strip():
            return c  # already HTML in your pipeline
    return "<p></p>"

def _build_feedback(feedback: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for k in ("correct", "incorrect", "neutral"):
        if feedback and isinstance(feedback.get(k), str) and feedback[k].strip():
            out[k] = feedback[k]
    return out

def _build_item_payload(q: Dict[str, Any], position: int, default_points: float) -> Dict[str, Any]:
    qtype = (q.get("question_type") or "").strip().lower()
    title = q.get("question_name") or ""
    stem_html = _as_html(_first_html(q.get("question_text"), title))

    # Base envelope
    item: Dict[str, Any] = {
        "position": int(position),
        "points_possible": float(q.get("points", default_points)),
        "properties": {},
        "entry_type": "Item",
        "entry": {
            "title": title or "Question",
            "item_body": stem_html,
            "calculator_type": "none",
            # These will be filled by each type handler:
            # "interaction_type_slug": ...,
            # "interaction_data": {...},
            # "properties": {...},
            # "scoring_data": {...},
            # "scoring_algorithm": "...",
        }
    }

    # Overall feedback on the question (rich content)
    fb = q.get("feedback") if isinstance(q.get("feedback"), dict) else {}
    fb_obj = _build_feedback(fb)
    if fb_obj:
        item["entry"]["feedback"] = fb_obj

    # Shuffle (where supported)
    shuffle = bool(q.get("shuffle"))
    shuffle_props_choices = {"shuffle_rules": {"choices": {"shuffled": True}}}

    # Dispatch per type
    if qtype == "multiple_choice_question":
        # choice + Equivalence
        answers = q.get("answers") or []
        choices, correct_id, ans_feedback = [], None, {}
        for idx, ans in enumerate(answers, start=1):
            cid = _uuid()
            choices.append({"id": cid, "position": idx, "item_body": _as_html(ans.get("text"))})
            if ans.get("is_correct"):
                correct_id = cid
            if isinstance(ans.get("feedback"), str) and ans["feedback"].strip():
                ans_feedback[cid] = ans["feedback"]

        if not choices or not correct_id:
            raise ValueError("multiple_choice_question requires at least one correct answer")

        item["entry"].update({
            "interaction_type_slug": "choice",
            "interaction_data": {"choices": choices},
            "properties": (shuffle_props_choices if shuffle else {}),
            "scoring_algorithm": "Equivalence",
            "scoring_data": {"value": correct_id}
        })
        if ans_feedback:
            item["entry"]["answer_feedback"] = ans_feedback
        return item

    if qtype == "multiple_answers_question":
        # multi-answer + PartialScore (or AllOrNothing)
        answers = q.get("answers") or []
        choices, correct_ids = [], []
        for idx, ans in enumerate(answers, start=1):
            cid = _uuid()
            choices.append({"id": cid, "position": idx, "item_body": _as_html(ans.get("text"))})
            if ans.get("is_correct"):
                correct_ids.append(cid)
        if not choices or not correct_ids:
            raise ValueError("multiple_answers_question requires at least one correct answer")

        item["entry"].update({
            "interaction_type_slug": "multi-answer",
            "interaction_data": {"choices": choices},
            "properties": (shuffle_props_choices if shuffle else {}),
            "scoring_algorithm": "PartialScore",  # or "AllOrNothing"
            "scoring_data": {"value": correct_ids}
        })
        return item

    if qtype == "true_false_question":
        # true-false + Equivalence
        # If GPT provided answers, read which is correct; else default False
        correct_val = None
        answers = q.get("answers") or []
        for a in answers:
            t = (a.get("text") or "").strip().lower()
            if a.get("is_correct") and t in ("true", "false"):
                correct_val = (t == "true")
        if correct_val is None:
            correct_val = False

        item["entry"].update({
            "interaction_type_slug": "true-false",
            "interaction_data": {"true_choice": "True", "false_choice": "False"},
            "properties": {},
            "scoring_algorithm": "Equivalence",
            "scoring_data": {"value": bool(correct_val)}
        })
        return item

    if qtype == "essay_question":
        # essay + None
        grading_note = fb.get("neutral") or ""
        item["entry"].update({
            "interaction_type_slug": "essay",
            "interaction_data": {
                "rce": True,
                "essay": None,
                "word_count": True,
                "file_upload": False,
                "spell_check": True,
            },
            "properties": {},
            "scoring_algorithm": "None",
            "scoring_data": {"value": grading_note}
        })
        return item

    if qtype == "short_answer_question":
        # Map to rich-fill-blank with one openEntry blank
        # Accept all provided answers as equivalents (if multiple, TextInChoices)
        answers = [a.get("text") for a in (q.get("answers") or []) if (a.get("text") or "").strip()]
        if not answers:
            raise ValueError("short_answer_question requires at least one acceptable answer")

        blank_id = _uuid()
        scoring_alg = "TextEquivalence" if len(answers) == 1 else "TextInChoices"
        scoring_value = answers[0] if len(answers) == 1 else answers

        item["entry"].update({
            "interaction_type_slug": "rich-fill-blank",
            "interaction_data": {
                "blanks": [{"id": blank_id, "answer_type": "openEntry"}],
                "reuse_word_bank_choices": False
            },
            "properties": {},
            "scoring_algorithm": "MultipleMethods",
            "scoring_data": {
                "value": [{
                    "id": blank_id,
                    "scoring_data": {
                        "value": scoring_value,
                        "blank_text": answers[0],
                        "ignore_case": True
                    },
                    "scoring_algorithm": scoring_alg
                }],
                # working_item_body uses backticks to mark blanks—use a neutral placeholder
                "working_item_body": "<p>`_____`</p>"
            }
        })
        return item

    if qtype == "fill_in_multiple_blanks_question":
        # Map {{blank_id}} markers to multiple openEntry blanks
        # q["answers"] like: [{"blank_id":"b1","text":"2"}, {"blank_id":"b2","text":"water"}]
        stem = _as_html(q.get("question_text"))
        answers_raw = [a for a in (q.get("answers") or []) if a.get("blank_id")]
        if not answers_raw:
            raise ValueError("fill_in_multiple_blanks_question requires answers with blank_id")

        # Group acceptable answers per blank_id
        per_blank: Dict[str, List[str]] = {}
        for a in answers_raw:
            per_blank.setdefault(a["blank_id"], []).append(a.get("text") or "")

        # Create stable UUID per blank_id
        blank_uuid_map = {bid: _uuid() for bid in per_blank.keys()}
        blanks = [{"id": blank_uuid_map[bid], "answer_type": "openEntry"} for bid in per_blank.keys()]

        scoring_value_list = []
        # Create 'working_item_body' by replacing {{b}} with backticked first answer
        working_body = stem
        for bid, vals in per_blank.items():
            first = (vals[0] if vals else "_____")
            working_body = working_body.replace("{{" + bid + "}}", f"`{first}`")
            scoring_alg = "TextEquivalence" if len(vals) == 1 else "TextInChoices"
            scoring_value_list.append({
                "id": blank_uuid_map[bid],
                "scoring_data": {
                    "value": (vals[0] if len(vals) == 1 else vals),
                    "blank_text": first,
                    "ignore_case": True
                },
                "scoring_algorithm": scoring_alg
            })

        item["entry"].update({
            "interaction_type_slug": "rich-fill-blank",
            "interaction_data": {
                "blanks": blanks,
                "reuse_word_bank_choices": False
            },
            "properties": {},
            "scoring_algorithm": "MultipleMethods",
            "scoring_data": {
                "value": scoring_value_list,
                "working_item_body": working_body
            }
        })
        return item

    if qtype == "matching_question":
        # matching + PartialDeep (or DeepEquals)
        # input: matches: [{"prompt":"H2O","match":"water"}, ...]
        pairs = [m for m in (q.get("matches") or []) if m.get("prompt") and m.get("match")]
        if not pairs:
            raise ValueError("matching_question requires 'matches' with prompt+match")

        # Right-side answer options must be a list of strings that includes all correct answers.
        right_answers = list({m["match"] for m in pairs})
        # Left-side questions each need an id & item_body
        questions = [{"id": str(i + 1), "item_body": m["prompt"]} for i, m in enumerate(pairs)]

        # Build correct_matches using the question ids
        correct_matches = []
        for qobj, m in zip(questions, pairs):
            correct_matches.append({
                "question_id": qobj["id"],
                "question_body": qobj["item_body"],
                "answer_body": m["match"]
            })

        item["entry"].update({
            "interaction_type_slug": "matching",
            "interaction_data": {
                "answers": right_answers,
                "questions": questions
            },
            "properties": {},
            "scoring_algorithm": "PartialDeep",  # allows partial credit
            "scoring_data": {
                "value": {
                    "correct_matches": correct_matches,
                    "distractors": []  # you can add wrong options here if you want
                }
            }
        })
        return item

    if qtype == "numerical_question":
        # numeric + Numeric
        num = (q.get("numerical_answer") or {})
        exact = num.get("exact")
        tol = num.get("tolerance")
        if exact is None:
            raise ValueError("numerical_question requires numerical_answer.exact")

        # Minimal numeric: one preciseResponse with optional precision; you can
        # also build 'numeric' type answers as shown in docs, but this is enough.
        responses = [{
            "id": _uuid(),
            "type": "preciseResponse",
            "value": str(exact),
            # If you want grading precision, set decimals:
            "precision": "0",
            "precision_type": "decimals"
        }]

        item["entry"].update({
            "interaction_type_slug": "numeric",
            "interaction_data": {"responses": responses},
            "properties": {},
            "scoring_algorithm": "Numeric",
            "scoring_data": {"responses": responses}
        })
        return item

    # If we got here, type wasn't mapped
    raise ValueError(f"Unsupported question_type: {qtype}")
