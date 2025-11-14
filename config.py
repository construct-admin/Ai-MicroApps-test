# ------------------------------------------------------------------------------
# Refactor date: 2025-11-12
# Refactored by: Imaad Fakier
# Purpose: Guided Critical Analysis (Config Module)
# Refactored for clarity and OES GenAI alignment
# ------------------------------------------------------------------------------
"""
This module defines the configuration for the **Guided Critical Analysis**
AI-tutored rubric demo app.

It contains:
- App metadata (titles, descriptions, buttons)
- Phased structure (prompts, scoring, feedback)
- LLM configuration and scoring controls
- Runtime configuration dictionary passed into `main(config)`
"""

# ─────────────────────────────────────────────────────────────
# 🧭 App Metadata
# ─────────────────────────────────────────────────────────────
APP_TITLE = "Guided Critical Analysis"

APP_INTRO = """
In this guided case study, we'll both read the same case study. Then, you'll be guided through an analysis of the paper. Let's begin by reading the paper!

This is a **DEMO**, so sample answers are pre-filled and the article is one that is highly familiar to people.
"""

APP_HOW_IT_WORKS = """
This is an **AI-Tutored Rubric Exercise** that acts as a tutor guiding a student through a shared asset, like an article.  
It uses the **OpenAI Assistants API with GPT-4**.

The faculty defines:
- Questions and rubrics
- Pass thresholds and scoring logic

AI provides:
- Feedback on each response
- Approximate scoring guidance
- Suggestions for refinement

⚠️ Experimental notes:
- AI may make mistakes; users may skip confusing questions.
- Grading is lenient and should be used for formative guidance only.
- Avoid showing numeric scores directly to users.
"""

# ─────────────────────────────────────────────────────────────
# 🔗 Shared Assets and Buttons
# ─────────────────────────────────────────────────────────────
SHARED_ASSET = {}

HTML_BUTTON = {
    "url": "http://up.csail.mit.edu/other-pubs/las2014-pguo-engagement.pdf",
    "button_text": "Read PDF",
}

SYSTEM_PROMPT = "You are an AI assistant who evaluates student submissions."

# ─────────────────────────────────────────────────────────────
# 🎯 Phase Configuration
# ─────────────────────────────────────────────────────────────
PHASES = {
    "phase1": {
        "name": "Introduction",
        "fields": {
            "name": {
                "type": "text_input",
                "label": "What is your name?",
                "value": "Jane Doe",
            },
            "background": {
                "type": "text_area",
                "label": "What do you already know about online education and video engagement?",
                "value": (
                    "I have taken a few online courses and noticed that some video lectures "
                    "are more engaging than others. I think factors like video length and "
                    "the instructor's speaking style might affect engagement."
                ),
            },
        },
        "phase_instructions": (
            "The user provides their name and background. Greet the user formally and explain "
            "how their background relates to the paper being analyzed."
        ),
        "user_prompt": "My name is {name} and here is the {background} of the study",
        "ai_response": False,
        "custom_response": (
            "Welcome {name}, and thank you for sharing your background ({background})."
        ),
        "scored_phase": False,
        "allow_revisions": False,
        "allow_skip": True,
        "show_prompt": True,
        "read_only_prompt": False,
    },
    "phase2": {
        "name": "Article Overview",
        "fields": {
            "topic": {
                "type": "text_area",
                "label": "What is the main topic of this research paper?",
                "value": (
                    "This research paper focuses on the impact of video production decisions "
                    "on student engagement in online educational videos."
                ),
            }
        },
        "phase_instructions": (
            "Evaluate understanding of the paper’s topic and goals. "
            "Guide refinement using details from the paper."
        ),
        "user_prompt": "Here is the main topic of the research paper: {topic}",
        "ai_response": True,
        "scored_phase": False,
        "allow_revisions": True,
        "max_revisions": 3,
        "allow_skip": True,
        "show_prompt": True,
        "read_only_prompt": False,
    },
    "phase3": {
        "name": "Methodology Analysis",
        "fields": {
            "data_collection": {
                "type": "text_area",
                "label": "How did the researchers collect data for this study?",
                "value": (
                    "The researchers collected data from edX, analyzing millions of video "
                    "sessions across multiple courses."
                ),
            },
            "analysis_method": {
                "type": "text_area",
                "label": "What methods did the researchers use to analyze the data?",
                "value": (
                    "They used statistical correlations between video attributes and engagement, "
                    "along with qualitative categorization of video styles."
                ),
            },
        },
        "phase_instructions": (
            "Assess the student’s understanding of data collection and analysis methods. "
            "Encourage mention of both quantitative and qualitative aspects."
        ),
        "user_prompt": (
            "The data was collected as follows: {data_collection}. "
            "The analysis methods used were: {analysis_method}"
        ),
        "ai_response": True,
        "allow_revisions": False,
        "allow_skip": True,
        "show_prompt": True,
        "read_only_prompt": False,
    },
    "phase4": {
        "name": "Results and Implications",
        "fields": {
            "key_findings": {
                "type": "text_area",
                "label": "What are the most significant findings of this study?",
                "value": (
                    "1. Shorter videos are more engaging.\n"
                    "2. Enthusiastic instructors retain attention better.\n"
                    "3. Khan-style tablet drawings outperform slides."
                ),
            },
            "implications": {
                "type": "text_area",
                "label": "How might these findings impact future video creation?",
                "value": (
                    "Educators may adopt shorter, high-engagement formats with "
                    "authentic delivery and integrated visual explanations."
                ),
            },
        },
        "phase_instructions": (
            "Evaluate understanding of findings and implications. "
            "Provide hints if key insights are missing."
        ),
        "user_prompt": (
            "The key findings of the study are: {key_findings}. "
            "The implications for online educational videos are: {implications}"
        ),
        "ai_response": True,
        "scored_phase": True,
        "minimum_score": 3,
        "rubric": """
1. Comprehensiveness  
   - 3 pts: Mentions ≥3 findings  
   - 2 pts: Mentions 2 findings  
   - 1 pt: Mentions 1 finding  
   - 0 pts: No relevant findings

2. Accuracy  
   - 2 pts: All findings accurate  
   - 1 pt: Some accurate  
   - 0 pts: None accurate
""",
        "allow_revisions": True,
        "max_revisions": 3,
        "allow_skip": True,
        "show_prompt": False,
        "read_only_prompt": False,
    },
}

# ─────────────────────────────────────────────────────────────
# 🤖 Model Configuration
# ─────────────────────────────────────────────────────────────
PREFERRED_LLM = "gpt-4o-mini"

LLM_CONFIG_OVERRIDE = {
    "gpt-4o-mini": {
        "family": "openai",
        "model": "gpt-4o-mini",
        "max_tokens": 1000,
        "temperature": 1.0,
        "top_p": 1.0,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "supports_image": False,
        "price_input_token_1M": 0.15,
        "price_output_token_1M": 0.60,
    }
}

# ─────────────────────────────────────────────────────────────
# 🧮 Scoring & Display
# ─────────────────────────────────────────────────────────────
SCORING_DEBUG_MODE = True
DISPLAY_COST = True
COMPLETION_MESSAGE = "You've reached the end! I hope you learned something!"
COMPLETION_CELEBRATION = False

# ─────────────────────────────────────────────────────────────
# 📚 RAG / Source Configuration
# ─────────────────────────────────────────────────────────────
RAG_IMPLEMENTATION = True
SOURCE_DOCUMENT = "student_engagement.pdf"

# ─────────────────────────────────────────────────────────────
# ⚙️ Page & Template Settings
# ─────────────────────────────────────────────────────────────
PAGE_CONFIG = {
    "page_title": "AI Assessment",
    "page_icon": "👨‍💻",
    "layout": "centered",
    "initial_sidebar_state": "expanded",
}

SIDEBAR_HIDDEN = True
TEMPLATES = {"AI Assessment": "config"}

# ─────────────────────────────────────────────────────────────
# 🚀 Entry Point
# ─────────────────────────────────────────────────────────────
from core_logic.main import main

config = {
    "APP_TITLE": APP_TITLE,
    "APP_INTRO": APP_INTRO,
    "APP_HOW_IT_WORKS": APP_HOW_IT_WORKS,
    "HTML_BUTTON": HTML_BUTTON,
    "PREFERRED_LLM": PREFERRED_LLM,
    "LLM_CONFIG_OVERRIDE": LLM_CONFIG_OVERRIDE,
    "PHASES": PHASES,
    "COMPLETION_MESSAGE": COMPLETION_MESSAGE,
    "COMPLETION_CELEBRATION": COMPLETION_CELEBRATION,
    "SCORING_DEBUG_MODE": SCORING_DEBUG_MODE,
    "DISPLAY_COST": DISPLAY_COST,
    "RAG_IMPLEMENTATION": RAG_IMPLEMENTATION,
    "SOURCE_DOCUMENT": SOURCE_DOCUMENT,
    "PAGE_CONFIG": PAGE_CONFIG,
    "SIDEBAR_HIDDEN": SIDEBAR_HIDDEN,
    "TEMPLATES": TEMPLATES,
}

main(config)
