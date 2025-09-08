import re
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pyperclip

# -------------------------
# Streamlit Page Config
# -------------------------
st.set_page_config(page_title="Coursera → Doc Agent", page_icon="📋", layout="wide")
st.title("📋 Coursera → Google Doc (copy‑paste) Agent")
st.caption("Headful Playwright + your Chrome profile. Automates clicking each item, extracting text, and building a .docx you can import into Google Docs.")

# -------------------------
# Utilities
# -------------------------
COURSE_EDIT_TMPL = "https://www.coursera.org/teach/{slug}/content/edit"

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


def parse_slug_from_input(user_input: str) -> str:
    """Accepts a full /teach/.../content/edit URL or a bare slug and returns slug."""
    url = user_input.strip().strip('"')
    m = re.search(r"/teach/([\w\-]+)/content/edit", url)
    if m:
        return m.group(1)
    # If it's just a slug-looking string
    return url.split("?")[0].split("/")[-1]


def deep_query_eval_script() -> str:
    return r"""
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


def grab_visible_text_script() -> str:
    return r"""
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


def wait_for_editor_ready(page, ms: int = 800):
    time.sleep(ms / 1000.0)
    try:
        page.mouse.wheel(0, 300)
        time.sleep(0.2)
    except Exception:
        pass


def export_docx(run: RunResult, outfile: str) -> str:
    doc = Document()
    styles = doc.styles
    # Title
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
            p_format = p.paragraph_format
            p_format.space_after = Pt(6)
        else:
            doc.add_paragraph("[Captured title only or non-text content (quiz/LTI/external).]")
        doc.add_paragraph("")

    doc.save(outfile)
    return outfile


def run_agent(course_input: str, chrome_profile: str, max_items: Optional[int] = None, use_copy_fallback: bool = True) -> RunResult:
    slug = parse_slug_from_input(course_input)
    result = RunResult(course_slug=slug)
    edit_url = COURSE_EDIT_TMPL.format(slug=slug)

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile,
                channel="chrome",  # Use real Chrome for existing login
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            result.errors.append(f"Failed to open Chrome profile. Close all Chrome windows and retry. Details: {e}")
            return result

        page = ctx.new_page()
        try:
            page.goto(edit_url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as e:
            result.errors.append(f"Failed to open {edit_url}: {e}")
            ctx.close()
            return result

        # Give the SPA time to boot
        page.wait_for_timeout(4000)

        try:
            outline = page.evaluate(deep_query_eval_script())
        except Exception as e:
            result.errors.append(f"Failed to build outline (shadow DOM traversal). Details: {e}")
            ctx.close()
            return result

        count = 0
        for m_i, mod in enumerate(outline, start=1):
            module_title = mod.get("moduleTitle", f"Module {m_i}")
            items = mod.get("items", [])
            for it_i, item in enumerate(items, start=1):
                if max_items and count >= max_items:
                    break
                title = item.get("title", f"Item {it_i}")
                itype = item.get("type", "page")

                # Try to click by visible text
                clicked = False
                try:
                    page.get_by_text(title, exact=False).first.click(timeout=7_000)
                    clicked = True
                except PWTimeoutError:
                    # Try scrolling and retry
                    try:
                        page.mouse.wheel(0, 800)
                        page.get_by_text(title, exact=False).first.click(timeout=7_000)
                        clicked = True
                    except Exception:
                        result.errors.append(f"Could not click item: {title}")
                        clicked = False

                wait_for_editor_ready(page)

                # Capture content
                content_text = ""
                if clicked:
                    try:
                        content_text = page.evaluate(grab_visible_text_script()) or ""
                    except Exception:
                        content_text = ""

                    # If DOM text is tiny, try copy‑paste fallback
                    if use_copy_fallback and len(content_text.strip()) < 40:
                        try:
                            # Focus body and select all → copy
                            page.focus("body")
                            page.keyboard.down("Control")
                            page.keyboard.press("KeyA")
                            page.keyboard.press("KeyC")
                            page.keyboard.up("Control")
                            time.sleep(0.3)
                            cp = pyperclip.paste() or ""
                            # Heuristic: if clipboard is much bigger, use it
                            if len(cp.strip()) > len(content_text.strip()):
                                content_text = cp
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


# -------------------------
# Sidebar Controls
# -------------------------
st.sidebar.header("Settings")
course_input = st.text_input(
    "Coursera course URL or slug",
    value="technical-assessment-testing-sandbox",
    help="Paste the full /teach/.../content/edit URL or just the course slug.",
)

default_profile = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data")
chrome_profile = st.text_input(
    "Chrome User Data directory",
    value=default_profile,
    help="Close all Chrome windows before running. Uses your logged‑in Chrome profile for SSO.",
)

colA, colB, colC = st.columns([1,1,1])
with colA:
    max_items = st.number_input("Limit items (0 = all)", min_value=0, max_value=10_000, value=0, step=1)
with colB:
    use_copy = st.checkbox("Enable copy‑paste fallback", value=True)
with colC:
    export_name = st.text_input("Output .docx name", value="coursera_export.docx")

run_btn = st.button("▶️ Run Agent", type="primary")

log_box = st.container(border=True)
result_holder = st.empty()

# -------------------------
# Run
# -------------------------
if run_btn:
    if not course_input.strip():
        st.error("Please enter a course URL or slug.")
    elif not os.path.isdir(chrome_profile):
        st.error("Chrome profile path doesn't exist. Check the directory.")
    else:
        with st.status("Launching Chrome and building outline…", expanded=True) as status:
            st.write(f"Target: **{course_input}**")
            st.write(f"Chrome profile: `{chrome_profile}`")
            try:
                rr = run_agent(course_input, chrome_profile, max_items or None, use_copy)
            except Exception as e:
                st.exception(e)
                st.stop()

            if rr.errors:
                st.warning("Some steps reported issues:")
                for e in rr.errors:
                    st.write("• " + e)

            st.write(f"Captured **{len(rr.items)}** items.")
            status.update(label="Exporting .docx…", state="running")

        # Export docx
        outfile = export_docx(rr, export_name)
        with open(outfile, "rb") as f:
            st.download_button(
                label="⬇️ Download .docx",
                data=f.read(),
                file_name=os.path.basename(outfile),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # Quick preview table
        st.subheader("Preview")
        import pandas as pd
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

        st.info("Upload the .docx to Google Drive and open as Google Doc, or import into Docs. If you want a Google Docs direct export with OAuth, I can add it next.")

# -------------------------
# Footer Help
# -------------------------
st.markdown(
    """
---
**Setup notes**

1. Install dependencies (PowerShell):
   ```powershell
   pip install streamlit playwright python-docx pyperclip
   python -m playwright install chrome
   ```
2. Close **all** Chrome windows before running (profile lock).
3. Start the app:
   ```powershell
   streamlit run app.py
   ```
4. Paste your course slug (or full /teach/.../content/edit URL), confirm your Chrome profile path, and click **Run Agent**.

**How it works**
- Opens your course editor with your real Chrome profile.
- Traverses the Shadow DOM to list modules & items.
- Clicks each item → grabs visible text. If DOM text is tiny, tries a **copy‑paste** fallback (Ctrl+A/Ctrl+C) and reads from your clipboard.
- Builds a structured .docx you can import to Google Docs.

**Limitations**
- Quizzes/LTI/external embeds may not expose text → you'll still get titles.
- If the Coursera UI changes significantly, update selectors in `deep_query_eval_script()`.
    """
)
