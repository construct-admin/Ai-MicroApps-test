# canvas_api.py
from typing import Optional, Dict, Any, Tuple
import requests
import json

# -------------------------
# Basic helpers
# -------------------------

def BASE(domain: str) -> str:
    """Return a fully-qualified Canvas base URL for the given domain."""
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    """Sanitize and return auth header."""
    t = (token or "").strip()
    return {"Authorization": f"Bearer {t}"}

def safe_body(r: requests.Response) -> Any:
    """Return JSON body if possible, else text, else placeholder."""
    try:
        return r.json()
    except Exception:
        try:
            return r.text
        except Exception:
            return "<unreadable>"

# -------------------------
# Token sanity check
# -------------------------

def whoami(domain: str, token: str) -> Tuple[int, Any]:
    """GET /users/self to validate the token and show the user it resolves to."""
    url = f"{BASE(domain)}/api/v1/users/self"
    r = requests.get(url, headers=H(token), timeout=30)
    return r.status_code, safe_body(r)

# -------------------------
# Internal helpers
# -------------------------

def _extract_assignment_id(data: Dict[str, Any]) -> Optional[int]:
    """Pick the assignment_id out of several possible response shapes."""
    if not isinstance(data, dict):
        return None
    return (
        data.get("assignment_id")
        or (data.get("quiz") or {}).get("assignment_id")
        or (data.get("data") or {}).get("assignment_id")
        or (data.get("result") or {}).get("assignment_id")
    )

def _resolve_assignment_id_from_quiz_id(domain: str, course_id: str, quiz_id: str, token: str) -> Optional[int]:
    """
    GET the quiz details and pull assignment_id if the create response didn’t include it.
    /api/quiz/v1/courses/:course_id/quizzes/:quiz_id
    """
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code not in (200, 201):
        return None
    try:
        data = r.json()
    except Exception:
        return None
    return _extract_assignment_id(data) or data.get("assignment_id")

def _find_assignment_id_for_new_quiz(domain: str, course_id: str, title: str, token: str) -> Optional[int]:
    """
    Fallback: search Assignments for a likely New Quiz matching the title.
    Prefers external_tool assignments pointing to New Quizzes.
    """
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments"
    params = {"search_term": title, "per_page": 100}
    r = requests.get(url, headers=H(token), params=params, timeout=60)
    if r.status_code != 200:
        return None
    try:
        items = r.json()
    except Exception:
        return None
    if not isinstance(items, list):
        return None

    candidates = []
    for a in items:
        if "external_tool" in (a.get("submission_types") or []):
            ett = a.get("external_tool_tag_attributes") or {}
            url_hint = (ett.get("url") or "").lower()
            if any(k in url_hint for k in ["quizzes-next", "quizzes.next", "new_quiz", "new-quizzes", "quizzes"]):
                candidates.append(a)

    if candidates:
        candidates.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return candidates[0].get("id")

    same_title = [a for a in items if (a.get("name") or "") == title]
    if same_title:
        same_title.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return same_title[0].get("id")

    return None

# -------------------------
# Create New Quiz (assignment-backed)
# -------------------------

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    """
    Create a New Quiz shell and return:
      {
        "assignment_id": <int or None>,
        "raw": <create response body or None>,
        "http_debug": {"attempts":[...]}   # statuses/bodies for troubleshooting
      }
    This function never raises; the caller can decide what to do if assignment_id is None.
    """
    attempts = []
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"

    # 1) JSON attempt — must be wrapped in top-level "quiz"
    json_payload = {"quiz": {"title": title, "instructions": description or "", "points_possible": 0}}
    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=json_payload, timeout=60)
    attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})

    if r1.status_code in (200, 201):
        data = r1.json()
        aid = _extract_assignment_id(data)
        if not aid:
            quiz_id = (data.get("quiz") or {}).get("id") or data.get("id")
            if quiz_id:
                aid = _resolve_assignment_id_from_quiz_id(domain, course_id, str(quiz_id), token)
        if not aid:
            aid = _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": attempts}}

    # 2) FORM fallback
    form = {"quiz[title]": title, "quiz[instructions]": description or "", "quiz[points_possible]": 0}
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})

    if r2.status_code in (200, 201):
        data = r2.json()
        aid = _extract_assignment_id(data)
        if not aid:
            quiz_id = (data.get("quiz") or {}).get("id") or data.get("id")
            if quiz_id:
                aid = _resolve_assignment_id_from_quiz_id(domain, course_id, str(quiz_id), token)
        if not aid:
            aid = _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": attempts}}

    # 3) Hard failure
    return {"assignment_id": None, "raw": None, "http_debug": {"attempts": attempts}}

# -------------------------
# New Quiz Items API
# -------------------------

def get_new_quiz_items(domain: str, course_id: str, assignment_id: int, token: str) -> Tuple[int, Any]:
    """GET the list of items for a New Quiz assignment."""
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    r = requests.get(url, headers=H(token), timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def update_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, item_payload: dict, token: str):
    """
    PUT the item back to the Items API (useful to force a content refresh).
    item_payload must be shaped as {"item": {...}}.
    """
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    r = requests.put(url, headers=H(token), data={"item": json.dumps(item_payload["item"])}, timeout=60)
    return r

def delete_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, token: str):
    """DELETE one New Quiz item (useful when a partial/bad item makes Build spin)."""
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    return requests.delete(url, headers=H(token), timeout=60)

# -------------------------
# Assignments API helpers (publish, link, modules)
# -------------------------

def publish_assignment(domain: str, course_id: str, assignment_id: int, token: str) -> bool:
    """Publish the assignment shell so it’s immediately visible."""
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.put(url, headers=H(token), data={"assignment[published]": True}, timeout=60)
    return r.status_code in (200, 201)

def assignment_url(domain: str, course_id: str, assignment_id: int) -> str:
    """Return a direct URL for the assignment in Canvas."""
    return f"{BASE(domain)}/courses/{course_id}/assignments/{assignment_id}"

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
    """
    Add an item (e.g., the New Quiz assignment) to a given module.
    item_type: usually "Assignment" for New Quizzes
    ref_id:    the assignment_id
    """
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/modules/{module_id}/items"
    data = {
        "module_item[type]": item_type,            # "Assignment" for New Quizzes
        "module_item[content_id]": ref_id,         # assignment_id
        "module_item[title]": title,
        "module_item[indent]": 0,
        "module_item[published]": True,
    }
    r = requests.post(url, headers=H(token), data=data, timeout=60)
    return r.status_code in (200, 201)
