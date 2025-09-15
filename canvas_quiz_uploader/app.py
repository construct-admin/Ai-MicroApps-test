# app.py — one-file New Quizzes uploader (no external local imports)
import json, re, time, uuid, sys, pathlib
from typing import Dict, Any, List, Tuple, Optional
import requests
import streamlit as st

# -----------------------------
# Canvas HTTP helpers
# -----------------------------
def BASE(domain: str) -> str:
    return f"https://{domain}" if not domain.startswith("http") else domain

def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def safe_body(r: requests.Response):
    try:
        return r.json()
    except Exception:
        try:
            return r.text
        except Exception:
            return "<unreadable>"

# -----------------------------
# Canvas API: whoami / feature flag
# -----------------------------
def whoami(domain: str, token: str):
    url = f"{BASE(domain)}/api/v1/users/self"
    r = requests.get(url, headers=H(token), timeout=30)
    try:
        data = r.json()
    except Exception:
        data = r.text
    return r.status_code, data

def is_new_quizzes_enabled(domain: str, course_id: str, token: str) -> Optional[bool]:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/features/enabled"
    r = requests.get(url, headers=H(token), timeout=60)
    if r.status_code != 200:
        return None
    flags = r.json() if isinstance(r.json(), list) else []
    known = {"quizzes_next", "quizzes.next", "new_quizzes"}
    return any(f in flags for f in known)

# -----------------------------
# Create New Quiz (shell)
# -----------------------------
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
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments"
    params = {"search_term": title, "per_page": 100}
    r = requests.get(url, headers=H(token), params=params, timeout=60)
    if r.status_code != 200:
        return None
    items = r.json() if isinstance(r.json(), list) else []
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

def create_new_quiz(domain: str, course_id: str, title: str, description: str, token: str) -> Dict[str, Any]:
    http_attempts = []
    enabled = is_new_quizzes_enabled(domain, course_id, token)
    if enabled is False:
        return {"assignment_id": None, "raw": {"error": "New Quizzes disabled"}, "http_debug": {"preflight": "feature flag disabled"}}

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes"
    payload = {"title": title, "description": description or "", "points_possible": 0}

    r1 = requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json=payload, timeout=60)
    http_attempts.append({"where": "json", "status": r1.status_code, "body": safe_body(r1)})
    if r1.status_code in (200, 201):
        data = r1.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    form = {"quiz[title]": title, "quiz[description]": description or "", "quiz[points_possible]": 0}
    r2 = requests.post(url, headers=H(token), data=form, timeout=60)
    http_attempts.append({"where": "form", "status": r2.status_code, "body": safe_body(r2)})
    if r2.status_code in (200, 201):
        data = r2.json()
        aid = _extract_assignment_id(data) or _find_assignment_id_for_new_quiz(domain, course_id, title, token)
        return {"assignment_id": aid, "raw": data, "http_debug": {"attempts": http_attempts}}

    return {"assignment_id": None, "raw": {"error": "Create New Quiz failed"}, "http_debug": {"attempts": http_attempts}}

# -----------------------------
# Items API (get / put / delete)
# -----------------------------
def get_new_quiz_items(domain: str, course_id: str, assignment_id: int, token: str):
    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    r = requests.get(url, headers=H(token), timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text}
    return r.status_code, data

def update_new_quiz_item(domain: str, course_id: str, assignment_id: int, item_id: str, item_payload: dict, token: str):
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

# -----------------------------
# Publish & modules convenience
# -----------------------------
def publish_assignment(domain: str, course_id: str, assignment_id: int, token: str) -> bool:
    url = f"{BASE(domain)}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.put(url, headers=H(token), data={"assignment[published]": True}, timeout=60)
    return r.status_code in (200, 201)

def assignment_url(domain: str, course_id: str, assignment_id: int) -> str:
    return f"{BASE(domain)}/courses/{course_id}/assignments/{assignment_id}"

def add_to_module(domain: str, course_id: str, module_id: str, item_type: str, ref_id: str, title: str, token: str) -> bool:
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

# -----------------------------
# New Quiz Items: builder + poster (with MC/MA hardening)
# -----------------------------
def _uuid() -> str:
    return str(uuid.uuid4())

SUPPORTED_TYPES = [
    "multiple_choice","multiple_answer","true_false","fill_in_blank",
    "short_answer","essay","numeric","matching","ordering","categorization",
    "file_upload","hot_spot","formula"
]

def _label(s: str) -> Dict[str, str]:
    s = (s or "").strip()
    return {"text": s, "item_body": s}

def _extract_paragraph_texts(html: str) -> List[str]:
    if not html:
        return []
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    out = []
    for p in paras:
        txt = re.sub(r"(?s)<[^>]+>", "", p).strip()
        if txt:
            out.append(txt)
    return out

def _split_prompt_and_inline_options(prompt_html: str) -> Tuple[str, List[str]]:
    paras = _extract_paragraph_texts(prompt_html)
    if not paras:
        return prompt_html or "", []
    q_text = paras[0]
    opts = []
    for raw in paras[1:]:
        s = raw.lstrip("*").strip()
        s = s.split("  ", 1)[0].strip() if "  " in s else s
        if s:
            opts.append(s)
    clean_prompt = f"<p>{q_text}</p>"
    return clean_prompt, opts

def _ensure_min_choices_for_mc(entry: Dict[str, Any]) -> None:
    ia = entry.get("interaction_data") or {}
    choices = ia.get("choices") or []
    clean_prompt, inline_opts = _split_prompt_and_inline_options(entry.get("item_body") or "")
    if len(choices) < 2 and inline_opts:
        existing = {(c.get("text") or "").strip() for c in choices if c.get("text")}
        for opt in inline_opts:
            if opt and opt not in existing:
                choices.append({"id": _uuid(), **_label(opt)})
        entry["item_body"] = clean_prompt
    while len(choices) < 2:
        tag = f"Option {len(choices)+1}"
        choices.append({"id": _uuid(), **_label(tag)})
    ia["choices"] = choices
    entry["interaction_data"] = ia
    ids = [c["id"] for c in choices]
    val = ((entry.get("scoring_data") or {}).get("value"))
    if val not in ids:
        entry["scoring_data"] = {"value": ids[0]}

def _ensure_min_choices_for_ma(entry: Dict[str, Any]) -> None:
    ia = entry.get("interaction_data") or {}
    choices = ia.get("choices") or []
    clean_prompt, inline_opts = _split_prompt_and_inline_options(entry.get("item_body") or "")
    if len(choices) < 2 and inline_opts:
        existing = {(c.get("text") or "").strip() for c in choices if c.get("text")}
        for opt in inline_opts:
            if opt and opt not in existing:
                choices.append({"id": _uuid(), **_label(opt)})
        entry["item_body"] = clean_prompt
    while len(choices) < 2:
        tag = f"Option {len(choices)+1}"
        choices.append({"id": _uuid(), **_label(tag)})
    ia["choices"] = choices
    entry["interaction_data"] = ia
    ids = {c["id"] for c in choices}
    val = ((entry.get("scoring_data") or {}).get("value")) or []
    val = [v for v in val if v in ids]
    entry["scoring_data"] = {"value": val}

class NewQuizItemBuilder:
    def build_item(self, q: Dict[str, Any]) -> Dict[str, Any]:
        t = (q.get("type") or "").lower().strip()
        item = {
            "position": None,
            "points_possible": float(q.get("points", 1)),
            "entry_type": "Item",
            "entry": {
                "title": q.get("title") or (q.get("name") or ""),
                "item_body": q.get("prompt_html") or q.get("prompt") or "",
                "calculator_type": "none",
                "interaction_type_slug": None,
                "interaction_data": None,
                "properties": {},
                "scoring_data": None,
                "scoring_algorithm": None,
                "feedback": {k: v for k, v in (q.get("feedback") or {}).items() if v},
                "answer_feedback": None,
            }
        }

        if t == "multiple_choice":
            choices, correct_id, per_ans_fb = [], None, {}
            for ans in (q.get("answers") or []):
                label = (ans.get("text") or "").strip()
                if not label: continue
                cid = _uuid()
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"): correct_id = cid
                if ans.get("feedback_html"): per_ans_fb[cid] = ans["feedback_html"]
            item["entry"]["interaction_type_slug"] = "choice"
            item["entry"]["interaction_data"] = {"choices": choices, "shuffle_answers": bool(q.get("shuffle", True))}
            item["entry"]["properties"] = {
                "shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}},
                "vary_points_by_answer": False
            }
            item["entry"]["scoring_data"] = {"value": correct_id}
            item["entry"]["scoring_algorithm"] = "Equivalence"
            item["entry"]["answer_feedback"] = per_ans_fb or None
            _ensure_min_choices_for_mc(item["entry"])

        elif t == "multiple_answer":
            choices, correct_ids = [], []
            for ans in (q.get("answers") or []):
                label = (ans.get("text") or "").strip()
                if not label: continue
                cid = _uuid()
                choices.append({"id": cid, **_label(label)})
                if ans.get("is_correct"): correct_ids.append(cid)
            item["entry"]["interaction_type_slug"] = "multi-answer"
            item["entry"]["interaction_data"] = {"choices": choices, "shuffle_answers": bool(q.get("shuffle", True))}
            item["entry"]["properties"] = {"shuffle_rules": {"choices": {"shuffled": bool(q.get("shuffle", True))}}}
            item["entry"]["scoring_data"] = {"value": correct_ids}
            item["entry"]["scoring_algorithm"] = "PartialScore"
            _ensure_min_choices_for_ma(item["entry"])

        elif t == "true_false":
            item["entry"]["interaction_type_slug"] = "true-false"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": bool(q.get("correct"))}
            item["entry"]["scoring_algorithm"] = "Equivalence"

        elif t == "fill_in_blank":
            blanks = q.get("blanks") or []
            twb = q.get("text_with_blanks") or q.get("prompt_html") or q.get("prompt") or ""
            if not blanks:
                twb = twb + " {{b1}}"
                answers = [a.get("text") for a in (q.get("answers") or []) if a.get("text")]
                blanks = [{"id": "b1", "correct": answers}]
            blanks_map = {b["id"]: [{"id": _uuid(), **_label(v)} for v in (b.get("correct") or [])] for b in blanks}
            item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            item["entry"]["interaction_data"] = {"text_with_blanks": twb, "blanks": blanks_map}
            item["entry"]["scoring_data"] = {
                "value": {"blank_to_correct_answer_ids": {bid: [a["id"] for a in alts] for bid, alts in blanks_map.items()}}
            }
            item["entry"]["scoring_algorithm"] = "MultipleMethods"

        elif t == "short_answer":
            answers = [a.get("text", "") for a in (q.get("answers") or []) if a.get("text")]
            twb = (q.get("prompt_html") or q.get("prompt") or "") + " {{b1}}"
            alts = [{"id": _uuid(), **_label(s)} for s in answers]
            item["entry"]["interaction_type_slug"] = "rich-fill-blank"
            item["entry"]["interaction_data"] = {"text_with_blanks": twb, "blanks": {"b1": alts}}
            item["entry"]["scoring_data"] = {"value": {"blank_to_correct_answer_ids": {"b1": [a["id"] for a in alts]}}}
            item["entry"]["scoring_algorithm"] = "MultipleMethods"

        elif t == "essay":
            item["entry"]["interaction_type_slug"] = "essay"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        elif t == "numeric":
            spec = q.get("numeric") or {}
            exact = spec.get("exact")
            tol = float(spec.get("tolerance", 0) or 0)
            item["entry"]["interaction_type_slug"] = "numeric"
            item["entry"]["interaction_data"] = {}
            if exact is not None and tol > 0:
                item["entry"]["scoring_data"] = {"value": [{
                    "id": _uuid(), "type": "marginOfError", "value": str(exact), "margin": str(tol), "margin_type": "absolute"
                }]}
            else:
                item["entry"]["scoring_data"] = {"value": [{
                    "id": _uuid(), "type": "exactResponse", "value": str(exact if exact is not None else "")
                }]}
            item["entry"]["scoring_algorithm"] = "Numeric"

        elif t == "matching":
            right_ids, choices, prompts = {}, [], []
            for pair in (q.get("pairs") or []):
                right = pair["match"]
                rcid = right_ids.get(right)
                if not rcid:
                    rcid = _uuid()
                    right_ids[right] = rcid
                    choices.append({"id": rcid, **_label(right)})
                prompts.append({"id": _uuid(), **_label(pair["prompt"]), "answer_choice_id": rcid})
            item["entry"]["interaction_type_slug"] = "matching"
            item["entry"]["interaction_data"] = {"choices": choices, "prompts": prompts}
            item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}
            item["entry"]["scoring_data"] = {"value": {p["id"]: p["answer_choice_id"] for p in prompts}}
            item["entry"]["scoring_algorithm"] = "DeepEquals"

        elif t == "ordering":
            items = [{"id": _uuid(), **_label(x)} for x in (q.get("order") or [])]
            item["entry"]["interaction_type_slug"] = "ordering"
            item["entry"]["interaction_data"] = {"choices": items}
            item["entry"]["scoring_data"] = {"value": [c["id"] for c in items]}
            item["entry"]["scoring_algorithm"] = "DeepEquals"

        elif t == "categorization":
            src = q.get("categories", []) or []
            categories, by_name = [], {}
            for cat in src:
                cid = _uuid()
                by_name[cat["name"]] = cid
                categories.append({"id": cid, **_label(cat["name"])})
            choices = []
            for cat in src:
                cid = by_name[cat["name"]]
                for label in (cat.get("items") or []):
                    choice_id = _uuid()
                    choices.append({"id": choice_id, **_label(label), "category_id": cid})
            item["entry"]["interaction_type_slug"] = "categorization"
            item["entry"]["interaction_data"] = {"categories": categories, "choices": choices}
            item["entry"]["scoring_data"] = {"value": {c["id"]: c["category_id"] for c in choices}}
            item["entry"]["scoring_algorithm"] = "Categorization"
            item["entry"]["properties"] = {"shuffle_rules": {"questions": {"shuffled": False}}}

        elif t == "file_upload":
            item["entry"]["interaction_type_slug"] = "file-upload"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": None}
            item["entry"]["scoring_algorithm"] = "None"

        elif t == "hot_spot":
            item["entry"]["interaction_type_slug"] = "hot-spot"
            item["entry"]["interaction_data"] = {
                "image": q.get("hotspot_image") or {"url": q.get("image_url")},
                "hotspots": q.get("hotspots", [])
            }
            item["entry"]["scoring_data"] = {"value": [hs.get("id") for hs in q.get("hotspots", [])]}
            item["entry"]["scoring_algorithm"] = "HotSpot"

        elif t == "formula":
            item["entry"]["interaction_type_slug"] = "formula"
            item["entry"]["interaction_data"] = {}
            item["entry"]["scoring_data"] = {"value": []}
            item["entry"]["scoring_algorithm"] = "Numeric"

        else:
            raise ValueError(f"Unsupported question type: {t}")

        return {"item": item}

def _post_form(url: str, token: str, payload: dict):
    return requests.post(url, headers=H(token), data={"item": json.dumps(payload["item"])}, timeout=60)

def _post_json(url: str, token: str, payload: dict):
    return requests.post(url, headers={**H(token), "Content-Type": "application/json"}, json={"item": payload["item"]}, timeout=60)

def post_new_quiz_item(domain: str, course_id: str, assignment_id: str, item_payload: dict, token: str, position=None):
    if position is not None:
        item_payload["item"]["position"] = int(position)
    # final preflight hardening for MC/MA
    try:
        slug = (item_payload["item"]["entry"]["interaction_type_slug"] or "").strip()
        if slug == "choice":
            _ensure_min_choices_for_mc(item_payload["item"]["entry"])
        elif slug == "multi-answer":
            _ensure_min_choices_for_ma(item_payload["item"]["entry"])
    except Exception:
        pass

    url = f"{BASE(domain)}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items"
    delays = [1, 2, 4, 6]
    for d in [0] + delays:
        if d: time.sleep(d)
        r = _post_form(url, token, item_payload)
        if r.status_code in (200, 201): return r
        if 500 <= r.status_code < 600: continue
        r2 = _post_json(url, token, item_payload)
        if r2.status_code in (200, 201): return r2
        if 500 <= r2.status_code < 600: continue
        return r2
    return r

# -----------------------------
# Minimal storyboard loader
# -----------------------------
def load_storyboard_text(uploaded) -> str:
    name = getattr(uploaded, "name", "") or ""
    data = uploaded.read()
    if name.lower().endswith(".docx"):
        try:
            import docx  # python-docx
            doc = docx.Document(uploaded)
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            # fallback to bytes decode
            return data.decode("utf-8", errors="ignore")
    # .txt
    try:
        return data.decode("utf-8")
    except Exception:
        return data.decode("latin-1", errors="ignore")

# -----------------------------
# Very small fallback parser (uses your tag style); if you already have a
# richer quiz_tag_parser in your repo, you can ignore this and paste
# your own logic here.
# -----------------------------
def parse_quiz_block(text: str) -> Dict[str, Any]:
    # This covers MC, True/False, Short Answer, Numeric, Matching, Ordering, Categorization, FIB (basic)
    qs: List[Dict[str, Any]] = []
    blocks = re.findall(r"(?is)<question>(.*?)</question>", text)
    for idx, b in enumerate(blocks, start=1):
        b_low = b.lower()
        def has(tag): return f"<{tag}>" in b_low
        q: Dict[str, Any] = {"title": f"Question {idx}", "points": 1}

        # Multiple choice / multiple answer
        if "<multiple_answer>" in b_low or "<multiple answers>" in b_low:
            q["type"] = "multiple_answer"
            q["prompt_html"] = extract_prompt(b)
            q["answers"] = extract_answers(b)  # list of {"text", "is_correct"}
            q["shuffle"] = ("<no_shuffle>" not in b_low)
        elif "<multiple_choice>" in b_low or "<multiple choice>" in b_low:
            q["type"] = "multiple_choice"
            q["prompt_html"] = extract_prompt(b)
            q["answers"] = extract_answers(b)
            q["shuffle"] = ("<no_shuffle>" not in b_low)

        elif "<true_false>" in b_low or "<true/false>" in b_low:
            q["type"] = "true_false"
            q["prompt_html"] = extract_prompt(b)
            m = re.search(r"(?im)^\s*correct\s*:\s*(true|false)\s*$", b)
            q["correct"] = (m.group(1).lower() == "true") if m else True

        elif "<short_answer>" in b_low:
            q["type"] = "short_answer"
            q["prompt_html"] = extract_prompt(b)
            q["answers"] = [{"text": s} for s in extract_block_list(b, r"(?im)^answers:\s*$")]

        elif "<numeric>" in b_low:
            q["type"] = "numeric"
            q["prompt_html"] = extract_prompt(b)
            exact = find_value(b, r"(?im)^\s*exact\s*:\s*(.+)$")
            tol   = find_value(b, r"(?im)^\s*tolerance\s*:\s*(.+)$")
            q["numeric"] = {"exact": (exact if exact is None else str(exact).strip()),
                            "tolerance": float(tol) if tol not in (None, "") else 0}

        elif "<matching>" in b_low:
            q["type"] = "matching"
            q["prompt_html"] = extract_prompt(b)
            pairs = []
            for line in extract_block_list(b, r"(?im)^pairs:\s*$"):
                if "=>" in line:
                    left, right = [s.strip() for s in line.split("=>", 1)]
                    pairs.append({"prompt": left, "match": right})
            q["pairs"] = pairs

        elif "<ordering>" in b_low:
            q["type"] = "ordering"
            q["prompt_html"] = extract_prompt(b)
            q["order"] = extract_block_list(b, r"(?im)^order:\s*$")

        elif "<categorization>" in b_low:
            q["type"] = "categorization"
            q["prompt_html"] = extract_prompt(b)
            cats = []
            cat_blocks = re.findall(r"(?is)category\s+([^\:]+)\s*:\s*(.*?)(?=^category\s+|\Z)", b, flags=re.M)
            for name, items_blob in cat_blocks:
                items = [ln.strip() for ln in items_blob.splitlines() if ln.strip()]
                cats.append({"name": name.strip(), "items": items})
            q["categories"] = cats

        elif "<fill_in_blank>" in b_low or "<fill in the blank>" in b_low:
            q["type"] = "fill_in_blank"
            # If text_with_blanks exists: use it, otherwise build from prompt + answers
            # Expect tokens like H{{b1}}O
            m = re.search(r"(?is)text_with_blanks\s*:\s*(.+)$", b)
            if m:
                q["text_with_blanks"] = m.group(1).strip()
                # parse blank sections:
                blanks = []
                for m2 in re.finditer(r"(?is)blank\s+([a-z0-9_]+)\s*:\s*(.*?)\n(?=blank\s+[a-z0-9_]+:|\Z)", b):
                    bid = m2.group(1)
                    alts = [ln.strip("- ").strip() for ln in m2.group(2).splitlines() if ln.strip()]
                    blanks.append({"id": bid, "correct": alts})
                q["blanks"] = blanks
            else:
                q["prompt_html"] = extract_prompt(b)
                # answers: list under "answers:" section
                ans = extract_block_list(b, r"(?im)^answers:\s*$")
                q["answers"] = [{"text": s} for s in ans]

        else:
            # Fallback: treat as essay
            q["type"] = "essay"
            q["prompt_html"] = extract_prompt(b)

        qs.append(q)

    return {"questions": qs}

def extract_prompt(b: str) -> str:
    # first non-empty line that isn't a directive
    lines = [ln.strip() for ln in re.split(r"\r?\n", b)]
    content = []
    for ln in lines:
        if ln.lower().startswith(("<multiple", "<true", "<short", "<numeric", "<matching", "<ordering",
                                  "<categorization", "<fill", "<no_shuffle>", "answers:", "pairs:", "order:",
                                  "category ", "blank ", "text_with_blanks:", "correct:")):
            continue
        if ln:
            content.append(ln)
    if not content:
        return ""
    # wrap first line as the question, others as <p> lines (some authors paste options here)
    q = f"<p>{content[0]}</p>"
    tail = "".join(f"<p>{x}</p>" for x in content[1:])
    return q + tail

def extract_answers(b: str) -> List[Dict[str, Any]]:
    # lines like:
    # * 4 <feedback> Correct
    # 3 <feedback> Off by one
    answers: List[Dict[str, Any]] = []
    for ln in b.splitlines():
        s = ln.strip()
        if not s: continue
        is_correct = False
        if s.startswith("*"):
            is_correct = True
            s = s[1:].strip()
        if "<feedback>" in s.lower():
            left, fb = s.split("<feedback>", 1)
            text = left.strip()
            feedback_html = f"<p>{fb.strip()}</p>"
        else:
            text = s
            feedback_html = None
        # ignore directive lines
        if ":" in text and text.lower().split(":")[0] in {"correct","answers","pairs","order","category","blank","text_with_blanks"}:
            continue
        if text:
            answers.append({"text": text, "is_correct": is_correct, "feedback_html": feedback_html})
    return answers

def extract_block_list(b: str, header_regex: str) -> List[str]:
    """
    Example:
      answers:
      Red
      Blue
      Yellow
    """
    m = re.search(header_regex, b)
    if not m: return []
    start = m.end()
    lines = []
    for ln in b[start:].splitlines():
        if re.match(r"(?i)^(answers:|pairs:|order:|category |blank |text_with_blanks:)", ln.strip()):
            break
        s = ln.strip()
        if s:
            s = s.lstrip("- ").strip()
            lines.append(s)
    return lines

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Canvas New Quizzes Uploader (One-file)", layout="wide")
st.title("Canvas New Quizzes Uploader (All Item Types) — Single File")

def validate_item_payload(p: dict) -> List[str]:
    errs = []
    entry = p.get("item", {}).get("entry", {}) if isinstance(p, dict) else {}
    slug = (entry.get("interaction_type_slug") or "").lower()
    if slug in ("choice", "multi-answer"):
        choices = (entry.get("interaction_data") or {}).get("choices") or []
        if len(choices) < 2:
            errs.append(f"{slug}: needs ≥2 choices, has {len(choices)}")
        ids = [c.get("id") for c in choices if c.get("id")]
        if slug == "choice":
            val = ((entry.get("scoring_data") or {}).get("value"))
            if val not in ids:
                errs.append("choice: scoring_data.value not in choices")
        else:
            vals = ((entry.get("scoring_data") or {}).get("value")) or []
            bad = [v for v in vals if v not in ids]
            if bad:
                errs.append(f"multi-answer: invalid ids in value: {bad}")
    if slug == "rich-fill-blank":
        val = (entry.get("scoring_data") or {}).get("value") or {}
        bmap = val.get("blank_to_correct_answer_ids") or {}
        if not bmap:
            errs.append("fill-in-blank: missing blank_to_correct_answer_ids")
    if slug == "numeric":
        v = (entry.get("scoring_data") or {}).get("value") or []
        if not isinstance(v, list) or not v:
            errs.append("numeric: scoring_data.value must be non-empty list")
    if slug == "matching":
        ia = entry.get("interaction_data") or {}
        if not (ia.get("choices") and ia.get("prompts")):
            errs.append("matching: needs choices and prompts")
    if slug == "ordering":
        ia = entry.get("interaction_data") or {}
        if not (ia.get("choices") and (entry.get("scoring_data") or {}).get("value")):
            errs.append("ordering: choices or scoring value missing")
    if slug == "categorization":
        ia = entry.get("interaction_data") or {}
        if not (ia.get("categories") and ia.get("choices")):
            errs.append("categorization: categories or choices missing")
    return errs

with st.sidebar:
    st.header("Canvas Settings")
    canvas_domain = st.text_input("Canvas domain (no protocol)", placeholder="your.instructure.com")
    canvas_token = st.text_input("Canvas Access Token", type="password")
    course_id = st.text_input("Course ID", placeholder="12345")
    module_id = st.text_input("Module ID (optional)", placeholder="67890")
    st.caption("Supported types: " + ", ".join(sorted(SUPPORTED_TYPES)))

tab1, tab2 = st.tabs(["Upload Storyboard", "Quick Test"])

with tab1:
    st.subheader("Upload Storyboard (.docx or .txt)")
    up = st.file_uploader("Upload a storyboard file", type=["docx", "txt"])
    if up is not None:
        raw_text = load_storyboard_text(up)
        st.text_area("Raw storyboard (detected)", raw_text, height=200)
        pages = raw_text.split("</canvas_page>")
        pages = [p + "</canvas_page>" for p in pages if "<canvas_page>" in p.lower()]
        st.write(f"Detected {len(pages)} <canvas_page> block(s).")

        for i, block in enumerate(pages, start=1):
            with st.expander(f"Canvas Page #{i}"):
                st.code(block, language="xml")
                if "<quiz_start>" in block.lower():
                    st.info("Quiz block detected in this page.")
                    parsed = parse_quiz_block(block)
                    qs = parsed.get("questions", [])
                    st.write(f"Parsed {len(qs)} question(s).")
                    st.json(parsed)

                    colA, colB = st.columns(2)
                    with colA:
                        quiz_title = st.text_input(f"Quiz Title (Page #{i})", f"Quiz from Page {i}", key=f"title_{i}")
                    with colB:
                        description = st.text_area(f"Quiz Description (Page #{i})", "Generated by API Uploader", key=f"desc_{i}")

                    if st.button(f"Create & Upload New Quiz for Page #{i}", key=f"upload_{i}"):
                        if not (canvas_domain and canvas_token and course_id):
                            st.error("Canvas settings are required in the sidebar."); st.stop()
                        if len(qs) == 0:
                            st.error("Parsed 0 questions. Ensure <question> blocks exist."); st.stop()

                        code, me = whoami(canvas_domain, canvas_token)
                        if code != 200:
                            st.error("Token check failed."); st.code(json.dumps(me, indent=2), language="json"); st.stop()

                        created = create_new_quiz(canvas_domain, course_id, quiz_title, description, canvas_token)
                        if not created or not created.get("assignment_id"):
                            st.error("Create New Quiz did not return an assignment_id.")
                            st.code(json.dumps(created.get("http_debug", {}), indent=2), language="json"); st.stop()
                        assignment_id = created["assignment_id"]

                        builder = NewQuizItemBuilder()
                        success_ct, failures = 0, []

                        for pos, q in enumerate(qs, start=1):
                            try:
                                payload = builder.build_item(q)

                                # Validate before POST
                                problems = validate_item_payload(payload)
                                if problems:
                                    st.warning(f"Item #{pos} failed validation: {problems}")

                                # Show payload for first item
                                if pos == 1:
                                    st.write("DEBUG • About to POST item #1")
                                    st.code(json.dumps(payload, indent=2), language="json")

                                r = post_new_quiz_item(canvas_domain, course_id, assignment_id, payload, canvas_token, position=pos)
                                try:
                                    body = r.json()
                                except Exception:
                                    body = r.text
                                if r.status_code in (200, 201):
                                    success_ct += 1
                                else:
                                    failures.append({"position": pos, "status": r.status_code, "body": body})
                            except Exception as e:
                                failures.append({"position": pos, "status": "client-exception", "body": str(e)})

                        st.success(f"New Quiz created. {success_ct}/{len(qs)} items posted. (assignment_id={assignment_id})")

                        status_code, items_data = get_new_quiz_items(canvas_domain, course_id, assignment_id, canvas_token)
                        st.caption(f"Items GET status: {status_code}")
                        st.code(json.dumps(items_data, indent=2), language="json")

                        if publish_assignment(canvas_domain, course_id, assignment_id, canvas_token):
                            st.success("Assignment published.")
                        else:
                            st.warning("Could not publish assignment (publish manually if needed).")

                        st.markdown(f"[Open in Canvas]({assignment_url(canvas_domain, course_id, assignment_id)})")

                        if failures:
                            st.warning("Some items failed to add:")
                            st.code(json.dumps(failures, indent=2), language="json")

                        if module_id:
                            ok = add_to_module(canvas_domain, course_id, module_id, "Assignment", assignment_id, quiz_title, canvas_token)
                            st.success("Added to Module.") if ok else st.warning("Could not add to Module.")

                        st.markdown("---")
                        if st.button("Reset items (delete all) and re-post", key=f"repair_{i}"):
                            summary = delete_all_new_quiz_items(canvas_domain, course_id, assignment_id, canvas_token)
                            st.info(f"Deleted {summary.get('deleted', 0)} existing item(s).")
                            builder = NewQuizItemBuilder()
                            success_ct2, failures2 = 0, []
                            for pos, q in enumerate(qs, start=1):
                                payload = builder.build_item(q)
                                problems = validate_item_payload(payload)
                                if problems:
                                    st.warning(f"Item #{pos} failed validation: {problems}")
                                r = post_new_quiz_item(canvas_domain, course_id, assignment_id, payload, canvas_token, position=pos)
                                try:
                                    body = r.json()
                                except Exception:
                                    body = r.text
                                if r.status_code in (200, 201):
                                    success_ct2 += 1
                                else:
                                    failures2.append({"position": pos, "status": r.status_code, "body": body})
                            st.success(f"Re-posted {success_ct2}/{len(qs)} items.")
                            if failures2:
                                st.code(json.dumps(failures2, indent=2), language="json")

with tab2:
    st.subheader("Try a Minimal Example")
    example = """<canvas_page>
<quiz_start>
<question><multiple_choice><no_shuffle>
What is 2 + 2?
* 4 <feedback> Correct
3 <feedback> Off by one
5 <feedback> Too high
</question>

<question><true_false>
The sky is blue.
correct: True
</question>

<question><short_answer>
Name a primary color.
answers:
Red
Blue
Yellow
</question>

<question><numeric>
What is the speed (m/s)?
exact: 12.5
tolerance: 0.5
</question>

<question><matching>
Match the chemical to its common name.
pairs:
H2O => Water
NaCl => Salt
</question>

<question><ordering>
Order the stages:
order:
First
Second
Third
</question>

<question><categorization>
Sort animals:
category Mammals:
Dog
Cat
category Birds:
Eagle
Sparrow
</question>

<question><fill_in_blank>
Water formula: H{{b1}}O is {{b2}}.
blank b1:
  - 2
blank b2:
  - water
</question>
</quiz_end>
</canvas_page>"""
    st.code(example, language="xml")
    st.caption("Paste this into a .txt file to test.")
