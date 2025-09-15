# canvas_api.py
from typing import Optional, Dict, Any, Tuple
import requests, json

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def safe_body(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        try:
            return r.text
        except Exception:
            return "<unreadable>"

def is_new_quizzes_enabled(domain: str, course_id: str, token: str) -> Optional[bool]:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/features/enabled"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code != 200:
        return None
    try:
        flags = r.json()
    except Exception:
        return None
    if not isinstance(flags, list):
        return None
    known = {"quizzes_next", "quizzes.next", "new_quizzes"}
    return any(f in flags for f in known)

# ---------- Create New Quiz shell (assignment-backed) ----------
def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    attempts = []
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"

    payload = {"title": title, "description": description or "", "points_possible": 0}
    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)
    attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})
    if r1.status_code in (200, 201):
        data = r1.json()
        aid = data.get("assignment_id") or (data.get("quiz") or {}).get("assignment_id")
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": attempts}}

    form = {"quiz[title]": title, "quiz[description]": description or "", "quiz[points_possible]": 0}
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})
    if r2.status_code in (200, 201):
        data = r2.json()
        aid = data.get("assignment_id") or (data.get("quiz") or {}).get("assignment_id")
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": attempts}}

    return {"assignment_id": None, "raw": None, "http_debug": {"attempts": attempts}}

# ---------- Items API helpers ----------
def get_new_quiz_items(domain: str, course_id: str, assignment_id: int, token: str) -> Tuple[int, Any]:
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    r = requests.get(url, headers=H(token), timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def update_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, item_payload: dict, token: str):
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    r = requests.put(url, headers=H(token), data={"item": json.dumps(item_payload["item"])}, timeout=60)
    return r

def publish_assignment(domain: str, course_id: str, assignment_id: int, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.put(url, headers=H(token), data={"assignment[published]": True}, timeout=60)
    return r.status_code in (200, 201)

def assignment_url(domain: str, course_id: str, assignment_id: int) -> str:
    return f"{BASE(domain)}/courses/{course_id}/assignments/{assignment_id}"

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/modules/{module_id}/items"
    data = {
        "module_item[type]": item_type,            # 'Assignment'
        "module_item[content_id]": ref_id,         # assignment_id
        "module_item[title]": title,
        "module_item[indent]": 0,
        "module_item[published]": True
    }
    r = requests.post(url, headers=H(token), data=data, timeout=60)
    return r.status_code in (200, 201)
