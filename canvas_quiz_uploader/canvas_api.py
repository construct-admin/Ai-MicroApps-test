# canvas_api.py
from typing import Optional, Dict, Any
import requests

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

# ---------- helpers ----------

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
    """Fallback: search Assignments for a likely New Quiz matching the title."""
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments"
    params = {"search_term": title, "per_page": 100}
    r = requests.get(url, headers=H(token), params=params, timeout=60)
    if r.status_code != 200:
        return None
    items = r.json() if isinstance(r.json(), list) else []
    # Prefer External Tool assignments whose launch URL looks like New Quizzes
    candidates = []
    for a in items:
        if "external_tool" in (a.get("submission_types") or []):
            ett = a.get("external_tool_tag_attributes") or {}
            url_hint = (ett.get("url") or "").lower()
            if any(k in url_hint for k in ["quizzes-next", "quizzes.next", "new_quiz", "new-quizzes", "quizzes"]):
                candidates.append(a)
    if candidates:
        # newest first
        candidates.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return candidates[0].get("id")
    # else: exact title match, newest first
    same_title = [a for a in items if (a.get("name") or "") == title]
    if same_title:
        same_title.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return same_title[0].get("id")
    return None

def is_new_quizzes_enabled(domain: str, course_id: str, token: str) -> Optional[bool]:
    """Checks the course feature flags for New Quizzes."""
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/features/enabled"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code != 200:
        return None  # unknown
    flags = r.json() if isinstance(r.json(), list) else []
    known = {"quizzes_next", "quizzes.next", "new_quizzes"}
    return any(f in flags for f in known)

# ---------- main API you call from the app ----------

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    """
    Create a New Quiz shell and return:
      {
        "assignment_id": <int or None>,
        "raw": <create response or error body>,
        "http_debug": {"attempts":[...]}   # so you can see status/body of each attempt
      }
    Never raises; the caller can decide what to do if assignment_id is None.
    """
    http_attempts = []

    # Optional preflight: is New Quizzes enabled?
    enabled = is_new_quizzes_enabled(domain, course_id, token)
    if enabled is False:
        return {
            "assignment_id": None,
            "raw": {"error": "New Quizzes not enabled for this course/account."},
            "http_debug": {"preflight": "feature flag disabled"}
        }

    # 1) Try JSON payload
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    payload = {"title": title, "description": description or "", "points_possible": 0}
    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)
    http_attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})

    if r1.status_code in (200, 201):
        data = r1.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    # 2) Some tenants only accept form-encoded fields
    form = {"quiz[title]": title, "quiz[description]": description or "", "quiz[points_possible]": 0}
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    http_attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})

    if r2.status_code in (200, 201):
        data = r2.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    # 3) Hard failure — return details (don’t raise)
    return {
        "assignment_id": None,
        "raw": {"error": "Create New Quiz failed"},
        "http_debug": {"attempts": http_attempts}
    }

def safe_body(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        try:
            return r.text
        except Exception:
            return "<unreadable>"

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
