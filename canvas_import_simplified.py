# ------------------------------------------------------------------------------
# Refactor date: 2025-11-12
# Refactored by: Imaad Fakier
# Purpose: Align Canvas Import micro-app with OES GenAI Streamlit app standards.
# ------------------------------------------------------------------------------
#!/usr/bin/env python3
"""
Canvas Import Utility (Simplified)
----------------------------------
Lightweight Streamlit app for converting uploaded DOCX or PDF files to HTML
and publishing directly to Canvas LMS.

Intended for internal operations or content teams who already have access
to the Streamlit environment (no access gate or SHA-256 auth).

Key Features:
- Upload DOCX or PDF files and extract text.
- Optionally generate formatted HTML using OpenAI GPT-4o.
- Push generated content directly to Canvas modules and pages.

Requirements:
    - streamlit
    - requests
    - python-docx
    - pypdf
"""

import os
import requests
import streamlit as st

# Optional OpenAI integration
try:
    import openai
except ImportError:
    openai = None

# ------------------------------------------------------------------------------
# App metadata
# ------------------------------------------------------------------------------
PUBLISHED = True
APP_URL = "https://alt-text-bot.streamlit.app/"
APP_TITLE = "Construct HTML Generator"
APP_INTRO = "Convert DOCX or PDF content into HTML and push to Canvas."
APP_HOW_IT_WORKS = """
1. Upload one or more DOCX or PDF files.
2. The app extracts their content and optionally generates HTML using GPT-4o.
3. You can then push the resulting page directly to a Canvas course.
"""
SYSTEM_PROMPT = (
    "Convert the given raw course content into clean, readable HTML suitable for Canvas. "
    "Do not include <!DOCTYPE> or <html> tags — output only the body content."
)


# ------------------------------------------------------------------------------
# File text extraction
# ------------------------------------------------------------------------------
def extract_text_from_uploaded_files(files):
    """Extract text from DOCX or PDF files."""
    texts = []
    for file in files:
        ext = file.name.split(".")[-1].lower()
        try:
            if ext == "docx":
                from docx import Document

                doc = Document(file)
                text = "\n".join(p.text for p in doc.paragraphs)
                texts.append(text)
            elif ext == "pdf":
                from pypdf import PdfReader

                reader = PdfReader(file)
                text = "".join(page.extract_text() or "" for page in reader.pages)
                texts.append(text)
            else:
                texts.append(file.read().decode("utf-8"))
        except Exception as e:
            texts.append(f"[Error reading {file.name}: {e}]")
    return "\n".join(texts)


# ------------------------------------------------------------------------------
# OpenAI HTML generation
# ------------------------------------------------------------------------------
def get_ai_generated_html(prompt):
    """Generate HTML via OpenAI GPT-4o."""
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        st.error("Missing OpenAI API key in Streamlit secrets.")
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
# Canvas API helpers
# ------------------------------------------------------------------------------
def create_module(module_name, canvas_domain, course_id, headers):
    """Create a new Canvas module."""
    url = f"https://{canvas_domain}/api/v1/courses/{course_id}/modules"
    payload = {"module": {"name": module_name, "published": PUBLISHED}}
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json().get("id") if resp.status_code in [200, 201] else None


def create_wiki_page(page_title, page_body, canvas_domain, course_id, headers):
    """Create a Canvas page."""
    url = f"https://{canvas_domain}/api/v1/courses/{course_id}/pages"
    payload = {
        "wiki_page": {"title": page_title, "body": page_body, "published": PUBLISHED}
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json() if resp.status_code in [200, 201] else None


def add_page_to_module(
    module_id, page_title, page_url, canvas_domain, course_id, headers
):
    """Attach an existing page to a Canvas module."""
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
# Main Streamlit app
# ------------------------------------------------------------------------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="centered")
    st.title(APP_TITLE)
    st.markdown(APP_INTRO)
    st.markdown(APP_HOW_IT_WORKS)

    # Step 1: File upload
    st.header("Step 1: Upload Files")
    module_title = st.text_input("Canvas Module Title:")
    page_title = st.text_input("Page Title:")
    files = st.file_uploader(
        "Upload DOCX or PDF", type=["docx", "pdf"], accept_multiple_files=True
    )

    extracted_text = extract_text_from_uploaded_files(files) if files else ""
    if extracted_text:
        st.subheader("Extracted Text")
        st.text_area("Preview", extracted_text, height=300)

    # Step 2: Generate HTML (optional)
    st.header("Step 2: Generate HTML")
    if st.button("Generate HTML"):
        if not module_title or not page_title or not extracted_text:
            st.error("Please fill all fields and upload a file.")
        else:
            prompt = f"Module: {module_title}\nPage: {page_title}\nContent:\n{extracted_text}"
            ai_html = get_ai_generated_html(prompt)
            if ai_html:
                st.text_area("AI-Generated HTML", ai_html, height=300)
                st.session_state.ai_html = ai_html

    # Step 3: Push to Canvas
    st.header("Step 3: Push to Canvas")
    if st.session_state.get("ai_html"):
        if st.button("Push to Canvas"):
            domain = st.secrets.get("CANVAS_DOMAIN")
            course_id = st.secrets.get("CANVAS_ID")
            token = st.secrets.get("CANVAS_ACCESS_TOKEN")

            if not all([domain, course_id, token]):
                st.error("Missing Canvas credentials in Streamlit secrets.")
                return

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            module_id = create_module(module_title, domain, course_id, headers)
            if not module_id:
                st.error("Module creation failed.")
                return

            page_data = create_wiki_page(
                page_title, st.session_state.ai_html, domain, course_id, headers
            )
            if not page_data:
                st.error("Page creation failed.")
                return

            page_url = page_data.get("url") or page_title.lower().replace(" ", "-")
            add_page_to_module(
                module_id, page_title, page_url, domain, course_id, headers
            )
            st.success(
                f"✅ Successfully added '{page_title}' to Canvas module '{module_title}'."
            )


if __name__ == "__main__":
    main()
