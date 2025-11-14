# ------------------------------------------------------------------------------
# Refactor date: 2025-11-12
# Refactored by: Imaad Fakier
# Purpose: Align CLD Topic Extractor with OES GenAI Streamlit standards.
# ------------------------------------------------------------------------------

"""
CLD Topic Extractor (Refactored, Production-Secure)
---------------------------------------------------
Streamlit micro-app for extracting headings and module topics from Course Learning
Design (.docx) files, then structuring them into a clean, hierarchical format
for downstream use (e.g., Umich Feedback Bot).

Highlights in this refactor:
- `.env` loading via `dotenv` and unified SHA-256 access-code authentication.
- Clear sectioning, robust error handling, and truncation guards.
- Preserves GPT-driven grouping logic (gpt-4o-mini) with deterministic settings.
- Safe UI/UX: optional previews, clean status messages, and download button.

Dependencies:
    streamlit, python-docx, python-dotenv, openai (>=1.x)
"""

from __future__ import annotations

import io
import os
import hashlib
from typing import List, Tuple, Optional

import streamlit as st
from dotenv import load_dotenv

# OpenAI SDK (v1.x)
try:
    from openai import OpenAI  # pip install openai>=1.0.0
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


# ------------------------------------------------------------------------------
# Environment setup
# ------------------------------------------------------------------------------
load_dotenv()  # Load variables from .env when present

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
ACCESS_CODE_HASH = os.getenv("ACCESS_CODE_HASH", "").strip()

# Initialize OpenAI client if possible
client = OpenAI(api_key=OPENAI_API_KEY) if (OpenAI and OPENAI_API_KEY) else None


# ------------------------------------------------------------------------------
# Streamlit page configuration
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="CLD Topic Extractor",
    page_icon="📘",
    layout="centered",
    initial_sidebar_state="expanded",
)

# App metadata (for consistency with other OES apps)
APP_URL = ""  # optional registry URL if you publish a test/prod link
APP_IMAGE = ""  # optional image path
PUBLISHED = True

APP_TITLE = "CLD Topic Extractor"
APP_INTRO = (
    "Upload a Course Learning Design (.docx) file. This tool extracts headings "
    "and structures them into a clean, hierarchical table of contents suitable "
    "for the Umich Feedback Bot."
)

ACCENT_COLOR = "#2563EB"
MAX_PREVIEW_CHARS = 80_000  # Prevent overly large text previews
SIDEBAR_HIDDEN = True


# ------------------------------------------------------------------------------
# Authentication utilities (SHA-256 access code)
# ------------------------------------------------------------------------------
def _hash_code(input_code: str) -> str:
    """Hash an access code using SHA-256 for secure comparison."""
    return hashlib.sha256(input_code.encode("utf-8")).hexdigest()


if not ACCESS_CODE_HASH:
    st.error(
        "⚠️ ACCESS_CODE_HASH not found in environment. "
        "Ask Engineering for the hashed access code and configure it in the deployment env."
    )
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Access Restricted")
    code = st.text_input("Enter Access Code:", type="password", key="access_code_input")
    if st.button("Submit", key="submit_access_code"):
        if _hash_code(code) == ACCESS_CODE_HASH:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect access code. Please try again.")
    st.stop()


# ------------------------------------------------------------------------------
# Lazy import helper for python-docx
# ------------------------------------------------------------------------------
def _try_load_docx():
    """Safely import python-docx (avoids hard crash if missing)."""
    try:
        import docx  # type: ignore

        return docx
    except Exception:
        return None


DOCX_MOD = _try_load_docx()


# ------------------------------------------------------------------------------
# File reading utilities
# ------------------------------------------------------------------------------
def read_docx_bytes(file_bytes: bytes) -> Tuple[str, List[str]]:
    """
    Extract plain text and all heading lines from a DOCX file.

    Args:
        file_bytes: Raw bytes from a .docx upload.

    Returns:
        (full_text, headings)
        - full_text: str with document text joined by newlines
        - headings: list[str] of detected headings ("Heading 1", "Heading 2", etc.)
    """
    if not DOCX_MOD:
        return "", []

    document = DOCX_MOD.Document(io.BytesIO(file_bytes))
    all_lines: List[str] = []
    headings: List[str] = []

    for para in document.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        all_lines.append(text)

        style_name = getattr(para.style, "name", "") or ""
        if style_name.lower().startswith("heading"):
            headings.append(text)

    return "\n".join(all_lines), headings


# ------------------------------------------------------------------------------
# GPT grouping logic
# ------------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are a precise academic text parser that structures extracted headings from a Course Learning Design (CLD) document.

Your goal is to produce a *clean, hierarchical table of contents* of all modules and their subtopics, like this:

Module One: How Do Values Shape Technology
- Social Values
- Political Priorities
- Impacts of Values, Biases, and Assumptions That Shape Design

Module Two: Technology and Equity
- Traditional Goals and Values
- Hiding Bias and Inequities in Language
- Hidden Assumptions and Embedded Inequalities in Technology Design and Development

Guidelines:
- Preserve document order.
- Only include *Modules and their subtopics* (omit admin pages like “Welcome!”, “Resources”, “Files for Download”).
- Keep topic titles concise and true to source text.
- Always begin new sections with “Module X:”.
- Output plain text only (no Markdown).
""".strip()


def gpt_group_modules(raw_headings: List[str], raw_text: str) -> str:
    """
    Group extracted CLD headings into a module-based Table of Contents using GPT.

    Args:
        raw_headings: List of detected heading strings.
        raw_text: Full text of the CLD document (context).

    Returns:
        Formatted plain-text Table of Contents (modules and subtopics).
    """
    if not client:
        return ""

    user_prompt = f"""Extracted Headings:
{chr(10).join(raw_headings)}

Full Text (for context, truncated):
{raw_text[:MAX_PREVIEW_CHARS]}
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=900,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        st.error(f"⚠️ GPT request failed: {e}")
        return ""


# ------------------------------------------------------------------------------
# UI Layout
# ------------------------------------------------------------------------------
st.title("📘 CLD Topic Extractor")
st.markdown(
    f"""
<div style="color:#475569">
  Upload a <code>.docx</code> CLD document to automatically organize module titles and subtopics
  into a structured Table of Contents for the Umich Feedback Bot.
</div>
""",
    unsafe_allow_html=True,
)

with st.expander("Notes & Usage", expanded=False):
    st.markdown(
        """
**Steps**
1. Upload the `.docx` CLD document.  
2. (Optional) Enable *Show text preview*.  
3. Click **Generate Structured Topics**.  
4. Copy or download the formatted Table of Contents.  
        """
    )

col1, col2 = st.columns([3, 2])
with col1:
    uploaded = st.file_uploader("Upload CLD .docx file", type=["docx"])
with col2:
    show_preview = st.checkbox("Show text preview", value=False)

if not DOCX_MOD:
    st.warning(
        "⚠️ `python-docx` not installed.\n\nInstall dependencies:\n"
        "```bash\npip install python-docx python-dotenv openai streamlit\n```"
    )

if uploaded is not None and DOCX_MOD:
    file_bytes = uploaded.read()
    full_text, raw_headings = read_docx_bytes(file_bytes)

    with st.expander("🔹 Extracted Headings (raw preview)", expanded=False):
        if raw_headings:
            st.success(f"Found {len(raw_headings)} heading(s).")
            st.code("\n".join(raw_headings[:200]), language="text")
        else:
            st.warning(
                "No styled headings detected — GPT will infer topics directly from text."
            )

    if show_preview:
        st.markdown("### Document Text Preview")
        st.code(full_text[:MAX_PREVIEW_CHARS], language="text")

    st.divider()

    disabled = not bool(OPENAI_API_KEY)
    if disabled:
        st.info(
            "Add your OPENAI_API_KEY to the environment or `.env` file before generating."
        )

    generate = st.button(
        "Generate Structured Topics",
        use_container_width=True,
        disabled=disabled,
    )

    if generate:
        with st.spinner("Structuring topics into modules..."):
            structured_output = gpt_group_modules(raw_headings, full_text)

        if structured_output:
            st.success("✅ Modules and topics structured successfully!")
            st.markdown("### 📋 Formatted Table of Contents (for Feedback Bot)")

            st.text_area(
                "Final Output (copy into Feedback Bot 'List of Topics' field):",
                value=structured_output,
                height=350,
                key="structured_output",
            )

            st.download_button(
                label="⬇️ Download Structured Topics",
                data=structured_output,
                file_name="cld_structured_topics.txt",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            st.error(
                "❌ No structured topics were generated. Check the heading structure or try again."
            )
else:
    st.info("📤 Upload a CLD `.docx` to begin.")

# ------------------------------------------------------------------------------
# Sidebar controls
# ------------------------------------------------------------------------------
st.sidebar.button(
    "Logout", on_click=lambda: st.session_state.update({"authenticated": False})
)
