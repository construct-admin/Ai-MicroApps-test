# ------------------------------------------------------------------------------
# Refactor date: 2025-11-14
# Refactored by: Imaad Fakier
# Purpose: Align Alt Text / Discussion Generator micro-app with
#          OES GenAI Streamlit standards + fix Streamlit proxy env issue.
# ------------------------------------------------------------------------------
"""
core_logic.handlers (Refactored)
--------------------------------
Provides per-family LLM invocation handlers.

Includes:
- `openai` (supports image+text, exponential backoff)
- Placeholders for future model families

Key additions:
- Safe proxy scrubbing for Streamlit Cloud
- Clean OpenAI v1 Client usage
- Exponential backoff helper
- Stable multimodal formatting for GPT-4o
- Defensive error reporting for Streamlit
"""

# ------------------------------------------------------------------------------
# ❗ Critical: Remove proxy variables BEFORE importing OpenAI
# ------------------------------------------------------------------------------
import os

for key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(key, None)

# ------------------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------------------
import time
import random
from openai import OpenAI
import streamlit as st


# ------------------------------------------------------------------------------
# Helper: retry wrapper
# ------------------------------------------------------------------------------
def with_backoff(fn, *args, **kwargs):
    """
    Execute a callable with exponential backoff up to 5 attempts.
    Intended for transient failures (timeouts, rate limits, etc.).
    """
    delay = 0.5
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # final attempt → raise
            if attempt == 4:
                raise
            wait = delay + random.random() * delay
            st.warning(f"Retrying after transient error: {e} (wait {wait:.1f}s)")
            time.sleep(wait)
            delay *= 2


# ------------------------------------------------------------------------------
# Handler: OpenAI
# ------------------------------------------------------------------------------
def handle_openai(context):
    """
    Core OpenAI handler used by most micro-apps.
    Supports image inputs for GPT-4o family models.
    Returns (response_text, execution_price).
    """

    # ------------------------------------------------------------------------------
    # Initialize shared OpenAI client
    # ------------------------------------------------------------------------------
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

    model = context["model"]
    temperature = context["temperature"]
    max_tokens = context["max_tokens"]

    # ---- Build messages ------------------------------------------------------
    messages = [{"role": "system", "content": context["SYSTEM_PROMPT"]}]

    user_prompt = context.get("user_prompt", "")
    user_content = [{"type": "text", "text": user_prompt}]

    # Attach image URLs (multimodal)
    if context.get("supports_image") and context.get("image_urls"):
        for url in context["image_urls"]:
            user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages.append({"role": "user", "content": user_content})

    # ---- Execute request with retry -----------------------------------------
    try:
        response = with_backoff(
            _client.chat.completions.create,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=context.get("top_p", 1.0),
            frequency_penalty=context.get("frequency_penalty", 0.0),
            presence_penalty=context.get("presence_penalty", 0.0),
        )

        text = response.choices[0].message.content.strip()

        # Token usage + pricing
        usage = getattr(response, "usage", None)
        input_toks = getattr(usage, "input_tokens", 0) or getattr(
            usage, "prompt_tokens", 0
        )
        output_toks = getattr(usage, "output_tokens", 0) or getattr(
            usage, "completion_tokens", 0
        )

        price_in = context.get("price_input_token_1M", 0)
        price_out = context.get("price_output_token_1M", 0)
        execution_price = (
            (input_toks * price_in) + (output_toks * price_out)
        ) / 1_000_000.0

        return text, execution_price

    except Exception as e:
        st.error(f"OpenAI handler failed: {e}")
        raise


# ------------------------------------------------------------------------------
# HANDLERS registry
# ------------------------------------------------------------------------------
HANDLERS = {
    "openai": handle_openai,
    # "anthropic": handle_anthropic,
    # "azure_openai": handle_azure_openai,
}
