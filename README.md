# 🧠 OES GenAI Micro-Apps — Internal Development & Refactor Sandbox

**Last Updated:** 2025-11-24
**Maintained by:** **Imaad Fakier — Senior GenAI Developer, OES**

This repo is the **internal engineering environment** used to prototype, refactor, and standardize all OES GenAI micro-applications.

**This is not production** — it is the **prime staging layer** where:

- new apps are created,
- legacy apps are stabilised,
- standards are enforced,
- functionality is validated,
- UX and architecture are iterated,
- refactors are completed before migration to `AI-MicroApps-main`.

---

## 🚀 Mission of This Repository

`AI-MicroApps-test` functions as:

🔬 **A controlled R&D sandbox**
Proof-of-concept and iterative experimentation.

🧰 **A refactor + remediation hub**
Where legacy micro-apps are upgraded to 2025 standards.

📦 **Architecture enforcement layer**
Ensures every app follows:

- consistent UI/UX,
- shared helper modules,
- unified environment design,
- deterministic dependency stacks,
- secure access patterns.

🔁 **Pre-production pipeline**
Once stable → move to `AI-MicroApps-main`.

---

## 📁 Current Repository Structure (as of 2025-11-24)

Only relevant developer assets are listed.

```text
AI-MicroApps-test/
│
├── api_uploader_split_project/            # Canvas Import (flagship app)
│   ├── app.py                             # Streamlit entrypoint
│   ├── canvas_api.py
│   ├── gdoc_utils.py
│   ├── kb.py                              # Vector store utilities
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
├── umich_feedback_bot.py                  # Refactored; CAI-aligned feedback generator
├── visual_transcripts.py                  # Refactored; Marrichelle UX requirements applied
│
├── app_mg_script_gen.py
├── app_ptc_video_script_gen.py
├── app_quiz_question_gen.py
├── app_scenario_video_script.py
│
├── core_logic/
│   ├── handlers.py
│   ├── llm_config.py
│   ├── main.py
│   ├── rag_pipeline.py
│   └── data_storage.py
│
├── rag_docs/                              # Internal datasets for RAG
├── shared_assets/                         # Rubrics, PDFs, internal resources
├── app_images/                            # Icons/images for UI
│
├── requirements.txt                       # Unified dev dependency stack
├── packages.txt                           # Linux build deps (optional)
│
├── LICENSE
└── README.md
```

---

## 🧩 Micro-Apps Overview

Each `app_*.py` file is an **independent Streamlit micro-application** that follows OES’s 2025 architectural standards.

| Micro-App                                  | Purpose                                                                                                                    |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **api_uploader_split_project/app.py**      | Converts storyboard → Canvas modules, pages, discussions, assignments, Classic + New Quizzes. Full GDoc + RAG integration. |
| **visual_transcripts.py**                  | Visual transcript generator — now meets Marrichelle Berkeley constraints (precise frame capture + editable text panel).    |
| **umich_feedback_bot.py**                  | CAI-aligned elaborative feedback generator for Y/N responses (Michigan pilot).                                             |
| **app_quiz_question_gen.py**               | Model-aligned multidimensional quiz generation with LO traceability.                                                       |
| **app_construct_lo_generator.py**          | Generate learning objectives from CLDs or direct instructional content.                                                    |
| **app_alt_text_construct.py**              | WCAG 2.x alt-text generator. Consistent with Construct accessibility standards.                                            |
| **app_discussion_generator.py**            | Canvas discussion prompt synthesis with contextual framing.                                                                |
| **app_image_text.py / app_image_latex.py** | Convert diagrams → structured text or LaTeX.                                                                               |
| **app_mg_script_gen.py**                   | Micro-learning scripts for academic video/slide use.                                                                       |
| **app_scenario_video_script.py**           | Domain-based scenario instructional script generator.                                                                      |
| **app_ptc_video_script_gen.py**            | Pre-tutorial content generator.                                                                                            |

---

## 🧱 Shared Helper Modules (2025 Standard)

**Do not rewrite logic inside individual apps. Import from these:**

### 🔗 Canvas App Services

- `canvas_api.py`
- `quizzes_classic.py`
- `quizzes_new.py`

### 📚 RAG stack / KB

- `kb.py` — vector storage bootstrap
- `rag_pipeline.py` — ingestion & query pipeline
- `data_storage.py` — standardized IO layer

### 📄 Document utilities

- `gdoc_utils.py`
- `parsers.py`
- `module_tags.py`
- `utils.py`

These modules:

- follow consistent docstrings,
- support streaming OpenAI SDK v1,
- eliminate duplication across apps.

---

## 🎨 UI/UX Framework

All micro-apps follow:

✔️ Sidebar-first navigation
✔️ Inputs → preview → generation → export
✔️ Standardized session state
✔️ Non-blocking UI interactions
✔️ Auth via SHA-256 access code
✔️ Documentable outputs (docx/pdf/json)

---

## 🔐 Secrets and Environment

Never hardcode keys.

Use:

```text
.env
.env.sample
streamlit secrets
```

Variables include:

- `OPENAI_API_KEY`
- `ACCESS_CODE_HASH`
- model overrides per app

---

## ⚙️ Local Setup

```bash
git clone <PRIVATE_TEST_REPO_URL>
cd AI-MicroApps-test

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.sample .env
```

Run any app:

```bash
streamlit run visual_transcripts.py
```

---

## 🧠 Dev Protocol

1. Refactor in **test**.
2. Remove legacy / duplicated code.
3. Align UI/UX + dependencies.
4. Validate with domain experts.
5. Move to **AI-MicroApps-main**.

---

## 🧭 Current Status (as of 24 Nov 2025)

| Category                      | Status              | Notes                                   |
| ----------------------------- | ------------------- | --------------------------------------- |
| Legacy cleanup                | 🚧 Active           | Deleting orphaned code across repo      |
| Helper module standardization | ✅ Done             | All apps must import from core_logic    |
| Visual transcripts            | 🟢 Usable           | Marrichelle UX requirements implemented |
| Umich feedback                | 🟢 Refactored       | CAI-aligned + architecture compliant    |
| Canvas importer               | 🟢 Production-grade | Fully refactored                        |

---

## 📄 License

Internal proprietary OES development repository.
No external distribution permitted.

---

## 💬 Maintainer

**Imaad Fakier** — Senior GenAI Developer
📧 [ifakier@oes.com](mailto:ifakier@oes.com)

> **“The place where prototypes grow muscles before they go live.”**
