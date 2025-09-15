
from typing import Union
from io import BytesIO
from pathlib import Path

def load_storyboard_text(uploaded) -> str:
    """
    Accepts a .docx or .txt upload and returns raw text.
    """
    name = getattr(uploaded, "name", "upload.txt").lower()
    if name.endswith(".txt"):
        return uploaded.read().decode("utf-8", errors="ignore")

    if name.endswith(".docx"):
        try:
            from docx import Document
        except Exception:
            raise RuntimeError("python-docx is required to parse .docx files.")
        data = uploaded.read()
        doc = Document(BytesIO(data))
        parts = []
        for p in doc.paragraphs:
            parts.append(p.text)
        # join with newlines
        return "\n".join(parts)
    # Fallback
    return uploaded.read().decode("utf-8", errors="ignore")
