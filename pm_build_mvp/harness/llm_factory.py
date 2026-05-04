import os
from crewai import LLM

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"

def _pick_env():
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_API_BASE") or DEFAULT_BASE_URL
    model = os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL_NAME") or DEFAULT_MODEL
    return api_key, base_url, model

def validate_llm_env() -> tuple[bool, list[str]]:
    errors =[]
    api_key, base_url, model = _pick_env()
    
    if not api_key:
        errors.append("Missing API key: set OPENROUTER_API_KEY (or OPENAI_API_KEY for compatibility).")
    if not base_url.startswith("http"):
        errors.append("Invalid base URL: must start with http/https.")
    if "[" in base_url or "]" in base_url or "(" in base_url or ")" in base_url:
        errors.append("Invalid base URL format: markdown link format is not allowed.")
    if not model:
        errors.append("Missing model name: set OPENROUTER_MODEL.")
        
    return len(errors) == 0, errors

def build_llm_from_env() -> LLM:
    api_key, base_url, model = _pick_env()
    # When routing through OpenRouter, prefix the model with "openrouter/" so
    # CrewAI routes to the OpenAI-compatible provider instead of the native
    # Anthropic provider (which expects a different response format).
    if "openrouter" in base_url and not model.startswith("openrouter/"):
        model = f"openrouter/{model}"
    return LLM(
        api_key=api_key,
        base_url=base_url,
        model=model
    )

def build_translator_llm_from_env() -> LLM:
    """Translator-only LLM (Gemini Flash or equivalent fast/cheap model).

    Priority:
      1. OPENROUTER_TRANSLATOR_MODEL env var — set to the exact OpenRouter model slug,
         e.g. "google/gemini-flash-1.5" (confirm slug at openrouter.ai/models).
      2. Falls back to build_llm_from_env() if the var is missing or empty.

    API key and base URL are always reused from the primary env vars.
    """
    api_key, base_url, _ = _pick_env()
    translator_model = os.getenv("OPENROUTER_TRANSLATOR_MODEL", "").strip()

    if translator_model:
        if "openrouter" in base_url and not translator_model.startswith("openrouter/"):
            translator_model = f"openrouter/{translator_model}"
        return LLM(
            api_key=api_key,
            base_url=base_url,
            model=translator_model,
        )

    print("[translator] OPENROUTER_TRANSLATOR_MODEL not set — falling back to default LLM")
    return build_llm_from_env()
