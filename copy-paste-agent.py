import os
import re
import sys
import json
import time
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import streamlit as st
import pandas as pd
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ===============
# Page config
# ===============
st.set_page_config(page_title="Coursera → Google Doc (Agentic)", page_icon="🤖", layout="wide")
st.title("🤖 Coursera → Google Doc — Agentic Exporter")
st.caption("GPT function-calling orchestrates Playwright to click through your Coursera course and build a .docx ready for Google Docs.")

COURSE_EDIT_TMPL = "https://www.coursera.org/teach/{slug}/content/edit"

# ===============
# Models / state
# ===============
@dataclass
class ItemRecord:
    module_index: int
    module_title: str
    item_index: int
    item_type: str
    item_title: str
    content_text: str

@dataclass
class RunState:
    course_slug: str
    items: List[ItemRecord] = field(default_factory=list)
    seen_titles: set = field(default_factory=set)
    errors: List[str] = field(default_factory=list)

# ===============
# Playwright bootstrap (self-healing)
# ===============

def ensure_playwright():
    """Import Playwright; if missing, pip-install it; ensure Chromium is available."""
    try:
        import playwright  # noqa: F401
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright==1.46.0"])  # stable pin
        except Exception as e:
            st.error(f"Failed to install Playwright: {e}")
            st.stop()
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception:
        pass
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError  # type: ignore
    return sync_playwright, PWTimeoutError

# ===============
# JS utilities injected in page
# ===============

def js_all_in_one() -> str:
    return r"""
    (function(){
      function allDeepChildren(root) { const out=[]; function w(n){ out.push(n); if(n && n.shadowRoot){ Array.from(n.shadowRoot.children).forEach(w); } if(n && n.children){ Array.from(n.children).forEach(w); } } w(root||document.documentElement); return out; }
      function text(el){ try{ return (el && (el.textContent||'')).replace(/\u00A0/g,' ').replace(/\s+\n/g,'\n').replace(/[ \t]+/g,' ').trim(); }catch(e){ return ''; } }
      function vis(n){ try{ const s=getComputedStyle(n); return s && s.visibility!=='hidden' && s.display!=='none'; }catch(e){ return false; } }
      function hasScroll(n){ try{ return n && (n.scrollHeight > n.clientHeight+30) && (getComputedStyle(n).overflowY||'').match(/auto|scroll/); }catch(e){return false;} }

      function deepOutlineOnce(){
        const nodes = allDeepChildren(document.documentElement);
        const moduleRows = nodes.filter(n => n.getAttribute && (
          n.getAttribute('data-e2e')==='module-row' || n.getAttribute('data-e2e')==='content-module' || (''+(n.className||'')).match(/\bmodule\b/i)
        ));
        const outline=[];
        for(const m of moduleRows){
          const kids = allDeepChildren(m);
          const titleEl = kids.find(k => k.getAttribute && (k.getAttribute('data-e2e')==='module-title' || k.getAttribute('data-e2e')==='editable-title' || k.tagName==='H2' || k.tagName==='H3')) || m;
          const moduleTitle = (text(titleEl)||'Untitled Module').replace(/^\s*Module\s*:\s*/i,'');
          const itemNodes = kids.filter(k => k.getAttribute && (k.getAttribute('data-e2e')==='module-item' || k.getAttribute('data-e2e')==='content-item' || (''+(k.className||'')).match(/(module|content)[-_ ]item/i)));
          const uniq = Array.from(new Set(itemNodes));
          const items=[];
          uniq.forEach((it,idx)=>{
            const leaf = allDeepChildren(it).find(a => a.getAttribute && (a.getAttribute('data-e2e')==='item-title' || a.getAttribute('data-e2e')==='editable-title' || a.tagName==='H4' || a.tagName==='H5' || a.tagName==='A' || a.tagName==='DIV')) || it;
            const t = text(leaf) || `Item ${idx+1}`;
            const lower = t.toLowerCase();
            let ty='page';
            if(/quiz|knowledge\s*check|assessment/.test(lower)) ty='quiz'; else if(/assignment|graded/.test(lower)) ty='assignment'; else if(/discussion/.test(lower)) ty='discussion'; else if(/video|lecture/.test(lower)) ty='video';
            items.push({title:t, type:ty});
          });
          if(items.length) outline.push({moduleTitle, items});
        }
        return outline;
      }

      function guessScrollContainer(){
        const cands = allDeepChildren(document.documentElement).filter(n=>hasScroll(n) && vis(n) && n.clientHeight>300);
        function score(n){ const kids=n.querySelectorAll('[role=listitem],[data-e2e],a,h2,h3,h4'); return (n.clientHeight||0) + kids.length*5; }
        let best=null,b=0; cands.forEach(n=>{ const s=score(n); if(s>b){best=n;b=s;} });
        return best || document.scrollingElement || document.documentElement;
      }

      function collectVisiblePairs(){
        const nodes=allDeepChildren(document.documentElement); const out=[];
        function isItem(n){ try{ const de=(n.getAttribute && (n.getAttribute('data-e2e')||''))||''; const cls=(''+(n.className||'')); const role=(n.getAttribute && (n.getAttribute('role')||''))||''; if(/module-item|content-item|item-row|curriculum-item/i.test(de)) return true; if(/(module|content)[-_ ]item|itemRow|curriculum-item|lesson[-_ ]item|rc-Item/i.test(cls)) return true; if(role==='listitem' && /(item|lesson|unit|content|resource)/i.test(cls)) return true; return false; }catch(e){return false;} }
        function findTitle(n){ const el=n.querySelector('[data-e2e="item-title"],[data-e2e="editable-title"],a,h4,h5,[role=button],div'); return text(el||n).slice(0,200); }
        function findModule(n){ let cur=n; for(let i=0;i<8 && cur;i++){ if(cur.getAttribute){ const de=(cur.getAttribute('data-e2e')||''); const cls=(''+(cur.className||'')); if(/module-row|content-module|module-container|rc-Module/i.test(de+" "+cls)){ const h=cur.querySelector('[data-e2e="module-title"],[data-e2e="editable-title"],h2,h3'); const t=text(h||cur); if(t) return t; } } cur=cur.parentElement; } const hs=[...document.querySelectorAll('h2,h3')]; let best='',top=-1; const r=n.getBoundingClientRect(); hs.forEach(h=>{ const rh=h.getBoundingClientRect(); if(rh.top<r.top && rh.top>top){ top=rh.top; best=text(h); } }); return best||'Untitled Module'; }
        function ty(t){ const l=t.toLowerCase(); if(/quiz|knowledge\s*check|assessment/.test(l)) return 'quiz'; if(/assignment|graded/.test(l)) return 'assignment'; if(/discussion/.test(l)) return 'discussion'; if(/video|lecture/.test(l)) return 'video'; return 'page'; }
        nodes.forEach(n=>{ if(!vis(n) || !isItem(n)) return; const t=findTitle(n); if(!t) return; out.push({moduleTitle:findModule(n), itemTitle:t, itemType:ty(t)}); });
        const seen=new Set(); const dedup=[]; for(const it of out){ const k=it.moduleTitle+'\u0000'+it.itemTitle; if(!seen.has(k)){ seen.add(k); dedup.push(it); } }
        return dedup;
      }

      function mainText(){
        const nodes =(function allDeep(root){ const out=[]; function w(n){ out.push(n); if(n.shadowRoot){Array.from(n.shadowRoot.children).forEach(w);} Array.from(n.children).forEach(w);} w(root||document.documentElement); return out; })(document.documentElement);
        function score(n){ try{ const s=getComputedStyle(n); if(s && (s.visibility==='hidden'||s.display==='none')) return 0; }catch(e){return 0;} const t=(n.innerText||'').trim(); if(!t) return 0; const tag=(n.tagName||'').toLowerCase(); if(['nav','header','footer','button'].includes(tag)) return 0; const cls=(''+(n.className||'')).toLowerCase(); if(/toolbar|menu|aside|toast|modal|breadcrumb/.test(cls)) return 0; let base=t.length; if(n.getAttribute&&n.getAttribute('contenteditable')==='true') base*=1.4; if(['article','main','section'].includes(tag)) base*=1.2; return base; }
        let best=null,bs=0; for(const n of nodes){ const sc=score(n); if(sc>bs){best=n; bs=sc;} }
        return best ? (best.innerText||'').trim().replace(/\n{3,}/g,'\n\n') : '';
      }

      return { deepOutlineOnce, guessScrollContainer, collectVisiblePairs, mainText };
    })();
    """


def js_call(fn: str) -> str:
    return f"""
    (function(){{ const lib = ({js_all_in_one}); return lib.{fn}; }})()
    """.replace("{js_all_in_one}", js_all_in_one())

# ===============
# Outline & capture helpers
# ===============

def wait_ready(page, ms=900):
    time.sleep(ms/1000.0)
    try:
        page.mouse.wheel(0, 400)
    except Exception:
        pass


def build_outline(page, log) -> List[Dict[str, Any]]:
    # A) e2e selectors
    try:
        outline = page.evaluate(js_call("deepOutlineOnce()"))
    except Exception:
        outline = []
    total = sum(len(m.get("items", [])) for m in outline)
    if total:
        log.write(f"Outline via e2e selectors → {total} items")
        return outline

    # B) scroll + visible scan
    log.write("No outline found. Progressive scroll scan…")
    try:
        page.evaluate(
            """
            (function(){ try{ const lib=(%s); const sc = lib.guessScrollContainer(); sc && sc.setAttribute('data-agent-scroll-root','1'); }catch(e){} })();
            """ % js_all_in_one()
        )
    except Exception:
        pass

    seen = []
    seen_keys = set()

    def scroll_down():
        try:
            page.evaluate(
                """
                (function(){ const sc=document.querySelector('[data-agent-scroll-root=\"1\"]') || document.scrollingElement || document.documentElement; sc.scrollBy({top:800,behavior:'auto'}); })();
                """
            )
        except Exception:
            try:
                page.mouse.wheel(0, 800)
            except Exception:
                pass

    for _ in range(24):
        try:
            vis = page.evaluate(js_call("collectVisiblePairs()"))
        except Exception:
            vis = []
        for it in vis:
            key = it.get("moduleTitle","?") + "\u0000" + it.get("itemTitle","?")
            if key not in seen_keys and it.get("itemTitle"):
                seen_keys.add(key)
                seen.append(it)
        scroll_down()
        wait_ready(page, 250)

    # group
    modules: Dict[str, List[Dict[str,str]]] = {}
    for p in seen:
        mt = p.get("moduleTitle") or "Untitled Module"
        modules.setdefault(mt, []).append({"title": p.get("itemTitle"), "type": p.get("itemType","page")})
    outline = [{"moduleTitle": m, "items": items} for m,items in modules.items()]
    log.write(f"Scan result → {sum(len(m['items']) for m in outline)} items across {len(outline)} modules")
    return outline


def click_by_title(page, title: str) -> bool:
    for _ in range(10):
        try:
            page.get_by_text(title, exact=False).first.click(timeout=1200)
            return True
        except Exception:
            try:
                page.evaluate("(function(){ (document.scrollingElement||document.documentElement).scrollBy(0,600); })();")
            except Exception:
                try:
                    page.mouse.wheel(0, 700)
                except Exception:
                    pass
    return False


def capture_text(page) -> str:
    try:
        txt = page.evaluate(js_call("mainText()")) or ""
    except Exception:
        txt = ""
    if len(txt.strip()) < 40:
        try:
            # Select-all fallback (works in headless too by reading selection)
            txt2 = page.evaluate(
                """
                (function(){ try{ const sel=window.getSelection(); sel.removeAllRanges(); const r=document.createRange(); r.selectNodeContents(document.body); sel.addRange(r); const t=sel.toString()||''; sel.removeAllRanges(); return t.trim(); }catch(e){ return ''; } })();
                """
            ) or ""
            if len(txt2.strip()) > len(txt.strip()):
                txt = txt2
        except Exception:
            pass
    return txt

# ===============
# GPT function-calling agent
# ===============


def run_agentic(mode: str, slug: str, chrome_profile: str = "", cauth_cookie: str = "", api_key: str = "", model: str = "gpt-4o-mini", max_items: Optional[int] = None, log=None) -> RunState:
    """Use GPT to orchestrate order/scrolling/capture via tool calls. Deterministic tools do the heavy lifting."""
    # Open Playwright
    sync_playwright, PWTimeoutError = ensure_playwright()
    state = RunState(course_slug=slug)
    edit_url = COURSE_EDIT_TMPL.format(slug=slug)

    # --- LLM client
    try:
        import openai
        if hasattr(openai, "OpenAI"):
            # new SDK style, but fallback to old signature below if present
            from openai import OpenAI
            client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY", ""))
            use_new = True
        else:
            openai.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
            client = openai
            use_new = False
    except Exception as e:
        st.error("openai package not installed. Add `openai` to requirements.txt.")
        state.errors.append(str(e))
        return state

    with sync_playwright() as p:
        if mode == "Local":
            try:
                ctx = p.chromium.launch_persistent_context(user_data_dir=chrome_profile, channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"])  # noqa: E501
            except Exception as e:
                state.errors.append("Failed to open Chrome profile: " + str(e))
                return state
        else:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            if cauth_cookie:
                try:
                    ctx.add_cookies([{ "name":"CAUTH", "value": cauth_cookie, "domain": ".coursera.org", "path":"/", "httpOnly": True, "secure": True }])
                except Exception:
                    state.errors.append("Failed to set CAUTH cookie.")
        page = ctx.new_page()
        try:
            page.goto(edit_url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as e:
            state.errors.append("Failed to open editor: "+str(e))
            ctx.close();
            if mode != "Local":
                browser.close()
            return state
        page.wait_for_timeout(3500)
        if mode != "Local" and "login" in (page.url or "").lower():
            state.errors.append("Not authenticated — provide a fresh CAUTH cookie.")
            ctx.close();
            if mode != "Local":
                browser.close()
            return state

        # ---------- Tool functions (Python side)
        def tool_discover_outline() -> Dict[str, Any]:
            outline = build_outline(page, log or st)
            return {"outline": outline}

        def tool_click_and_capture(title: str) -> Dict[str, Any]:
            ok = click_by_title(page, title)
            wait_ready(page)
            txt = capture_text(page) if ok else ""
            mod = ""  # best-effort: we don't resolve module here
            return {"clicked": ok, "text_len": len(txt), "text": txt, "module_guess": mod}

        def tool_scroll(step: int = 800) -> Dict[str, Any]:
            try:
                page.evaluate(f"(function(){{ (document.scrollingElement||document.documentElement).scrollBy(0,{step}); }})();")
            except Exception:
                try:
                    page.mouse.wheel(0, step)
                except Exception:
                    pass
            wait_ready(page, 200)
            return {"scrolled": True}

        # ---------- LLM loop
        sys_prompt = (
            "You are an automation agent that exports a Coursera course to a docx. "
            "Use the provided tools to: 1) discover an outline, 2) click each item (skip duplicates), 3) capture the visible text. "
            "Prefer deterministic iteration over fancy planning. Return a short progress note in 'thought' and always call a tool until you are ready to finish. "
            "When all items captured (or a reasonable limit is reached), respond with JSON: {finish: true}."
        )

        tools_spec = [
            {"type": "function", "function": {"name": "discover_outline", "description": "Return module->items array for this course page.", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "click_and_capture", "description": "Click an item by visible title and return the captured text.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}},
            {"type": "function", "function": {"name": "scroll_page", "description": "Scroll the page down to reveal more items.", "parameters": {"type": "object", "properties": {"step": {"type": "integer", "default": 800}}}}}
        ]

        # shared state for loop
        outline_cache: List[Dict[str, Any]] = []
        titles_in_order: List[str] = []
        step_budget = 200

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps({"goal": f"Export course {slug}", "limit": max_items or 0})},
        ]

        def call_llm(msgs):
            if 'OpenAI' in str(type(client)) or hasattr(client, 'responses'):
                # new SDK (Responses API). NOTE: behavior may vary by version.
                try:
                    resp = client.responses.create(model=model, input=msgs, tools=tools_spec)
                    out = resp.output[0]
                    if getattr(out, 'type', '') == 'tool_call':
                        tc = out
                        return {"tool": tc.function.name, "arguments": json.loads(tc.function.arguments or '{}')}
                    else:
                        # plain content
                        first = out.content[0]
                        text = getattr(getattr(first, 'text', None), 'value', None)
                        return {"content": text or str(out)}
                except Exception as e:
                    return {"content": json.dumps({"finish": True, "error": str(e)})}
            else:
                # legacy Chat Completions
                resp = client.ChatCompletion.create(model=model, messages=msgs, tools=tools_spec, tool_choice="auto")
                msg = resp["choices"][0]["message"]
                if msg.get("tool_calls"):
                    tc = msg["tool_calls"][0]
                    name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"] or "{}")
                    return {"tool": name, "arguments": args}
                else:
                    return {"content": msg.get("content", "")}

        while step_budget > 0:
            step_budget -= 1
            decision = call_llm(messages)

            if decision.get("tool") == "discover_outline":
                res = tool_discover_outline()
                outline_cache = res.get("outline", [])
                titles_in_order = [it.get("title") for m in outline_cache for it in m.get("items", [])]
                messages.append({"role": "tool", "name": "discover_outline", "content": json.dumps({"found": len(titles_in_order)})})
                if not titles_in_order:
                    # try to scroll to reveal more and re-discover
                    tool_scroll()
                    continue
                next_title = next((t for t in titles_in_order if t and t not in state.seen_titles), None)
                if next_title:
                    messages.append({"role": "user", "content": json.dumps({"next": next_title})})
                continue

            if decision.get("tool") == "click_and_capture":
                title = decision["arguments"].get("title")
                if not title:
                    title = next((t for t in titles_in_order if t and t not in state.seen_titles), None)
                    if not title:
                        messages.append({"role": "assistant", "content": json.dumps({"finish": True})})
                        break
                ok_txt = tool_click_and_capture(title)
                state.seen_titles.add(title)
                # module mapping
                mod_title = ""; mod_idx = 0; it_idx = 0; it_type = "page"
                for mi, m in enumerate(outline_cache, start=1):
                    for ii, it in enumerate(m.get("items", []), start=1):
                        if it.get("title") == title:
                            mod_title = m.get("moduleTitle", f"Module {mi}")
                            mod_idx = mi; it_idx = ii; it_type = it.get("type", "page"); break
                    if mod_title: break
                state.items.append(ItemRecord(
                    module_index=mod_idx or 0,
                    module_title=mod_title or "",
                    item_index=it_idx or 0,
                    item_type=it_type,
                    item_title=title,
                    content_text=ok_txt.get("text", ""),
                ))
                messages.append({"role": "tool", "name": "click_and_capture", "content": json.dumps({"clicked": ok_txt.get("clicked"), "len": ok_txt.get("text_len")})})
                if max_items and len(state.items) >= max_items:
                    messages.append({"role": "assistant", "content": json.dumps({"finish": True})})
                    break
                continue

            if decision.get("tool") == "scroll_page":
                tool_scroll(**decision["arguments"])
                messages.append({"role": "tool", "name": "scroll_page", "content": json.dumps({"ok": True})})
                continue

            content = decision.get("content", "")
            try:
                maybe = json.loads(content) if content.strip().startswith("{") else {}
            except Exception:
                maybe = {}
            if maybe.get("finish"):
                break
            messages.append({"role": "user", "content": json.dumps({"hint": "call a tool or return {finish:true}"})})

        ctx.close()
        if mode != "Local":
            browser.close()

    return state

# ===============
# Export helper
# ===============

def export_docx(state: RunState, outfile: str) -> str:
    doc = Document()
    h = doc.add_heading(f"Coursera Export: {state.course_slug}", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph("")

    cur_mod = None
    for rec in state.items:
        if rec.module_title != cur_mod:
            doc.add_heading(f"Module {rec.module_index}: {rec.module_title or 'Untitled'}", level=1)
            cur_mod = rec.module_title
        doc.add_heading(f"{rec.item_type.title()}: {rec.item_title}", level=2)
        if rec.content_text.strip():
            p = doc.add_paragraph(rec.content_text.strip())
            p.paragraph_format.space_after = Pt(6)
        else:
            doc.add_paragraph("[Title only or non-text content]")
        doc.add_paragraph("")
    doc.save(outfile)
    return outfile

# ===============
# UI
# ===============
mode = st.sidebar.radio("Run mode", ["Local (Chrome profile)", "Streamlit Cloud (headless)"])
course_input = st.text_input("Course URL or slug", value="technical-assessment-testing-sandbox")
slug = (re.search(r"/teach/([\w\-]+)/content/edit", course_input.strip()) or re.match(r"^[\w\-]+$", course_input.strip()))

if mode.startswith("Local"):
    default_profile = os.path.expanduser(r"~\\AppData\\Local\\Google\\Chrome\\User Data")
    chrome_profile = st.text_input("Chrome User Data directory", value=default_profile)
    cauth = ""
else:
    chrome_profile = ""
    with st.expander("Cloud auth (Coursera)"):
        cauth = st.text_input("CAUTH cookie", type="password")

with st.sidebar:
    api_key = st.text_input("OpenAI API Key", type="password", help="Required for agentic control")
    model = st.text_input("Model", value="gpt-4o-mini")
    max_items = st.number_input("Limit items (0 = all)", min_value=0, max_value=10000, value=0)
    outfile = st.text_input("Output .docx name", value="coursera_export.docx")

run = st.button("▶️ Run GPT Agent", type="primary")

if run:
    if not api_key and not os.getenv("OPENAI_API_KEY"):
        st.error("Provide an OpenAI API Key in the sidebar or env var OPENAI_API_KEY.")
        st.stop()
    slug_text = course_input.strip().strip('"')
    slug_only = (re.search(r"/teach/([\w\-]+)/content/edit", slug_text) or re.match(r"^[\w\-]+$", slug_text))
    if not slug_only:
        st.error("Enter a course slug or the full /teach/.../content/edit URL.")
        st.stop()
    slug = re.search(r"/teach/([\w\-]+)/content/edit", slug_text)
    slug = slug.group(1) if slug else slug_text

    with st.status("Running agent…", expanded=True) as status:
        st.write(f"Course: **{slug}** | Mode: {mode}")
        rs = run_agentic("Local" if mode.startswith("Local") else "Cloud", slug, chrome_profile, cauth, api_key, model, max_items or None, log=st)
        if rs.errors:
            st.warning("Some issues were reported:")
            for e in rs.errors:
                st.write("• "+e)
        st.write(f"Captured **{len(rs.items)}** items.")
        status.update(label="Exporting .docx…", state="running")

    # export
    fname = export_docx(rs, outfile)
    with open(fname, "rb") as f:
        st.download_button("⬇️ Download .docx", f.read(), file_name=os.path.basename(fname), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # preview
    st.subheader("Preview")
    df = pd.DataFrame([
        {"Module #": it.module_index, "Module": it.module_title, "Type": it.item_type, "Title": it.item_title, "Snippet": (it.content_text[:180] + ("…" if len(it.content_text) > 180 else "")).replace("\n"," ")}
        for it in rs.items
    ])
    st.dataframe(df, use_container_width=True)

st.markdown("""
---
**Setup (local)**
```powershell
pip install streamlit playwright python-docx pandas openai
python -m playwright install chrome
streamlit run app_agentic.py
```
**Cloud notes**
- Add `openai` to requirements.txt; keep Chromium libs in packages.txt.
- For Cloud auth, paste a fresh **CAUTH** cookie for coursera.org.

**Privacy / ToS**
- Only automate content you own or are allowed to export. This is a personal tool that mirrors your in-browser access.
"""
)