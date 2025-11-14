# ------------------------------------------------------------------------------
# Refactor date: 2025-11-12
# Refactored by: Imaad Fakier
# Purpose: Align Canvas Import micro-app with OES GenAI Streamlit app standards.
# ------------------------------------------------------------------------------
"""
Canvas Import (Refactored)
--------------------------
Streamlit micro-application for converting uploaded DOCX or PDF files into HTML content
and publishing that content directly to a Canvas LMS course via API integration.

Highlights:
- Unified `.env` environment loading for Canvas and OpenAI secrets.
- SHA-256 access-code authentication aligned with OES GenAI access standards.
- Structured function documentation and modular design.
- Enhanced error handling, status messages, and consistent Streamlit UI design.
- Preserves AI-generated HTML workflow while standardizing the RAG/LLM pipeline format.

Dependencies:
    - streamlit
    - requests
    - python-docx
    - PyMuPDF or pypdf
    - python-dotenv

External APIs:
    - Canvas LMS REST API v1
    - OpenAI GPT-4o (optional)
"""

import os
import hashlib
import requests
import streamlit as st
from dotenv import load_dotenv

# Optional: AI HTML generation via OpenAI API
try:
    import openai
except ImportError:
    openai = None

# ------------------------------------------------------------------------------
# Environment setup
# ------------------------------------------------------------------------------
load_dotenv()

# ------------------------------------------------------------------------------
# Streamlit page configuration
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Canvas HTML Importer",
    page_icon="app_images/construct.webp",
    layout="centered",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------------------
# Authentication utilities
# ------------------------------------------------------------------------------
def _hash_code(input_code: str) -> str:
    """Hash an access code using SHA-256 for secure authentication."""
    return hashlib.sha256(input_code.encode("utf-8")).hexdigest()


ACCESS_CODE_HASH = os.getenv("ACCESS_CODE_HASH")
if not ACCESS_CODE_HASH:
    st.error(
        "⚠️ ACCESS_CODE_HASH not found in environment. Configure before deployment."
    )
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Access Restricted")
    code_input = st.text_input(
        "Enter Access Code:", type="password", key="access_code_input"
    )
    if st.button("Submit", key="submit_access_code"):
        if _hash_code(code_input) == ACCESS_CODE_HASH:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect access code. Please try again.")
    st.stop()

# ------------------------------------------------------------------------------
# App metadata and configuration
# ------------------------------------------------------------------------------
PUBLISHED = True
APP_URL = "https://alt-text-bot.streamlit.app/"

APP_TITLE = "Construct HTML Generator"
APP_INTRO = "Convert DOCX or PDF course content into HTML and publish to Canvas."
APP_HOW_IT_WORKS = (
    "1. Enter Canvas module and page details.\n"
    "2. Upload DOCX or PDF content.\n"
    "3. Generate AI-formatted HTML (optional).\n"
    "4. Push to Canvas via API integration."
)

SYSTEM_PROMPT = (
    "Convert raw academic content into clean, semantic HTML for Canvas.\n"
    "Exclude any <DOCTYPE> or <html>/<head> boilerplate. Focus on readability and structure."
)


# ------------------------------------------------------------------------------
# File extraction utilities
# ------------------------------------------------------------------------------
def extract_text_from_uploaded_files(files):
    """Extract plain text from DOCX or PDF uploads."""
    texts = []
    for file in files:
        ext = file.name.split(".")[-1].lower()
        try:
            if ext == "docx":
                from docx import Document

                doc = Document(file)
                texts.append("\n".join([p.text for p in doc.paragraphs]))
            elif ext == "pdf":
                from pypdf import PdfReader

                pdf = PdfReader(file)
                text = "".join([p.extract_text() or "" for p in pdf.pages])
                texts.append(text)
            else:
                texts.append(file.read().decode("utf-8"))
        except Exception as e:
            texts.append(f"[Error reading {file.name}: {e}]")
    return "\n".join(texts)


# ------------------------------------------------------------------------------
# OpenAI integration (optional)
# ------------------------------------------------------------------------------
def get_ai_generated_html(prompt: str):
    """Convert text content into formatted HTML using OpenAI GPT-4o."""
    api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        st.error("Missing OpenAI API key. Please configure in environment or secrets.")
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
    )
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip("`")
    st.error(f"OpenAI API Error {response.status_code}: {response.text}")
    return None


# ------------------------------------------------------------------------------
# Canvas API integration
# ------------------------------------------------------------------------------
def create_module(module_name, canvas_domain, course_id, headers):
    """Create a Canvas module and return its ID."""
    url = f"https://{canvas_domain}/api/v1/courses/{course_id}/modules"
    payload = {"module": {"name": module_name, "published": PUBLISHED}}
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json().get("id") if resp.status_code in [200, 201] else None


def create_wiki_page(page_title, page_body, canvas_domain, course_id, headers):
    """Create a Canvas wiki page within a course."""
    url = f"https://{canvas_domain}/api/v1/courses/{course_id}/pages"
    payload = {
        "wiki_page": {"title": page_title, "body": page_body, "published": PUBLISHED}
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json() if resp.status_code in [200, 201] else None


def add_page_to_module(
    module_id, page_title, page_url, canvas_domain, course_id, headers
):
    """Attach an existing wiki page to a Canvas module."""
    url = (
        f"https://{canvas_domain}/api/v1/courses/{course_id}/modules/{module_id}/items"
    )
    payload = {
        "module_item": {
            "title": page_title,
            "type": "Page",
            "page_url": page_url,
            "published": PUBLISHED,
        }
    }
    return requests.post(url, headers=headers, json=payload).json()


# ------------------------------------------------------------------------------
# Main Streamlit UI logic
# ------------------------------------------------------------------------------
def main():
    st.title(APP_TITLE)
    st.markdown(APP_INTRO)
    st.markdown(APP_HOW_IT_WORKS)

    st.header("Step 1: Provide Canvas Page Details")
    module_title = st.text_input("Module Title:")
    page_title = st.text_input("Page Title:")
    uploaded_files = st.file_uploader(
        "Upload DOCX or PDF files", type=["docx", "pdf"], accept_multiple_files=True
    )

    uploaded_text = (
        extract_text_from_uploaded_files(uploaded_files) if uploaded_files else ""
    )
    if uploaded_text:
        st.subheader("Extracted Content")
        st.text_area("Extracted Text", uploaded_text, height=300)

    st.header("Step 2: Generate HTML")
    if st.button("Generate HTML"):
        if not module_title or not page_title or not uploaded_text:
            st.error("Please provide all inputs before generating HTML.")
        else:
            prompt = (
                f"Module: {module_title}\nPage: {page_title}\nContent:\n{uploaded_text}"
            )
            ai_html = get_ai_generated_html(prompt)
            if ai_html:
                st.text_area("AI-Generated HTML Output", ai_html, height=300)
                st.session_state.ai_html = ai_html

    st.header("Step 3: Push to Canvas")
    if st.session_state.get("ai_html"):
        if st.button("Push to Canvas"):
            canvas_domain = os.getenv("CANVAS_DOMAIN") or st.secrets.get(
                "CANVAS_DOMAIN"
            )
            course_id = os.getenv("CANVAS_ID") or st.secrets.get("CANVAS_ID")
            access_token = os.getenv("CANVAS_ACCESS_TOKEN") or st.secrets.get(
                "CANVAS_ACCESS_TOKEN"
            )

            if not all([canvas_domain, course_id, access_token]):
                st.error(
                    "Missing Canvas credentials. Configure domain, course ID, and token."
                )
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            module_id = create_module(module_title, canvas_domain, course_id, headers)
            if not module_id:
                st.error("Module creation failed.")
                return

            page_data = create_wiki_page(
                page_title, st.session_state.ai_html, canvas_domain, course_id, headers
            )
            if not page_data:
                st.error("Page creation failed.")
                return

            page_url = page_data.get("url") or page_title.lower().replace(" ", "-")
            add_page_to_module(
                module_id, page_title, page_url, canvas_domain, course_id, headers
            )
            st.success(
                f"✅ Successfully pushed '{page_title}' to Canvas module '{module_title}'."
            )


# ------------------------------------------------------------------------------
# Sidebar controls and app entrypoint
# ------------------------------------------------------------------------------
SIDEBAR_HIDDEN = True
st.sidebar.button(
    "Logout", on_click=lambda: st.session_state.update({"authenticated": False})
)

if __name__ == "__main__":
    main()
