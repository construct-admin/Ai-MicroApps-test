# quizzes_new.py
# New Quizzes (LTI) helpers covering choice, true/false, short answer, essay,
# fill-in-multiple-blanks, matching, numerical. Sends question-level feedback
# and per-answer feedback where supported (choice-style).

API_SCHEMA_VERSION = "2025-09-21b"

import uuid
import requests


def _BASE(domain: str) -> str:
    return f"https://{domain}".rstrip("/")


def _H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────────────────
# Quiz shell
# ─────────────────────────────────────────────────────────────────────────────
def add_new_quiz(domain, course_id, title, description_html, token, points_possible=1):
    """
    Create a New Quiz (LTI).
    Returns: (assignment_id, err, status, raw_json_or_text)
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    payload = {
        "quiz": {
            "title": title,
            "points_possible": max(1, int(points_possible or 1)),
            "instructions": description_html or "",
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = None

    if r.status_code in (200, 201):
        aid = (data or {}).get("assignment_id") or (data or {}).get("id")
        return aid, None, r.status_code, (data or r.text)
    return None, (data or r.text), r.status_code, (data or r.text)


# ─────────────────────────────────────────────────────────────────────────────
# Choice (MCQ/MA/TF) — supports per-answer feedback + question-level feedback
# ─────────────────────────────────────────────────────────────────────────────
def _mc_scoring_for(answers):
    """
    Single-correct -> Equivalence
    Multi-correct  -> SetEquivalence  (array of choice ids)
    """
    correct = [a["_choice_id"] for a in answers if a.get("is_correct")]
    if len(correct) <= 1:
        return "Equivalence", (correct[0] if correct else None)
    return "SetEquivalence", correct


def add_choice_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: multiple_choice_question, multiple_answers_question, true_false_question
    Uses interaction_type_slug='choice'. Sends question-level + per-answer feedback.
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    answers = q.get("answers", []) or []
    if not answers:
        return False, "No answers provided."

    # Choices + per-answer feedback
    choices, answer_feedback = [], {}
    for idx, a in enumerate(answers, start=1):
        cid = a.get("_choice_id") or str(uuid.uuid4())
        a["_choice_id"] = cid
        choices.append(
            {
                "id": cid,
                "position": idx,
                "itemBody": f"<p>{a.get('text','')}</p>",
            }
        )
        if a.get("feedback"):
            answer_feedback[cid] = a["feedback"]

    scoring_algorithm, scoring_value = _mc_scoring_for(answers)

    entry = {
        "interaction_type_slug": "choice",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        "interaction_data": {"choices": choices},
        "properties": {
            "shuffleRules": {
                "choices": {"toLock": [], "shuffled": bool(q.get("shuffle", False))}
            },
            "varyPointsByAnswer": False,
        },
        "scoring_algorithm": scoring_algorithm,
        "scoring_data": {"value": scoring_value},
    }

    # Question-level feedback
    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    # Per-answer feedback (choice only)
    if answer_feedback:
        entry["answer_feedback"] = answer_feedback

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Short Answer — list of acceptable strings (exact/ci match)
# ─────────────────────────────────────────────────────────────────────────────
def add_short_answer_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: short_answer_question
    Acceptable answers come from q['answers'] = [{'text': '...' }, ...]
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    acceptable = [a.get("text", "") for a in (q.get("answers") or []) if a.get("text")]
    entry = {
        "interaction_type_slug": "short_answer",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        # Required for SA-type questions
        "user_response_type": "string",
        # Use Equivalence with an array of acceptable strings
        "scoring_algorithm": "Equivalence",
        "scoring_data": {"value": acceptable},
    }

    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }

    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Essay — instructor graded
# ─────────────────────────────────────────────────────────────────────────────
def add_essay_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: essay_question (manual grading)
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    entry = {
        "interaction_type_slug": "essay",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        # Required fields for essay
        "user_response_type": "text",
        "scoring_algorithm": "Manual",
        "scoring_data": {"value": []},
    }

    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Fill in multiple blanks — {{blank_id}} in item_body + mapping of answers
# ─────────────────────────────────────────────────────────────────────────────
def add_fimb_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: fill_in_multiple_blanks_question
    q['question_text'] should include {{blank_id}} placeholders.
    q['answers'] = [{'blank_id':'b1','text':'2'}, {'blank_id':'b2','text':'water'}, ...]
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    blanks_map = {}
    for a in (q.get("answers") or []):
        b = a.get("blank_id")
        t = a.get("text")
        if b and t:
            blanks_map.setdefault(b, []).append(t)

    entry = {
        "interaction_type_slug": "fill_in_multiple_blanks",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        # Required for FIMB
        "user_response_type": "string",
        # Each blank_id maps to acceptable strings
        "scoring_algorithm": "Equivalence",
        "scoring_data": {"value": blanks_map},
        "interaction_data": {"blanks": [{"id": k} for k in blanks_map.keys()]},
    }

    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Matching — stems (prompts) -> choices (matches)
# ─────────────────────────────────────────────────────────────────────────────
def add_matching_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: matching_question
    q['matches'] = [{'prompt':'H2O','match':'water'}, ...]
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    stems, choices, pairs = [], [], []
    # Build 1-1 mapping lists
    for idx, m in enumerate(q.get("matches", []) or [], start=1):
        sid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        stems.append({"id": sid, "position": idx, "itemBody": f"<p>{m.get('prompt','')}</p>"})
        choices.append({"id": cid, "position": idx, "itemBody": f"<p>{m.get('match','')}</p>"})
        pairs.append({"stem_id": sid, "choice_id": cid})

    entry = {
        "interaction_type_slug": "matching",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        "interaction_data": {"stems": stems, "choices": choices},
        # Scoring requires a `value` wrapper
        "scoring_algorithm": "Match",
        "scoring_data": {"value": {"pairs": pairs}},
    }

    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Numerical — exact w/ optional tolerance
# ─────────────────────────────────────────────────────────────────────────────
def add_numerical_item(domain, course_id, assignment_id, q, token, position=1):
    """
    Supports: numerical_question

    q['numerical_answer'] = {'exact': 12.5, 'tolerance': 0.5}  # tolerance optional
    """
    url = f"{_BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"

    na = q.get("numerical_answer") or {}
    exact = na.get("exact")
    tol = na.get("tolerance", 0)

    # API expects `scoring_data.value` to be an array of acceptable numeric answers
    val = {}
    if exact is not None:
        val["exact"] = exact
    if tol is not None:
        val["tolerance"] = tol

    entry = {
        "interaction_type_slug": "numeric",
        "title": q.get("question_name") or "Question",
        "item_body": q.get("question_text") or "",
        "calculator_type": "none",
        "scoring_algorithm": "Numeric",
        "scoring_data": {"value": [val]},
    }

    fb = (q.get("feedback") or {})
    qlevel = {k: v for k, v in fb.items() if v}
    if qlevel:
        entry["feedback"] = qlevel

    payload = {
        "item": {
            "entry_type": "Item",
            "points_possible": q.get("points_possible", 1),
            "position": position,
            "entry": entry,
        }
    }
    r = requests.post(url, headers=_H(token), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return True, None
    try:
        return False, r.json()
    except Exception:
        return False, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher (call the right builder per question_type)
# ─────────────────────────────────────────────────────────────────────────────
def add_item_for_question(domain, course_id, assignment_id, q, token, position=1):
    """
    Route by q['question_type'] and add the item.
    Returns: (ok: bool, debug: any)
    """
    qtype = (q.get("question_type") or "").strip()

    if qtype in (
        "multiple_choice_question",
        "multiple_answers_question",
        "true_false_question",
    ):
        return add_choice_item(domain, course_id, assignment_id, q, token, position=position)

    if qtype == "short_answer_question":
        return add_short_answer_item(domain, course_id, assignment_id, q, token, position=position)

    if qtype == "essay_question":
        return add_essay_item(domain, course_id, assignment_id, q, token, position=position)

    if qtype == "fill_in_multiple_blanks_question":
        return add_fimb_item(domain, course_id, assignment_id, q, token, position=position)

    if qtype == "matching_question":
        return add_matching_item(domain, course_id, assignment_id, q, token, position=position)

    if qtype == "numerical_question":
        return add_numerical_item(domain, course_id, assignment_id, q, token, position=position)

    return False, f"Unsupported question_type: {qtype}"
