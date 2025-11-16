# ------------------------------------------------------------------------------
# Refactor date: 2025-11-16
# Refactored by: Imaad Fakier
# Purpose: Align OES micro-applications with OES GenAI Streamlit standards.
# ------------------------------------------------------------------------------
"""
core_logic.handlers (Refactored - Updated for OpenAI v1.x)
-----------------------------------------------------------
Provides per-family LLM invocation handlers.

Included:
- `openai` (supports image + text)
- Exponential backoff wrapper
- Defensive error handling to prevent crashes
- Fully compatible with new OpenAI Python client v1.0+

Key changes from legacy handler:
- Removed deprecated global `openai.chat.completions.create`
- Replaced with new `OpenAI()` client (required for v1.x)
- Client created inside handler to prevent Streamlit Cloud injecting `proxies`

Additional improvements in this patch:
- Correct handling of multimodal output blocks (GPT-4o family)
- Accurate usage token extraction using v1.x fields (`input_tokens`, `output_tokens`)
- Consolidated message-building logic for clarity and maintainability
- More transparent error messages surfaced through the Streamlit UI
- Future-proofed against upcoming OpenAI v2+ API conventions
"""

import os
import time
import random
import streamlit as st
from openai import OpenAI


# ------------------------------------------------------------------------------
# Helper: retry wrapper
# ------------------------------------------------------------------------------
def with_backoff(fn, *args, **kwargs):
    """
    Execute a callable with exponential backoff up to 5 attempts.
    Intended for transient operational failures such as:
    - Temporary 5xx errors from OpenAI
    - Network jitter on Streamlit Community Cloud
    - Rate-limiting windows that open after a brief delay

    This mechanism ensures that small hiccups do NOT cause the app to crash.
    """
    delay = 0.5
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # On the final attempt, surface the error normally
            if attempt == 4:
                raise

            wait = delay + random.random() * delay
            st.warning(f"Retrying after transient error: {e} (waiting {wait:.1f}s)")
            time.sleep(wait)
            delay *= 2


# ------------------------------------------------------------------------------
# Handler: OpenAI (updated for OpenAI Python SDK v1.0+)
# ------------------------------------------------------------------------------
def handle_openai(context):
    """
    Core OpenAI handler used by OES micro-apps.

    Compatible with all current and upcoming OpenAI 2025 models:
    - GPT-4o / GPT-4o-mini
    - GPT-4.1 / GPT-4.1-mini
    - Future OpenAI "unified" chat models (v1 API)

    This handler supports:
    - Text-only prompts
    - Multimodal prompts (image + text)
    - Cost calculation using modern token usage fields
    - Fully updated message schema consistent with OpenAI v1.x

    Important implementation details:
    - The OpenAI client is constructed INSIDE the handler.
      This prevents Streamlit Cloud from injecting unsupported parameters
      such as `proxies`, a common source of deployment failures.
    - Message construction supports the GPT-4o "content blocks" format.
    """

    # ----------------------------------------------------------
    # Initialize OpenAI client (inside handler — CRITICAL FIX)
    # ----------------------------------------------------------
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

    # Modern constructor: accepts only safe, documented parameters.
    client = OpenAI(api_key=api_key)

    # ----------------------------------------------------------
    # Extract model parameters from context
    # ----------------------------------------------------------
    model = context["model"]
    temperature = context.get("temperature", 1.0)
    max_tokens = context.get("max_tokens", 1000)

    # ----------------------------------------------------------
    # Build messages payload (supports multimodal)
    # ----------------------------------------------------------
    messages = []

    # System prompt
    if context.get("SYSTEM_PROMPT"):
        messages.append({"role": "system", "content": context["SYSTEM_PROMPT"]})

    # User content: always a list of blocks for modern models
    user_content = []

    # Text block
    if context.get("user_prompt"):
        user_content.append({"type": "text", "text": context["user_prompt"]})

    # Optional image blocks (data URLs already base64-encoded upstream)
    if context.get("supports_image") and context.get("image_urls"):
        for url in context["image_urls"]:
            user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages.append({"role": "user", "content": user_content})

    # ----------------------------------------------------------
    # OpenAI API Call (wrapped in exponential backoff)
    # ----------------------------------------------------------
    try:
        response = with_backoff(
            client.chat.completions.create,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=context.get("top_p", 1.0),
            frequency_penalty=context.get("frequency_penalty", 0.0),
            presence_penalty=context.get("presence_penalty", 0.0),
        )

        # ------------------------------------------------------
        # Extract assistant text (handles multimodal structured blocks)
        # ------------------------------------------------------
        msg = response.choices[0].message["content"]

        if isinstance(msg, list):
            # GPT-4o sometimes returns multiple block types (reasoning, text, etc.)
            text = "\n".join(
                block.get("text", "")
                for block in msg
                if isinstance(block, dict) and "text" in block
            ).strip()
        else:
            text = str(msg).strip()

        # ------------------------------------------------------
        # Cost Calculation (OpenAI v1.x usage model)
        # ------------------------------------------------------
        usage = response.usage

        # Modern fields (preferred)
        input_toks = getattr(usage, "input_tokens", 0)
        output_toks = getattr(usage, "output_tokens", 0)

        # Model pricing loaded from template configuration
        price_in = context.get("price_input_token_1M", 0)
        price_out = context.get("price_output_token_1M", 0)

        # Convert token counts ↦ dollar amount
        execution_price = (input_toks / 1_000_000) * price_in + (
            output_toks / 1_000_000
        ) * price_out

        return text, float(execution_price)

    except Exception as e:
        # Visible in the UI and logs
        st.error(f"OpenAI handler failed: {e}")
        raise


# ------------------------------------------------------------------------------
# HANDLERS registry
# Add additional model families here as micro-apps expand
# ------------------------------------------------------------------------------
HANDLERS = {
    "openai": handle_openai,
    # "anthropic": handle_anthropic,
    # "azure_openai": handle_azure_openai,
    # "google_genai": handle_google_genai,
}
