# Canvas New Quizzes Uploader (All Item Types)

A Streamlit app that creates a New Quiz in Canvas and uploads questions of all supported types using the **New Quizzes Items** API. It also includes retry/backoff for flaky 5xx responses and an auto-repair pass that re-posts any items the service dropped.

## Features
- Parse storyboard `.txt`/`.docx` blocks with `<canvas_page>` and `<quiz_start>..</quiz_end>` tags
- Supports: multiple_choice, multiple_answer, true_false, short_answer, essay, numeric, matching, ordering, categorization, fill_in_blank, file_upload, hot_spot, formula
- Retries on 5xx when creating items
- Auto-repair (poll, re-post missing items)
- Optional: add the quiz to a module and publish the assignment

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
