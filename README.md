# 🧠 OES GenAI Micro‑Apps – Internal Development Sandbox

**Last Updated:** 2025-11-13

**Maintained by:** **Imaad Fakier — Senior GenAI Developer, OES**
_Technical ownership, refactoring, architectural direction, and ongoing maintenance are solely managed by Imaad Fakier.
Domain‑level instructional input is informed by Learning Design stakeholders (primarily via Christo Visser)._

---

## 🚀 Purpose of This Repository

`Ai-MicroApps-test` is the **internal research, prototyping, and integration sandbox** for all GenAI‑powered educational micro‑applications used across OES.

This environment acts as the **official pre‑production layer**, where GenAI micro‑apps are:

- Designed and architected
- Refactored and standardized
- Tested and validated
- Documented and production‑aligned
- Prepared for migration into `AI-MicroApps-main`

All major refactors in 2025 introduced unified architecture, updated UI/UX patterns, and consistent helper modules used across the entire OES GenAI ecosystem.

---

## 📁 Clean Repository Structure (Development‑Relevant Files Only)

The following structure excludes caches, `__pycache__`, environment folders, and other noise.

```text
Ai-MicroApps-test/
│
├── api_uploader_split_project/                    # Fully refactored Canvas Import micro‑app
│   ├── app.py
│   ├── canvas_api.py
│   ├── gdoc_utils.py
│   ├── kb.py
│   ├── module_tags.py
│   ├── parsers.py
│   ├── quizzes_classic.py
│   ├── quizzes_new.py
│   ├── requirements.txt
│   └── utils.py
│
├── app_alt_text_construct.py
├── app_construct_lo_generator.py
├── app_discussion_generator.py
├── app_image_latex.py
├── app_image_text.py
├── app_mg_script_gen.py
├── app_ptc_video_script_gen.py
├── app_quiz_question_gen.py
├── app_scenario_video_script.py
│
├── canvas_import_secure.py
├── canvas_import_simplified.py
├── canvas_quiz_upload/
│
├── cld_topic_extractor.py
├── config.py
├── copy-paste-agent.py
│
├── core_logic/
│   ├── data_storage.py
│   ├── handlers.py
│   ├── llm_config.py
│   ├── main.py
│   └── rag_pipeline.py
│
├── data_storage.py
├── quiz_question_generator.py
│
├── rag_docs/                                     # Internal PDFs for RAG testing
│
├── shared_assets/                                # Additional PDFs / resources
│
├── app_images/                                   # Icons, UI images, preview assets
│
├── requirements.txt
├── packages.txt
├── LICENSE
└── README.md
```

---

## 🧩 Micro‑Applications Overview

Each `app_*.py` file is an **independent Streamlit micro‑app**, following the OES‑standardized GenAI architecture.

| Micro‑App                                  | Purpose                                                                                                                                                                               |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **api_uploader_split_project/app.py**      | Flagship DOCX → Canvas importer. Converts storyboards into Canvas pages, modules, discussions, assignments, and quizzes (Classic + New Quizzes). Includes full RAG KB + GDoc support. |
| **app_alt_text_construct.py**              | Generates WCAG‑compliant alt‑text for images.                                                                                                                                         |
| **app_quiz_question_gen.py**               | Generates structured quiz questions aligned with LOs.                                                                                                                                 |
| **app_construct_lo_generator.py**          | Builds learning objectives from CLDs or raw text.                                                                                                                                     |
| **app_mg_script_gen.py**                   | Creates micro‑learning instructional scripts.                                                                                                                                         |
| **app_scenario_video_script.py**           | Generates scenario‑based instructional video scripts.                                                                                                                                 |
| **app_ptc_video_script_gen.py**            | Creates Pre‑Tutorial Content scripts.                                                                                                                                                 |
| **app_discussion_generator.py**            | Generates Canvas‑ready discussion prompts.                                                                                                                                            |
| **app_image_text.py / app_image_latex.py** | Produces structured text or LaTeX from diagrams/images.                                                                                                                               |
| **visual_transcripts.py**                  | Creates visual transcript summaries.                                                                                                                                                  |
| **cld_topic_extractor.py**                 | Extracts topics/concepts from CLDs.                                                                                                                                                   |
| **umich_feedback_bot.py**                  | Automated feedback generator (Umich pilot).                                                                                                                                           |
| **copy-paste-agent.py**                    | Minimal prompt‑exploration sandbox.                                                                                                                                                   |

---

## 🧱 Shared Helper Modules (Refactored 2025)

These modules form the backbone of all micro‑apps.

### **Canvas API & Integrations**

- `canvas_api.py` — Pages, Assignments, Discussions, Modules, Classic Quiz data
- `quizzes_classic.py` — Classic Quiz endpoints
- `quizzes_new.py` — Full LTI New Quizzes support (MCQ, MA, TF, SA, Essay, Numerical, Matching, FIMB)

### **Knowledge Base (RAG) / OpenAI Vector Stores**

- `kb.py`

  - Vector store creation
  - File uploads
  - Backwards‑compatible OpenAI SDK support

### **Document Processing Utilities**

- `gdoc_utils.py` — GDoc export, heading extraction, anchor resolution
- `parsers.py` — DOCX + text parsing (`<canvas_page>` blocks)
- `module_tags.py` — Extract `<module_name>...</module>` structures
- `utils.py` — Tag extraction helpers

These helpers now follow full docstring documentation, error handling consistency, and naming alignment.

---

## 🎨 UI/UX Standards (2025 OES GenAI Style)

All micro‑apps adhere to:

- **Sidebar‑first layout**
- Consistent spacing, headings, and section grouping
- Expanders for advanced configuration
- Unified colors and iconography (via `app_images/`)
- A predictable flow: **Input → Preview → Generate → Export / Upload**
- Standardized SHA‑256 access‑code authentication for secure apps

---

## ⚙️ Installation & Local Setup

```bash
git clone <PRIVATE_REPO_URL>
cd Ai-MicroApps-test

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.sample .env
# Add your secret keys
```

Run any micro‑app:

```bash
streamlit run api_uploader_split_project/app.py
# or
streamlit run app_quiz_question_gen.py
```

---

## 🧠 Development Guidelines

### **1. Micro‑App Independence**

Each micro‑app must function in isolation.

### **2. Shared Helper Modules Only**

No repeated logic; always import from:
`canvas_api.py`, `kb.py`, `utils.py`, etc.

### **3. No Hardcoded Secrets**

Everything goes into `.env` → accessed via `config.py`.

### **4. UI/UX Consistency**

New apps must follow the 2025 OES style.

### **5. Testing**

Local Streamlit testing before any internal deployment.

### **6. Git Hygiene**

Branches → PRs → Merges for all significant changes.

---

## 🧭 2025 Refactor Status

| Category                      | Status         | Notes                                   |
| ----------------------------- | -------------- | --------------------------------------- |
| Helper Module Standardization | ✅ Complete    | Major refactor across all shared utils. |
| Canvas Import App Overhaul    | ✅ Complete    | Production‑grade architecture & UX.     |
| Requirements Pinning          | ✅ Complete    | Rewritten for deterministic builds.     |
| UI/UX Standardization         | ⚙️ In Progress | Rolling out across all apps.            |
| RAG / Snowflake Experiments   | 🚧 Active      | Research for future analytics apps.     |
| Removal of Legacy Patterns    | 🔄 Ongoing     | Cleaning deprecated code.               |

---

## 📄 License

This repository includes proprietary OES GenAI tooling.
External distribution requires OES authorization.

---

## 💬 Maintainer Contact

**Imaad Fakier** — Senior GenAI Developer, OES
📧 _[ifakier@oes.com](mailto:ifakier@oes.com)_

> _“Where GenAI prototypes evolve into production‑ready educational tools.”_
