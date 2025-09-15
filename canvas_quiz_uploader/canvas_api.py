
import requests

def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str):
    """
    Uses the New Quizzes API to create a quiz shell.
    POST /api/quiz/v1/courses/:course_id/quizzes
    Returns JSON with at least {"assignment_id": <int>, ...} on success.
    """
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    data = {
        "quiz[title]": title,
        "quiz[description]": description,
        "quiz[points_possible]": 0
    }
    r = requests.post(url, headers=H(token), data=data, timeout=60)
    if r.status_code not in (200, 201):
        return None
    return r.json()

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
    """
    POST /api/v1/courses/:course_id/modules/:module_id/items
    module_item[type] ∈ {"Page","Assignment","Discussion","Quiz","ExternalUrl","File"}
    For New Quizzes, item_type="Assignment" and ref_id = assignment_id
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
