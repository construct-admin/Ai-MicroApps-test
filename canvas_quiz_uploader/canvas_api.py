# canvas_api.py
from typing import Optional, Dict, Any, Tuple, List
import requests, json

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

# ---------- small helpers ----------

def safe_body(r: requests.Response):
    try:
        return r.json()
    except Exception:
        try:
            return r.text
        except Exception:
            return "<unreadable>"

def _extract_assignment_id(data: Dict[str, Any]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    return (
        data.get("assignment_id")
        or (data.get("quiz") or {}).get("assignment_id")
        or (data.get("data") or {}).get("assignment_id")
        or (data.get("result") or {}).get("assignment_id")
    )

def _find_assignment_id_for_new_quiz(domain: str, course_id: str, title: str, token: str) -> Optional[int]:
    """Fallback: scan Assignments to find the new-quizzes assignment id by title/launch url."""
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments"
    params = {"search_term": title, "per_page": 100}
    r = requests.get(url, headers=H(token), params=params, timeout=60)
    if r.status_code != 200:
        return None
    items = r.json() if isinstance(r.json(), list) else []
    # Prefer External Tool assignments that look like New Quizzes
    candidates: List[Dict[str, Any]] = []
    for a in items:
        if "external_tool" in (a.get("submission_types") or []):
            ett = a.get("external_tool_tag_attributes") or {}
            url_hint = (ett.get("url") or "").lower()
            if any(k in url_hint for k in ["quizzes-next", "quizzes.next", "new_quiz", "new-quizzes", "quizzes"]):
                candidates.append(a)
    if candidates:
        candidates.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return candidates[0].get("id")
    # else: exact title match, newest first
    same_title = [a for a in items if (a.get("name") or "") == title]
    if same_title:
        same_title.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return same_title[0].get("id")
    return None

def is_new_quizzes_enabled(domain: str, course_id: str, token: str) -> Optional[bool]:
    """Check course feature flags for New Quizzes. Returns True/False or None if unknown."""
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/features/enabled"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code != 200:
        return None
    flags = r.json() if isinstance(r.json(), list) else []
    known = {"quizzes_next", "quizzes.next", "new_quizzes"}
    return any(f in flags for f in known)

# ---------- quick token sanity (optional in UI) ----------

def whoami(domain: str, token: str) -> Tuple[int, Any]:
    """GET /api/v1/users/self to validate the token/account."""
    url = f"{BASE(domain)}/api/v1/users/self"
    r = requests.get(url, headers=H(token), timeout=30)
    try:
        data = r.json()
    except Exception:
        data = r.text
    return r.status_code, data

# ---------- New Quizzes: create shell quiz ----------

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    """
    Creates a New Quiz shell (Assignments + LTI launch) and returns:
      {
        "assignment_id": <int or None>,
        "raw": <create response>,
        "http_debug": {"attempts":[...] }
      }
    Tries JSON and form bodies; falls back to scanning assignments to resolve assignment_id.
    """
    http_attempts = []

    enabled = is_new_quizzes_enabled(domain, course_id, token)
    if enabled is False:
        return {
            "assignment_id": None,
            "raw": {"error": "New Quizzes feature disabled for this course."},
            "http_debug": {"preflight": "feature flag disabled"}
        }

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    payload = {"title": title, "description": description or "", "points_possible": 0}

    # 1) JSON body
    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)
    http_attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})
    if r1.status_code in (200, 201):
        data = r1.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    # 2) Form-encoded
    form = {"quiz[title]": title, "quiz[description]": description or "", "quiz[points_possible]": 0}
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    http_attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})
    if r2.status_code in (200, 201):
        data = r2.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    return {"assignment_id": None, "raw": {"error": "Create New Quiz failed"}, "http_debug": {"attempts": http_attempts}}

# ---------- Items ----------

def get_new_quiz_items(domain: str, course_id: str, assignment_id: int, token: str):
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    r = requests.get(url, headers=H(token), timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text}
    return r.status_code, data

def update_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, item_payload: dict, token: str):
    """PUT the item (no-op update to nudge refresh)."""
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    r = requests.put(url, headers=H(token), data={"item": json.dumps(item_payload["item"])}, timeout=60)
    return r

def delete_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, token: str) -> bool:
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    r = requests.delete(url, headers=H(token), timeout=60)
    return r.status_code in (200, 204)

def delete_all_new_quiz_items(domain: str, course_id: str, assignment_id: int, token: str) -> dict:
    status, data = get_new_quiz_items(domain, course_id, assignment_id, token)
    if status != 200 or not isinstance(data, list):
        return {"status": status, "deleted": 0, "error": "GET items failed"}
    deleted = 0
    for it in data:
        if delete_new_quiz_item(domain, course_id, assignment_id, it["id"], token):
            deleted += 1
    return {"status": 200, "deleted": deleted}

# ---------- Assignments / Modules convenience ----------

def publish_assignment(domain: str, course_id: str, assignment_id: int, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.put(url, headers=H(token), data={"assignment[published]": True}, timeout=60)
    return r.status_code in (200, 201)

def assignment_url(domain: str, course_id: str, assignment_id: int) -> str:
    return f"{BASE(domain)}/courses/{course_id}/assignments/{assignment_id}"

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/modules/{module_id}/items"
    data = {
        "module_item[type]": item_type,            # "Assignment" for New Quizzes
        "module_item[content_id]": ref_id,         # assignment_id
        "module_item[title]": title,
        "module_item[indent]": 0,
        "module_item[published]": True
    }
    r = requests.post(url, headers=H(token), data=data, timeout=60)
    return r.status_code in (200, 201)
