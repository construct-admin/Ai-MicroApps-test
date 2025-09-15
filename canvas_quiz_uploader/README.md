
# Canvas API Uploader (Split Project, New Quizzes – all types)

This is a minimal, **working** split-project Streamlit app that supports **Canvas New Quizzes** and **all major item types** via a simple storyboard tag format inside `<canvas_page>` blocks.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Set Canvas **domain**, **token**, and **course_id** in the sidebar. Optionally add a **module_id** to auto-insert quizzes into a Module.

## Supported New Quizzes item types

- Multiple Choice (`multiple_choice`)
- Multiple Answer (`multiple_answer`)
- True/False (`true_false`)
- Short Answer (`short_answer`) → implemented as single **rich-fill-blank** with accepted answers
- Essay (`essay`)
- Numeric (`numeric`)
- Matching (`matching`)
- Ordering (`ordering`)
- Categorization (`categorization`)
- Fill‑in‑Blank (`fill_in_blank`) → modern **rich-fill-blank**
- File Upload (`file_upload`) – manual grading
- Hot Spot (`hot_spot`) – requires hosted image URL (or extend for presigned uploads)
- Formula (`formula`) – maps to numeric scoring rules

Backed by Canvas **New Quizzes API** (`/api/quiz/v1/courses/:course_id/quizzes`) and **New Quiz Items API** (`/api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items`). See Instructure developer docs for details.
