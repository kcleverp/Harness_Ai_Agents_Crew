import os
from crewai import LLM

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Role → env var mapping (single source of truth)
_ROLE_ENV_VARS: dict[str, str] = {
    "idea":          "OPENROUTER_MODEL_IDEA",
    "idea_critic":   "OPENROUTER_MODEL_IDEA_CRITIC",
    "synthesis":     "OPENROUTER_MODEL_SYNTHESIS",
    "decision":      "OPENROUTER_MODEL_DECISION",
    "creative":      "OPENROUTER_MODEL_CREATIVE",
    "tech_gen":      "OPENROUTER_MODEL_TECH_GEN",
    "tech_review":   "OPENROUTER_MODEL_TECH_REVIEW",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pick_connection() -> tuple[str, str]:
    """Return (api_key, base_url) from environment."""
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("OPENROUTER_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_BASE_URL
    )
    return api_key, base_url


def _apply_openrouter_prefix(model: str, base_url: str) -> str:
    """Prefix model slug with 'openrouter/' when routing via OpenRouter."""
    if "openrouter" in base_url and not model.startswith("openrouter/"):
        return f"openrouter/{model}"
    return model


def _build_role_llm(env_var: str) -> LLM:
    """Build an LLM for a specific role from its dedicated env var.

    Raises ValueError if the env var is missing or empty.
    No silent fallback to a default model.
    """
    api_key, base_url = _pick_connection()
    model = os.getenv(env_var, "").strip()
    if not model:
        raise ValueError(
            f"Missing required model env var: {env_var}. "
            "Set the correct OpenRouter model slug in .env before running."
        )
    model = _apply_openrouter_prefix(model, base_url)
    return LLM(api_key=api_key, base_url=base_url, model=model)


# ---------------------------------------------------------------------------
# Role-specific factory functions (Phase-aligned)
# ---------------------------------------------------------------------------

def build_idea_llm() -> LLM:
    """Phase 1 — Idea generation/revision (low-cost, e.g. gemini-2.5-flash)."""
    return _build_role_llm("OPENROUTER_MODEL_IDEA")


def build_idea_critic_llm() -> LLM:
    """Phase 1 — Idea critique (low-cost, e.g. gpt-4o-mini / gpt-5-mini)."""
    return _build_role_llm("OPENROUTER_MODEL_IDEA_CRITIC")


def build_synthesis_llm() -> LLM:
    """Phase 2 — Synthesis/structuring (low-cost, e.g. gpt-4o-mini / gpt-5-mini)."""
    return _build_role_llm("OPENROUTER_MODEL_SYNTHESIS")


def build_decision_llm() -> LLM:
    """Phase 3 — Decision/architecture (high-quality, e.g. claude-opus-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_DECISION")


def build_creative_llm() -> LLM:
    """Phase 4 — Creative production (high-quality, e.g. claude-sonnet-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_CREATIVE")


def build_technical_gen_llm() -> LLM:
    """Phase 5 — Technical JSON generation (low-cost, e.g. gemini-2.5-flash)."""
    return _build_role_llm("OPENROUTER_MODEL_TECH_GEN")


def build_technical_review_llm() -> LLM:
    """Phase 5 — Technical review/correction planning (low-cost, e.g. gpt-4o-mini)."""
    return _build_role_llm("OPENROUTER_MODEL_TECH_REVIEW")


# ---------------------------------------------------------------------------
# Translator (post-process Korean translation — existing path kept)
# ---------------------------------------------------------------------------

def build_translator_llm_from_env() -> LLM:
    """Translator-only LLM (Gemini Flash or equivalent fast/cheap model).

    Priority:
      1. OPENROUTER_TRANSLATOR_MODEL env var
      2. OPENROUTER_MODEL_IDEA (also flash-class) as fallback
      3. build_llm_from_env() as last resort

    API key and base URL are always reused from the primary env vars.
    """
    api_key, base_url = _pick_connection()
    translator_model = (
        os.getenv("OPENROUTER_TRANSLATOR_MODEL", "").strip()
        or os.getenv("OPENROUTER_MODEL_IDEA", "").strip()
    )
    if translator_model:
        translator_model = _apply_openrouter_prefix(translator_model, base_url)
        return LLM(api_key=api_key, base_url=base_url, model=translator_model)

    print("[translator] No translator model found — falling back to build_llm_from_env()")
    return build_llm_from_env()


# ---------------------------------------------------------------------------
# Legacy / backward compat (used by patch_engine.py only)
# ---------------------------------------------------------------------------

def _pick_env():
    """Legacy helper — kept for backward compat with patch_engine.py."""
    api_key, base_url = _pick_connection()
    model = os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL_NAME") or ""
    return api_key, base_url, model


def build_llm_from_env() -> LLM:
    """Legacy default LLM — used by patch_engine.py only.

    Still reads OPENROUTER_MODEL for backward compat.
    New phase code must use the role-specific build_*_llm() functions instead.
    """
    api_key, base_url, model = _pick_env()
    if model:
        model = _apply_openrouter_prefix(model, base_url)
    return LLM(api_key=api_key, base_url=base_url, model=model)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_llm_env() -> tuple[bool, list[str]]:
    """Validate all required env vars before the workflow starts.

    Checks:
    - OPENROUTER_API_KEY presence
    - OPENROUTER_BASE_URL validity (http/https, no markdown format)
    - All 7 role-specific model env vars
    """
    errors: list[str] = []
    api_key, base_url = _pick_connection()

    if not api_key:
        errors.append(
            "Missing API key: set OPENROUTER_API_KEY (or OPENAI_API_KEY for compatibility)."
        )

    if not base_url.startswith("http"):
        errors.append("Invalid base URL: must start with http/https.")

    if any(c in base_url for c in "[]()"):
        errors.append("Invalid base URL format: markdown link format is not allowed.")

    for role, env_var in _ROLE_ENV_VARS.items():
        if not os.getenv(env_var, "").strip():
            errors.append(f"Missing model for role '{role}': set {env_var} in .env.")

    return len(errors) == 0, errors
