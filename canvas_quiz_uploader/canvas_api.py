# canvas_api.py
import requests
from typing import Optional, Dict, Any

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def _extract_assignment_id(data: Dict[str, Any]) -> Optional[int]:
    # Handle common response shapes from different Canvas tenants/gateways
    if not isinstance(data, dict):
        return None
    return (
        data.get("assignment_id")
        or (data.get("quiz") or {}).get("assignment_id")
        or (data.get("data") or {}).get("assignment_id")
        or (data.get("result") or {}).get("assignment_id")
    )

def _find_assignment_id_for_new_quiz(domain: str, course_id: str, title: str, token: str) -> Optional[int]:
    """
    Fallback: search Assignments for a likely New Quizzes item matching the title.
    Heuristics:
      - submission_types contains "external_tool"
      - external_tool_tag_attributes URL often contains 'quizzes'/'quizzes.next'/'new_quiz'
      - if no URL hint, fall back to exact title match, newest first
    """
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments"
    params = {"search_term": title, "per_page": 100}
    r = requests.get(url, headers=H(token), params=params, timeout=60)
    if r.status_code != 200:
        return None
    items = r.json() if isinstance(r.json(), list) else []
    # First pass: external tool + quizzes-ish URL
    candidates = []
    for a in items:
        if "external_tool" in (a.get("submission_types") or []):
            ett = a.get("external_tool_tag_attributes") or {}
            url_hint = (ett.get("url") or "").lower()
            if any(k in url_hint for k in ["quizzes-next", "quizzes.next", "new_quiz", "quizzes"]):
                candidates.append(a)
    if candidates:
        candidates.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return candidates[0].get("id")

    # Second pass: exact title match (most recent)
    same_title = [a for a in items if (a.get("name") or "") == title]
    if same_title:
        same_title.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return same_title[0].get("id")

    return None

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str):
    """
    Create a New Quiz (LTI) shell via the New Quizzes API and return the assignment_id.
    POST /api/quiz/v1/courses/:course_id/quizzes

    Returns:
      {"assignment_id": <int>, "raw": <full response json>}
    Raises:
      RuntimeError on HTTP errors.
    """
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    payload = {
        "title": title,
        "description": description or "",
        "points_possible": 0
    }
    headers = {**H(token), "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=payload, timeout=60)

    if r.status_code not in (200, 201):
        # Surface body so you can see permission/feature flag errors in the UI
        raise RuntimeError(f"Create New Quiz failed: {r.status_code} | {r.text}")

    data = r.json()
    assignment_id = _extract_assignment_id(data)

    # Fallback to Assignments API if not present in the create response
    if not assignment_id:
        assignment_id = _find_assignment_id_for_new_quiz(domain, course_id, title, token)

    # Return shape expected by the Streamlit app
    return {"assignment_id": assignment_id, "raw": data}

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
    """
    POST /api/v1/courses/:course_id/modules/:module_id/items
    item_type for New Quizzes must be "Assignment" and ref_id is the assignment_id.
    """
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/modules/{module_id}/items"
    data = {
        "module_item[type]": item_type,
        "module_item[content_id]": ref_id,
        "module_item[title]": title,
        "module_item[indent]": 0,
        "module_item[published]": True
    }
    r = requests.post(url, headers=H(token), data=data, timeout=60)
    return r.status_code in (200, 201)
