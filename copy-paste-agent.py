import os
import re
import sys
import time
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import streamlit as st
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pandas as pd

# =========================
# Streamlit Config
# =========================
st.set_page_config(page_title="Coursera → Doc Agent", page_icon="📋", layout="wide")
st.title("📋 Coursera → Google Doc (agentic copy‑paste)")
st.caption(
    "Works in two modes: Local (uses your Chrome profile) or Cloud (headless Chromium with CAUTH cookie).\n"
    "Traverses the /teach/.../content/edit UI, clicks each item, extracts text (DOM or selection fallback), and exports a .docx."
)

COURSE_EDIT_TMPL = "https://www.coursera.org/teach/{slug}/content/edit"

# =========================
# Data Models
# =========================
@dataclass
class ItemRecord:
    module_index: int
    module_title: str
    item_index: int
    item_type: str
    item_title: str
    content_text: str

@dataclass
class RunResult:
    course_slug: str
    items: List[ItemRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

# =========================
# Playwright bootstrap (self‑healing)
# =========================

def ensure_playwright():
    """Import Playwright; if missing, pip‑install it; ensure Chromium is available."""
    try:
        import playwright  # noqa: F401
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright==1.46.0"])  # pin for stability
        except Exception as e:
            st.error(f"Failed to pip‑install playwright: {e}")
            st.stop()
    try:
        # Ensure Chromium is installed (no‑op if present)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception:
        # Ignore if already present; Cloud may have it prebuilt via packages.txt
        pass
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError  # type: ignore
    return sync_playwright, PWTimeoutError

# =========================
# Shadow‑DOM helpers (executed in page)
# =========================

def deep_query_eval_script() -> str:
    return (
        """
        (function() {
          function allDeepChildren(root) {
            const out = [];
            function walk(node) {
              out.push(node);
              if (node.shadowRoot) {
                Array.from(node.shadowRoot.children).forEach(walk);
              }
              Array.from(node.children).forEach(walk);
            }
            walk(root);
            return out;
          }
          function text(el) {
            return (el && (el.textContent || "")).trim().replace(/\s+\n/g, "\n").replace(/[ \t]+/g," ").trim();
          }
          const root = document.documentElement;
          const nodes = allDeepChildren(root);
          const moduleRows = nodes.filter(n => n.getAttribute && (
            n.getAttribute("data-e2e") === "module-row" ||
            n.getAttribute("data-e2e") === "content-module" ||
            (n.className && String(n.className).match(/module/i))
          ));
          const outline = [];
          for (const m of moduleRows) {
            const kids = allDeepChildren(m);
            const titleEl = kids.find(k => k.getAttribute && (
              k.getAttribute("data-e2e") === "module-title" ||
              k.getAttribute("data-e2e") === "editable-title" ||
              k.tagName === "H2" || k.tagName === "H3"
            )) || m;
            const moduleTitle = (text(titleEl) || "Untitled Module").replace(/^\s*Module\s*:\s*/i, "");
            const itemNodes = kids.filter(k => k.getAttribute && (
              k.getAttribute("data-e2e") === "module-item" ||
              k.getAttribute("data-e2e") === "content-item" ||
              String(k.className||"").match(/(module|content)[-_ ]item/i)
            ));
            const uniqueItems = Array.from(new Set(itemNodes));
            const items = [];
            uniqueItems.forEach((it, idx) => {
              const leafKids = allDeepChildren(it);
              const titleCand = leafKids.find(a => a.getAttribute && (
                a.getAttribute("data-e2e") === "item-title" ||
                a.getAttribute("data-e2e") === "editable-title" ||
                a.tagName === "H4" || a.tagName === "H5" || a.tagName === "A" || a.tagName === "DIV"
              )) || it;
              const t = text(titleCand) || `Item ${idx+1}`;
              const lower = t.toLowerCase();
              let itype = "page";
              if (lower.match(/quiz|knowledge\s*check|assessment/)) itype = "quiz";
              else if (lower.match(/assignment|graded/)) itype = "assignment";
              else if (lower.match(/discussion/)) itype = "discussion";
              else if (lower.match(/video|lecture/)) itype = "video";
              items.push({ title: t, type: itype, indexHint: idx });
            });
            outline.push({ moduleTitle, items });
          }
          return outline;
        })();
        """
    )


def grab_visible_text_script() -> str:
    return (
        """
        (function(){
          function allDeep(root) {
            const out=[]; 
            function walk(n){ 
              out.push(n); 
              if(n.shadowRoot){ Array.from(n.shadowRoot.children).forEach(walk); }
              Array.from(n.children).forEach(walk);
            }
            walk(root); return out;
          }
          const nodes = allDeep(document.documentElement);
          function scoreNode(n){
            const style = window.getComputedStyle(n);
            if (style && (style.visibility === "hidden" || style.display === "none")) return 0;
            let t = (n.innerText || "").trim();
            if (!t) return 0;
            const tag = (n.tagName || "").toLowerCase();
            if (["nav","header","footer","button"].includes(tag)) return 0;
            const cls = (n.className || "").toString().toLowerCase();
            if (cls.match(/toolbar|menu|aside|toast|modal|breadcrumb/)) return 0;
            let base = t.length;
            if (n.getAttribute && n.getAttribute("contenteditable") == "true") base *= 1.5;
            if (["article","main","section"].includes(tag)) base *= 1.3;
            return base;
          }
          let best = null; let bestScore = 0;
          for (const n of nodes) {
            const sc = scoreNode(n);
            if (sc > bestScore) { best = n; bestScore = sc; }
          }
          const txt = best ? (best.innerText || "").trim() : "";
          return txt.replace(/\n{3,}/g, "\n\n");
        })();
        """
    )


def grab_selection_text_script() -> str:
    return (
        """
        (function(){
          try {
            const sel = window.getSelection();
            sel.removeAllRanges();
            const range = document.createRange();
            range.selectNodeContents(document.body);
            sel.addRange(range);
            const txt = sel.toString() || "";
            sel.removeAllRanges();
            return txt.trim();
          } catch(e) { return ""; }
        })();
        """
    )

# =========================
# Misc helpers
# =========================

def parse_slug_from_input(user_input: str) -> str:
    url = user_input.strip().strip('"')
    m = re.search(r"/teach/([\w\-]+)/content/edit", url)
    if m:
        return m.group(1)
    return url.split("?")[0].split("/")[-1]


def wait_for_editor_ready(page, ms: int = 900):
    time.sleep(ms / 1000.0)
    try:
        page.mouse.wheel(0, 420)
        time.sleep(0.2)
    except Exception:
        pass


def export_docx(run: RunResult, outfile: str) -> str:
    doc = Document()
    h = doc.add_heading(f"Coursera Export: {run.course_slug}", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph("")

    current_module = None
    for rec in run.items:
        if rec.module_title != current_module:
            doc.add_heading(f"Module {rec.module_index}: {rec.module_title}", level=1)
            current_module = rec.module_title
        doc.add_heading(f"{rec.item_type.title()}: {rec.item_title}", level=2)
        if rec.content_text.strip():
            p = doc.add_paragraph(rec.content_text.strip())
            p.paragraph_format.space_after = Pt(6)
        else:
            doc.add_paragraph("[Captured title only or non-text content (quiz/LTI/external).]")
        doc.add_paragraph("")

    doc.save(outfile)
    return outfile

# =========================
# Agents (Local & Cloud)
# =========================

def run_agent_local(slug: str, chrome_profile: str, max_items: Optional[int], use_selection_fallback: bool) -> RunResult:
    sync_playwright, PWTimeoutError = ensure_playwright_installed = ensure_playwright()
    result = RunResult(course_slug=slug)
    edit_url = COURSE_EDIT_TMPL.format(slug=slug)

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            result.errors.append("Failed to open Chrome profile. Close all Chrome windows and retry. Details: " + str(e))
            return result

        page = ctx.new_page()
        try:
            page.goto(edit_url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as e:
            result.errors.append(f"Failed to open {edit_url}: {e}")
            ctx.close();
            return result

        page.wait_for_timeout(4000)
        try:
            outline = page.evaluate(deep_query_eval_script())
        except Exception as e:
            result.errors.append("Failed to build outline (shadow DOM). Details: " + str(e))
            ctx.close();
            return result

        count = 0
        for m_i, mod in enumerate(outline, start=1):
            module_title = mod.get("moduleTitle", f"Module {m_i}")
            for it_i, item in enumerate(mod.get("items", []), start=1):
                if max_items and count >= max_items:
                    break
                title = item.get("title", f"Item {it_i}")
                itype = item.get("type", "page")

                clicked = False
                try:
                    page.get_by_text(title, exact=False).first.click(timeout=7_000)
                    clicked = True
                except PWTimeoutError:
                    try:
                        page.mouse.wheel(0, 800)
                        page.get_by_text(title, exact=False).first.click(timeout=7_000)
                        clicked = True
                    except Exception:
                        result.errors.append("Could not click item: " + title)
                        clicked = False

                wait_for_editor_ready(page)

                content_text = ""
                if clicked:
                    try:
                        content_text = page.evaluate(grab_visible_text_script()) or ""
                    except Exception:
                        content_text = ""

                    if use_selection_fallback and len(content_text.strip()) < 40:
                        try:
                            content_text = page.evaluate(grab_selection_text_script()) or content_text
                        except Exception:
                            pass

                result.items.append(ItemRecord(
                    module_index=m_i,
                    module_title=module_title,
                    item_index=it_i,
                    item_type=itype,
                    item_title=title,
                    content_text=content_text,
                ))
                count += 1
            if max_items and count >= max_items:
                break

        ctx.close()
        return result


def run_agent_cloud(slug: str, cauth_cookie: Optional[str], max_items: Optional[int], use_selection_fallback: bool) -> RunResult:
    sync_playwright, PWTimeoutError = ensure_playwright()
    result = RunResult(course_slug=slug)
    edit_url = COURSE_EDIT_TMPL.format(slug=slug)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        try:
            if cauth_cookie:
                ctx.add_cookies([
                    {"name": "CAUTH", "value": cauth_cookie, "domain": ".coursera.org", "path": "/", "httpOnly": True, "secure": True}
                ])
        except Exception:
            result.errors.append("Failed to set CAUTH cookie. Use a fresh value.")

        page = ctx.new_page()
        try:
            page.goto(edit_url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as e:
            result.errors.append(f"Failed to open {edit_url}: {e}")
            ctx.close(); browser.close();
            return result

        page.wait_for_timeout(4000)
        if "login" in (page.url or "").lower():
            result.errors.append("Not authenticated. Provide a CAUTH cookie in the sidebar.")
            ctx.close(); browser.close();
            return result

        try:
            outline = page.evaluate(deep_query_eval_script())
        except Exception as e:
            result.errors.append("Failed to build outline (shadow DOM). Details: " + str(e))
            ctx.close(); browser.close();
            return result

        count = 0
        for m_i, mod in enumerate(outline, start=1):
            module_title = mod.get("moduleTitle", f"Module {m_i}")
            for it_i, item in enumerate(mod.get("items", []), start=1):
                if max_items and count >= max_items:
                    break
                title = item.get("title", f"Item {it_i}")
                itype = item.get("type", "page")

                clicked = False
                try:
                    page.get_by_text(title, exact=False).first.click(timeout=7_000)
                    clicked = True
                except PWTimeoutError:
                    try:
                        page.mouse.wheel(0, 800)
                        page.get_by_text(title, exact=False).first.click(timeout=7_000)
                        clicked = True
                    except Exception:
                        result.errors.append("Could not click item: " + title)
                        clicked = False

                wait_for_editor_ready(page)

                content_text = ""
                if clicked:
                    try:
                        content_text = page.evaluate(grab_visible_text_script()) or ""
                    except Exception:
                        content_text = ""

                    if use_selection_fallback and len(content_text.strip()) < 40:
                        try:
                            content_text = page.evaluate(grab_selection_text_script()) or content_text
                        except Exception:
                            pass

                result.items.append(ItemRecord(
                    module_index=m_i,
                    module_title=module_title,
                    item_index=it_i,
                    item_type=itype,
                    item_title=title,
                    content_text=content_text,
                ))
                count += 1
            if max_items and count >= max_items:
                break

        ctx.close(); browser.close()
        return result

# =========================
# UI
# =========================
mode = st.sidebar.radio("Run mode", ["Local (Chrome profile)", "Streamlit Cloud (headless)"])
course_input = st.text_input(
    "Coursera course URL or slug",
    value="technical-assessment-testing-sandbox",
    help="Paste the full /teach/.../content/edit URL or just the course slug.",
)
slug = parse_slug_from_input(course_input)

max_items = st.sidebar.number_input("Limit items (0 = all)", min_value=0, max_value=10000, value=0, step=1)
use_selection = st.sidebar.checkbox("Enable selection fallback (no clipboard)", value=True)
export_name = st.sidebar.text_input("Output .docx name", value="coursera_export.docx")

if mode.startswith("Local"):
    default_profile = os.path.expanduser(r"~\\AppData\\Local\\Google\\Chrome\\User Data")
    chrome_profile = st.text_input(
        "Chrome User Data directory (local only)",
        value=default_profile,
        help="Close all Chrome windows before running. Uses your logged‑in profile for SSO.",
    )
else:
    chrome_profile = ""

if mode.startswith("Streamlit"):
    with st.expander("Advanced auth (Cloud)"):
        st.markdown("Paste your Coursera **CAUTH** cookie (DevTools → Application → Cookies → coursera.org). Treat it like a password.")
        cauth_cookie = st.text_input("CAUTH cookie", type="password")
else:
    cauth_cookie = None

run_btn = st.button("▶️ Run Agent", type="primary")

# =========================
# Exec
# =========================
if run_btn:
    if not slug:
        st.error("Please enter a course URL or slug.")
        st.stop()

    limit = max_items or None

    if mode.startswith("Local"):
        if not os.path.isdir(chrome_profile):
            st.error("Chrome profile path doesn't exist. Check the directory.")
            st.stop()
        with st.status("Running locally…", expanded=True) as status:
            st.write(f"Course: **{slug}**  |  Profile: `{chrome_profile}`")
            rr = run_agent_local(slug, chrome_profile, limit, use_selection)
            if rr.errors:
                st.warning("Some issues were reported:")
                for e in rr.errors:
                    st.write("• " + e)
            st.write(f"Captured **{len(rr.items)}** items.")
            status.update(label="Exporting .docx…", state="running")
    else:
        with st.status("Running headless on Cloud…", expanded=True) as status:
            st.write(f"Course: **{slug}**")
            if not cauth_cookie:
                st.error("Not authenticated. Provide a CAUTH cookie in the sidebar.")
                st.stop()
            rr = run_agent_cloud(slug, cauth_cookie, limit, use_selection)
            if rr.errors:
                st.warning("Some issues were reported:")
                for e in rr.errors:
                    st.write("• " + e)
            st.write(f"Captured **{len(rr.items)}** items.")
            status.update(label="Exporting .docx…", state="running")

    # Export
    outfile = export_docx(rr, export_name)
    with open(outfile, "rb") as f:
        st.download_button(
            label="⬇️ Download .docx",
            data=f.read(),
            file_name=os.path.basename(outfile),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    # Preview
    st.subheader("Preview")
    df = pd.DataFrame([
        {
            "Module #": it.module_index,
            "Module": it.module_title,
            "Type": it.item_type,
            "Title": it.item_title,
            "Snippet": (it.content_text[:180] + ("…" if len(it.content_text) > 180 else "")).replace("\n", " ")
        }
        for it in rr.items
    ])
    st.dataframe(df, use_container_width=True)

    st.info("Upload the .docx to Google Drive and open as Google Doc. For direct Docs API export, I can wire OAuth next.")

# =========================
# Deploy notes (optional)
# =========================
st.markdown(
    """
---
### Setup (Local)
```powershell
pip install streamlit playwright python-docx pandas
python -m playwright install chrome
streamlit run app.py
```

### Setup (Streamlit Cloud)
- **requirements.txt**
```
streamlit>=1.36
playwright==1.46.0
python-docx>=1.1
pandas>=2.2
```
- **packages.txt** (Chromium libs)
```
libnss3
libnspr4
libatk1.0-0
libatk-bridge2.0-0
libdrm2
libxcomposite1
libxdamage1
libxfixes3
libgbm1
libpango-1.0-0
libasound2
libatspi2.0-0
libxrandr2
libgtk-3-0
libxkbcommon0
libx11-xcb1
libxcb1
```
- The app will attempt runtime `pip install playwright` and `playwright install chromium` if needed.
    """
)
