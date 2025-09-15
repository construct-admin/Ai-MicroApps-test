# storyboard.py
from typing import Union
from io import BytesIO
from docx import Document

def load_storyboard_text(file_like: Union[BytesIO, "UploadedFile"]) -> str:
    """
    Accepts a Streamlit UploadedFile or a BytesIO. Supports .txt and .docx.
    Returns a normalized UTF-8 string.
    """
    name = getattr(file_like, "name", "uploaded")
    data = file_like.read() if hasattr(file_like, "read") else file_like.getvalue()
    if name.lower().endswith(".txt"):
        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("latin-1", errors="ignore")
    if name.lower().endswith(".docx"):
        bio = BytesIO(data)
        doc = Document(bio)
        # Join paragraphs with line breaks
        text = "\n".join(p.text for p in doc.paragraphs)
        return text
    # fallback: try utf-8
    try:
        return data.decode("utf-8")
    except Exception:
        return data.decode("latin-1", errors="ignore")
