# ------------------------------------------------------------------------------
# Refactor date: 2025-11-14
# Refactored by: Imaad Fakier
# Purpose: Align Discussion Generator micro-app with OES GenAI Streamlit standards,
#          and update to new OpenAI Python SDK (v1.x) without proxy issues.
# ------------------------------------------------------------------------------
"""
core_logic.handlers (Refactored: New OpenAI SDK)
------------------------------------------------
Provides per-family LLM invocation handlers.

This refactor:
- Switches to `OpenAI()` client (new SDK)
- Removes deprecated `openai.chat.completions.create`
- Avoids all `httpx` / proxy injection issues on Streamlit Cloud
- Preserves exponential backoff
- Preserves multi-modal (text + images) support
- Output structure unchanged → (response_text, execution_price)
"""

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
    Intended for transient failures (timeouts, rate limits, etc.).
    """
    delay = 0.5
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == 4:
                raise
            wait = delay + random.random() * delay
            st.warning(f"Retrying after transient error: {e} (wait {wait:.1f}s)")
            time.sleep(wait)
            delay *= 2


# ------------------------------------------------------------------------------
# Handler implementations
# ------------------------------------------------------------------------------
def handle_openai(context):
    """
    Core OpenAI handler used by most micro-apps.
    Updated for the new OpenAI Python SDK (v1.x).
    Supports:
    - text-only calls
    - multimodal (text + image_url)
    Returns:
        (response_text, execution_price)
    """

    client = OpenAI()  # Safe: handles API keys + avoids proxy conflicts automatically

    model = context["model"]
    temperature = context["temperature"]
    max_tokens = context["max_tokens"]

    # Build message payload with image support
    user_prompt = context.get("user_prompt", "")
    user_content = [{"type": "text", "text": user_prompt}]

    if context.get("supports_image") and context.get("image_urls"):
        for url in context["image_urls"]:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })

    messages = [
        {"role": "system", "content": context["SYSTEM_PROMPT"]},
        {"role": "user", "content": user_content},
    ]

    try:
        # New SDK call (chat.completions.create still supported but rewritten safely)
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

        text = response.choices[0].message.content.strip()

        # Pricing calculations preserved for compatibility
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
    # "anthropic": handle_anthropic,
    # "azure_openai": handle_azure_openai,
}
