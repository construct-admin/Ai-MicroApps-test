# quiz_tag_parser.py
import re
from typing import List, Dict, Any

def _strip(s: str) -> str:
    return (s or "").strip()

def _normalize(text: str) -> str:
    text = (text or "").replace("\u00A0", " ")
    text = text.replace("•", "- ").replace("–", "- ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text

_OPTION_RE = re.compile(r"""^(
    \* \s |                 # "* "
    - \s |                  # "- "
    [A-Za-z]\) \s |         # "A) "
    \d+\) \s |              # "1) "
    [A-Za-z]\. \s |         # "A. "
    \d+\. \s                # "1. "
)""", re.X)

def _is_type_flag(line: str) -> bool:
    return bool(re.match(
        r"</?\s*(multiple_choice|multiple_answers|true_false|short_answer|essay|numeric|matching|ordering|categorization|fill_in_blank)\s*>",
        line, re.IGNORECASE))

def _is_shuffle_flag(line: str) -> bool:
    return bool(re.match(r"</?\s*(shuffle|no_shuffle)\s*>", line, re.IGNORECASE))

class QuizTagParser:
    """
    Parses <quiz_start>...</quiz_end> blocks inside a <canvas_page>.
    Produces a normalized list of questions for New Quizzes builder.
    Supported types:
      multiple_choice, multiple_answer, true_false, short_answer, essay, numeric,
      matching, ordering, categorization, fill_in_blank
    """
    def parse(self, raw_block: str) -> Dict[str, Any]:
        raw_block = _normalize(raw_block)
        m = re.search(r"<quiz_start\b[^>]*>\s*([\s\S]+?)\s*</\s*(?:quiz_end|quiz)\s*>",
                      raw_block, re.IGNORECASE)
        if not m:
            return {"questions": []}
        txt = m.group(1)

        q_blocks = re.findall(r"<question\b[^>]*>\s*([\s\S]+?)\s*</\s*question\s*>", txt, re.IGNORECASE)
        questions: List[Dict[str, Any]] = []

        for qidx, qb in enumerate(q_blocks, start=1):
            qb = _normalize(qb)
            lines = [ln.rstrip() for ln in qb.strip().splitlines() if _strip(ln)]

            joined = "\n".join(lines)
            if re.search(r"<\s*multiple_answers\s*>", joined, re.IGNORECASE):
                qtype = "multiple_answer"
            elif re.search(r"<\s*true_false\s*>", joined, re.IGNORECASE):
                qtype = "true_false"
            elif re.search(r"<\s*short_answer\s*>", joined, re.IGNORECASE):
                qtype = "short_answer"
            elif re.search(r"<\s*essay\s*>", joined, re.IGNORECASE):
                qtype = "essay"
            elif re.search(r"<\s*numeric\s*>", joined, re.IGNORECASE):
                qtype = "numeric"
            elif re.search(r"<\s*matching\s*>", joined, re.IGNORECASE):
                qtype = "matching"
            elif re.search(r"<\s*ordering\s*>", joined, re.IGNORECASE):
                qtype = "ordering"
            elif re.search(r"<\s*categorization\s*>", joined, re.IGNORECASE):
                qtype = "categorization"
            elif re.search(r"<\s*fill_in_blank\s*>", joined, re.IGNORECASE):
                qtype = "fill_in_blank"
            else:
                qtype = "multiple_choice"

            shuffle = True
            if re.search(r"<\s*no_shuffle\s*>", joined, re.IGNORECASE):
                shuffle = False

            prompt_lines: List[str] = []
            answers: List[Dict[str, Any]] = []
            q_fb = {"correct": None, "incorrect": None, "neutral": None}
            tf_correct = None
            numeric_spec = {"exact": None, "tolerance": 0.0}
            short_answers: List[str] = []
            blanks_map: Dict[str, List[str]] = {}
            matching_pairs: List[Dict[str, str]] = []
            ordering_items: List[str] = []
            categories: List[Dict[str, Any]] = []

            state = "stem"
            current_blank = None
            current_category = None

            for ln in lines:
                l = ln.strip()
                if not l or _is_type_flag(l) or _is_shuffle_flag(l):
                    continue
                lower = l.lower()

                if lower.startswith("feedback_correct:"):
                    q_fb["correct"] = _strip(l.split(":", 1)[1]); continue
                if lower.startswith("feedback_incorrect:"):
                    q_fb["incorrect"] = _strip(l.split(":", 1)[1]); continue
                if lower.startswith("feedback_neutral:"):
                    q_fb["neutral"] = _strip(l.split(":", 1)[1]); continue

                if qtype == "true_false" and lower.startswith("correct:"):
                    rhs = _strip(l.split(":", 1)[1])
                    tf_correct = rhs.lower() in ["true", "t", "1", "yes"]; continue

                if qtype == "numeric":
                    if lower.startswith("exact:"):
                        numeric_spec["exact"] = float(_strip(l.split(":", 1)[1])); continue
                    if lower.startswith("tolerance:"):
                        numeric_spec["tolerance"] = float(_strip(l.split(":", 1)[1])); continue

                if qtype == "short_answer":
                    if lower == "answers:":
                        state = "short_answer_answers"; continue
                    if state == "short_answer_answers":
                        if l and not l.endswith(":"):
                            short_answers.append(_strip(l.lstrip("-* "))); continue
                        state = "stem"

                if qtype == "fill_in_blank":
                    if lower.startswith("blank "):
                        m2 = re.match(r"blank\s+([A-Za-z0-9_]+)\s*:\s*$", l, re.IGNORECASE)
                        if m2:
                            current_blank = m2.group(1)
                            blanks_map.setdefault(current_blank, [])
                            state = "blank_values"; continue
                    if state == "blank_values":
                        if l.startswith(("-", "*")):
                            blanks_map[current_blank].append(_strip(l.lstrip("-* "))); continue
                        state = "stem"

                if qtype == "matching":
                    if lower == "pairs:":
                        state = "pairs"; continue
                    if state == "pairs":
                        if "=>" in l:
                            left, right = l.split("=>", 1)
                            matching_pairs.append({"prompt": _strip(left), "match": _strip(right)}); continue
                        state = "stem"

                if qtype == "ordering":
                    if lower == "order:":
                        state = "order"; continue
                    if state == "order":
                        if l and not l.endswith(":"):
                            ordering_items.append(_strip(l.lstrip("-* "))); continue
                        state = "stem"

                if qtype == "categorization":
                    if lower.startswith("category "):
                        m3 = re.match(r"category\s+(.+?):\s*$", l, re.IGNORECASE)
                        if m3:
                            current_category = m3.group(1).strip()
                            categories.append({"name": current_category, "items": []})
                            state = "category_items"; continue
                    if state == "category_items":
                        if l and not l.endswith(":"):
                            categories[-1]["items"].append(_strip(l.lstrip("-* "))); continue
                        state = "stem"

                if qtype in ["multiple_choice", "multiple_answer"] and _OPTION_RE.match(l):
                    is_correct = l.startswith("* ")
                    opt = l[2:] if is_correct else _strip(_OPTION_RE.sub("", l, count=1))
                    fb = None
                    if " <feedback>" in opt:
                        opt, fb = opt.split(" <feedback>", 1)
                        opt, fb = _strip(opt), _strip(fb)
                    answers.append({
                        "text": opt,
                        "is_correct": is_correct,
                        "feedback_html": (f"<p>{fb}</p>" if fb else None)
                    })
                    continue

                prompt_lines.append(l)

            prompt_html = "<p>" + "</p><p>".join([_strip(x) for x in prompt_lines if _strip(x)]) + "</p>" if prompt_lines else "<p></p>"

            qnorm: Dict[str, Any] = {
                "type": qtype,
                "title": f"Question {qidx}",
                "prompt_html": prompt_html,
                "points": 1,
                "shuffle": shuffle,
                "feedback": q_fb
            }
            if qtype in ["multiple_choice", "multiple_answer"]:
                qnorm["answers"] = answers
            elif qtype == "true_false":
                qnorm["correct"] = bool(tf_correct)
            elif qtype == "short_answer":
                qnorm["answers"] = [{"text": x} for x in short_answers]
            elif qtype == "numeric":
                qnorm["numeric"] = {"exact": numeric_spec["exact"], "tolerance": numeric_spec["tolerance"]}
            elif qtype == "fill_in_blank":
                qnorm["blanks"] = [{"id": k, "correct": v} for k, v in blanks_map.items()]
            elif qtype == "matching":
                qnorm["pairs"] = matching_pairs
            elif qtype == "ordering":
                qnorm["order"] = ordering_items
            elif qtype == "categorization":
                qnorm["categories"] = categories

            questions.append(qnorm)

        return {"questions": questions}
