# ------------------------------------------------------------------------------
# Refactor date: 2025-11-14
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
    Intended for transient failures (timeouts, rate limits, network hiccups).
    """
    delay = 0.5
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # Raise final attempt
            if attempt == 4:
                raise

            wait = delay + random.random() * delay
            st.warning(f"Retrying after transient error: {e} (waiting {wait:.1f}s)")
            time.sleep(wait)
            delay *= 2


# ------------------------------------------------------------------------------
# Handler implementations
# ------------------------------------------------------------------------------
def handle_openai(context):
    """
    Core OpenAI handler used by most micro-apps.

    Supports:
    - GPT-4o family
    - Text + image multimodal payloads
    - Pricing return for cost tracking

    Uses the new `OpenAI()` Python client (required for v1.x).
    The client is created inside the handler to avoid Streamlit Cloud
    injecting `proxies`, which the new SDK does not accept.
    """

    # ----------------------------------------------------------
    # Initialize OpenAI client (inside handler — critical fix)
    # ----------------------------------------------------------
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

    client = OpenAI(api_key=api_key)

    # ----------------------------------------------------------
    # Read model parameters
    # ----------------------------------------------------------
    model = context["model"]
    temperature = context["temperature"]
    max_tokens = context["max_tokens"]

    # ----------------------------------------------------------
    # Build messages payload
    # ----------------------------------------------------------
    # System message
    messages = [{"role": "system", "content": context["SYSTEM_PROMPT"]}]

    # User message
    user_prompt = context.get("user_prompt", "")
    user_content = [{"type": "text", "text": user_prompt}]

    # Optional multimodal images
    if context.get("supports_image") and context.get("image_urls"):
        for url in context["image_urls"]:
            user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages.append({"role": "user", "content": user_content})

    # ----------------------------------------------------------
    # API Call
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
        # Extract text + usage for cost calculation
        # ------------------------------------------------------
        text = response.choices[0].message.content.strip()
        usage = getattr(response, "usage", None)

        input_toks = getattr(usage, "prompt_tokens", 0)
        output_toks = getattr(usage, "completion_tokens", 0)

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
    # Add additional families here:
    # "anthropic": handle_anthropic,
    # "azure_openai": handle_azure_openai,
}
