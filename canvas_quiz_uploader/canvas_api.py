# canvas_api.py
from typing import Optional, Dict, Any, Tuple
import json, requests

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def safe_body(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text

# ---------- New Quizzes (create quiz shell) ----------
# POST /api/quiz/v1/courses/:course_id/quizzes
# Returns an object containing assignment_id (the assignment backing the New Quiz).
# Ref: New Quizzes API → Create a new quiz. :contentReference[oaicite:1]{index=1}
def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    attempts = []

    # JSON first
    payload = {"title": title, "instructions": description or "", "points_possible": 0}
    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json={"quiz": payload}, timeout=60)
    attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})
    if r1.status_code in (200, 201):
        data = r1.json()
        return {
            "assignment_id": data.get("assignment_id") or (data.get("quiz") or {}).get("assignment_id"),
            "raw": data,
            "http_debug": {"attempts": attempts},
        }

    # Form fallback (some tenants)
    form = {
        "quiz[title]": title,
        "quiz[instructions]": description or "",
        "quiz[points_possible]": 0,
    }
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})
    if r2.status_code in (200, 201):
        data = r2.json()
        return {
            "assignment_id": data.get("assignment_id") or (data.get("quiz") or {}).get("assignment_id"),
            "raw": data,
            "http_debug": {"attempts": attempts},
        }

    return {"assignment_id": None, "raw": None, "http_debug": {"attempts": attempts}}

# ---------- Quiz Items CRUD ----------
# POST /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items
# PATCH /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items/:item_id
# GET   /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items
# Ref: New Quiz Items API. :contentReference[oaicite:2]{index=2}
def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str):
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    return requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=item_payload, timeout=60)

def update_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_id: str, item_payload: dict, token: str):
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/{item_id}"
    return requests.patch(url, headers={**H(token), "Content-Type": "application/json"}, json=item_payload, timeout=60)

def get_new_quiz_items(domain: str, course_id: str, assignment_id: str, token: str) -> Tuple[int, Any]:
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    r = requests.get(url, headers=H(token), timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

# ---------- Hot-Spot helper ----------
# GET /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items/media_upload_url
# Use to obtain a presigned URL for the hotspot image. :contentReference[oaicite:3]{index=3}
def get_items_media_upload_url(domain: str, course_id: str, assignment_id: str, token: str) -> Optional[str]:
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items/media_upload_url"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code == 200:
        try:
            return r.json().get("url")
        except Exception:
            return None
    return None

# ---------- (optional) publish assignment shell via classic Assignments API ----------
def publish_assignment(domain: str, course_id: str, assignment_id: int, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.put(url, headers=H(token), data={"assignment[published]": True}, timeout=60)
    return r.status_code in (200, 201)

def assignment_url(domain: str, course_id: str, assignment_id: int) -> str:
    return f"{BASE(domain)}/courses/{course_id}/assignments/{assignment_id}"
