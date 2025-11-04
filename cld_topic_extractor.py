# ─────────────────────────────────────────────────────────────
# 📘 CLD Topic Extractor (Streamlit Deployment Version)
# Author: OES GenAI Team
# Purpose:
#   Extracts headings and module topics from Course Learning Design (CLD)
#   .docx files and structures them into a clean, hierarchical format
#   suitable for downstream use by the Umich Feedback Bot.
# Deployment:
#   Streamlit-ready for OES GenAI Studio
# Dependencies:
#   pip install streamlit openai python-docx python-dotenv
# ─────────────────────────────────────────────────────────────

import io
import os
from typing import List, Tuple
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


# ──────────────────────────────
# 🔧 Environment & API Setup
# ──────────────────────────────
load_dotenv()  # Load .env file if present
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Instantiate OpenAI client only if API key exists
client = OpenAI(api_key=API_KEY) if API_KEY else None


# ──────────────────────────────
# 🎨 Streamlit Page Configuration
# ──────────────────────────────
st.set_page_config(
    page_title="CLD Topic Extractor",
    page_icon="📘",
    layout="centered",
)
ACCENT_COLOR = "#2563EB"
MAX_PREVIEW_CHARS = 80_000  # Prevent overly large text previews


# ──────────────────────────────
# 🧩 Lazy Import Helper
# ──────────────────────────────
def try_load_docx():
    """Safely attempt to import `python-docx` to avoid runtime failure."""
    try:
        import docx  # type: ignore

        return docx
    except ImportError:
        return None


DOCX_MOD = try_load_docx()


# ──────────────────────────────
# 📄 File Reading Utilities
# ──────────────────────────────
def read_docx_bytes(file_bytes: bytes) -> Tuple[str, List[str]]:
    """
    Extracts plain text and all heading lines from a DOCX file.

    Args:
        file_bytes: The uploaded .docx file as raw bytes.

    Returns:
        Tuple containing:
        - full_text: str → all text joined with newlines
        - headings: List[str] → all detected headings (Heading 1, Heading 2, etc.)
    """
    if not DOCX_MOD:
        return "", []

    document = DOCX_MOD.Document(io.BytesIO(file_bytes))
    all_lines, headings = [], []

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        all_lines.append(text)

        # Identify heading styles
        style_name = getattr(para.style, "name", "") or ""
        if style_name.lower().startswith("heading"):
            headings.append(text)

    return "\n".join(all_lines), headings


# ──────────────────────────────
# 🧠 GPT Structuring Logic
# ──────────────────────────────
def gpt_group_modules(raw_headings: List[str], raw_text: str) -> str:
    """
    Uses GPT to group extracted CLD headings into a module-based Table of Contents.

    Args:
        raw_headings: List of detected heading strings.
        raw_text: The full text of the CLD document for contextual understanding.

    Returns:
        A formatted plain-text Table of Contents (modules and subtopics).
    """
    if not client:
        return ""

    # Model instructions for GPT
    system_prompt = """
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
- Output plain text only — no Markdown, no numbering beyond module titles.
""".strip()

    # Provide extracted content to the model
    user_prompt = f"""
Extracted Headings:
{chr(10).join(raw_headings)}

Full Text (for context, truncated):
{raw_text[:MAX_PREVIEW_CHARS]}
""".strip()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=900,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"⚠️ GPT request failed: {e}")
        return ""


# ──────────────────────────────
# 🖥️ Streamlit Interface
# ──────────────────────────────

# Header section
st.markdown(
    """
    <div style="text-align:center">
      <h1 style="margin-bottom:0">📘 CLD Topic Extractor</h1>
      <p style="color:#475569;margin-top:6px">
        Automatically organizes module titles and subtopics into a structured Table of Contents.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Usage instructions
with st.expander("Notes & Usage", expanded=False):
    st.markdown(
        """
**Purpose:**  
Extracts module titles and page topics from a Course Learning Design (CLD) document,  
then organizes them into the clean, hierarchical format required by the Umich Feedback Bot.

**Steps:**  
1. Upload the `.docx` CLD document  
2. (Optional) Enable *Show text preview*  
3. Click **Generate Structured Topics**  
4. Copy or download the formatted Table of Contents for the Feedback Bot  
"""
    )

# Upload section
col1, col2 = st.columns([3, 2])
with col1:
    uploaded = st.file_uploader("Upload CLD .docx file", type=["docx"])
with col2:
    show_preview = st.checkbox("Show text preview", value=False)

# Missing dependency message
if not DOCX_MOD:
    st.warning(
        "⚠️ `python-docx` not found.\n\nInstall dependencies first:\n"
        "```bash\npip install python-docx python-dotenv openai streamlit\n```",
        icon="warning",
    )

# Main logic
if uploaded is not None and DOCX_MOD:
    file_bytes = uploaded.read()
    full_text, raw_headings = read_docx_bytes(file_bytes)

    # Headings preview
    with st.expander("🔹 Extracted Headings (raw preview)", expanded=False):
        if raw_headings:
            st.success(f"Found {len(raw_headings)} heading(s).")
            st.code("\n".join(raw_headings[:200]), language="text")
        else:
            st.warning(
                "No styled headings detected — GPT will infer topics directly from text."
            )

    # Optional text preview
    if show_preview:
        st.markdown("### Document Text Preview")
        st.code(full_text[:MAX_PREVIEW_CHARS], language="text")

    st.divider()

    # Generate button
    generate = st.button(
        "Generate Structured Topics",
        use_container_width=True,
        disabled=not API_KEY,
    )

    if not API_KEY:
        st.info("Add your OPENAI_API_KEY to a `.env` file or environment variable.")

    # Generate structured output
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
