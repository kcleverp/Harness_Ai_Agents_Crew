import os
from crewai import LLM

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Role → env var mapping (single source of truth)
_ROLE_ENV_VARS: dict[str, str] = {
    # Original roles
    "idea":              "OPENROUTER_MODEL_IDEA",
    "idea_critic":       "OPENROUTER_MODEL_IDEA_CRITIC",
    "synthesis":         "OPENROUTER_MODEL_SYNTHESIS",
    "decision":          "OPENROUTER_MODEL_DECISION",
    "creative":          "OPENROUTER_MODEL_CREATIVE",
    "tech_gen":          "OPENROUTER_MODEL_TECH_GEN",
    "tech_review":       "OPENROUTER_MODEL_TECH_REVIEW",
    # Layer 0.5 — Founder Intent Review Gate
    "intent_review":     "OPENROUTER_MODEL_INTENT_REVIEW",
    # v4 additions
    "strategic_qa":      "OPENROUTER_MODEL_STRATEGIC_QA",
    "investor_qa":       "OPENROUTER_MODEL_INVESTOR_QA",
    "council_strategic": "OPENROUTER_MODEL_COUNCIL_STRATEGIC",
    "validation":        "OPENROUTER_MODEL_VALIDATION",
    "failure_scenario":  "OPENROUTER_MODEL_FAILURE_SCENARIO",
    "consistency":       "OPENROUTER_MODEL_CONSISTENCY",
    # Escalation routing
    "escalation_logic":  "OPENROUTER_MODEL_ESCALATION_LOGIC",
    "escalation_ops":    "OPENROUTER_MODEL_ESCALATION_OPS",
    "escalation_spec":   "OPENROUTER_MODEL_ESCALATION_SPEC",
    # Layer 1~3 upstream discovery (optional)
    "user_def":          "OPENROUTER_MODEL_USER_DEF",
    "problem_discovery": "OPENROUTER_MODEL_PROBLEM",
    "opportunity":       "OPENROUTER_MODEL_OPPORTUNITY",
}

# v4 roles that are optional during startup validation (warn, do not fail)
_OPTIONAL_ROLES: frozenset[str] = frozenset({
    "intent_review",
    "strategic_qa", "investor_qa",
    "council_strategic",
    "validation", "failure_scenario", "consistency",
    "escalation_logic", "escalation_ops", "escalation_spec",
    "user_def", "problem_discovery", "opportunity",
})


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


def _build_role_llm(
    env_var: str,
    *,
    temperature: float | None = None,
    top_k: int | None = None,
) -> LLM:
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
    llm_kwargs: dict = {"api_key": api_key, "base_url": base_url, "model": model}
    if temperature is not None:
        llm_kwargs["temperature"] = temperature
    if top_k is not None:
        llm_kwargs["top_k"] = top_k
    return LLM(**llm_kwargs)


# ---------------------------------------------------------------------------
# Role-specific factory functions (Phase-aligned)
# ---------------------------------------------------------------------------

def build_idea_llm() -> LLM:
    """Phase 1 — Idea generation/revision (low-cost, e.g. gemini-2.5-flash)."""
    return _build_role_llm("OPENROUTER_MODEL_IDEA", temperature=1.0)


def build_idea_critic_llm() -> LLM:
    """Phase 1 — Idea critique (low-cost, e.g. gpt-4o-mini / gpt-5-mini)."""
    return _build_role_llm("OPENROUTER_MODEL_IDEA_CRITIC", temperature=0)


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
    return _build_role_llm("OPENROUTER_MODEL_TECH_REVIEW", temperature=0)


# ---------------------------------------------------------------------------
# v4 factory functions
# ---------------------------------------------------------------------------

def build_intent_review_llm() -> LLM:
    """Layer 0.5 — Founder Intent Review Gate (strong model, e.g. claude-opus / gpt-5)."""
    return _build_role_llm("OPENROUTER_MODEL_INTENT_REVIEW")


def build_strategic_qa_llm() -> LLM:
    """Phase C — Strategic QA: Founder Preservation Check (e.g. claude-sonnet-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_STRATEGIC_QA")


def build_investor_qa_llm() -> LLM:
    """Phase C — Strategic QA: Market Viability Check (e.g. claude-opus-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_INVESTOR_QA")


def build_council_strategic_llm() -> LLM:
    """Phase C — Decision Council: Strategic Judgment (e.g. claude-opus-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_COUNCIL_STRATEGIC")


def build_validation_llm() -> LLM:
    """Phase D — Validation Strategy Engine (e.g. claude-sonnet-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_VALIDATION")


def build_failure_scenario_llm() -> LLM:
    """Phase D — Failure Scenario Generator (e.g. gemini-2.5-flash)."""
    return _build_role_llm("OPENROUTER_MODEL_FAILURE_SCENARIO")


def build_consistency_llm() -> LLM:
    """Phase D — Cross-Document Consistency Guardrail (e.g. gpt-5-mini)."""
    return _build_role_llm("OPENROUTER_MODEL_CONSISTENCY")


def build_escalation_logic_llm() -> LLM:
    """Escalation — Logic contradiction resolver (e.g. gpt-5.5)."""
    return _build_role_llm("OPENROUTER_MODEL_ESCALATION_LOGIC")


def build_escalation_ops_llm() -> LLM:
    """Escalation — Operational ambiguity resolver (e.g. gemini-3.1-pro)."""
    return _build_role_llm("OPENROUTER_MODEL_ESCALATION_OPS")


def build_escalation_spec_llm() -> LLM:
    """Escalation — Spec inconsistency resolver (e.g. claude-sonnet-4.6)."""
    return _build_role_llm("OPENROUTER_MODEL_ESCALATION_SPEC")


def build_user_definition_llm() -> LLM:
    """Layer 1 — User definition from signals (optional)."""
    return _build_role_llm("OPENROUTER_MODEL_USER_DEF")


def build_problem_discovery_llm() -> LLM:
    """Layer 2 — Problem discovery from user model (optional)."""
    return _build_role_llm("OPENROUTER_MODEL_PROBLEM")


def build_opportunity_sizing_llm() -> LLM:
    """Layer 3 — Opportunity sizing (optional)."""
    return _build_role_llm("OPENROUTER_MODEL_OPPORTUNITY")


def build_pm_reconstruction_llm() -> LLM:
    """PM Reconstruction — persona / problem / opportunity from kernel + intent review."""
    model_key = "OPENROUTER_MODEL_PM_RECON"
    if not os.getenv(model_key, "").strip():
        if os.getenv("OPENROUTER_MODEL_USER_DEF", "").strip():
            return build_user_definition_llm()
        return build_strategic_qa_llm()
    return _build_role_llm(model_key)


# ---------------------------------------------------------------------------
# Translator (post-process Korean translation — existing path kept)
# ---------------------------------------------------------------------------

def build_translator_llm_from_env() -> LLM:
    """Translator-only LLM (Gemini Flash or equivalent fast/cheap model).

    Uses temperature=0 only — no top_k/top_p (OpenRouter/Gemini rejects top_k).

    Priority:
      1. OPENROUTER_TRANSLATOR_MODEL env var
      2. OPENROUTER_MODEL_IDEA (also flash-class) as fallback

    API key and base URL are always reused from the primary env vars.
    Raises RuntimeError if neither env var is set (should be caught by
    validate_llm_env() at startup).
    """
    api_key, base_url = _pick_connection()
    translator_model = (
        os.getenv("OPENROUTER_TRANSLATOR_MODEL", "").strip()
        or os.getenv("OPENROUTER_MODEL_IDEA", "").strip()
    )
    if translator_model:
        translator_model = _apply_openrouter_prefix(translator_model, base_url)
        return LLM(
            api_key=api_key, base_url=base_url, model=translator_model,
            temperature=0,
        )

    # This branch is unreachable: validate_llm_env() halts startup when
    # OPENROUTER_MODEL_IDEA is absent, so the or-chain above always resolves.
    raise RuntimeError(
        "[translator] Neither OPENROUTER_TRANSLATOR_MODEL nor OPENROUTER_MODEL_IDEA "
        "is set — this path should have been caught by validate_llm_env() at startup."
    )


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_llm_env() -> tuple[bool, list[str]]:
    """Validate all required env vars before the workflow starts.

    Checks:
    - OPENROUTER_API_KEY presence
    - OPENROUTER_BASE_URL validity (http/https, no markdown format)
    - All required role-specific model env vars (hard errors)
    - Optional v4 role env vars (warn-only, printed but do not fail)
    """
    errors: list[str] = []
    warnings: list[str] = []
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
            if role in _OPTIONAL_ROLES:
                warnings.append(
                    f"[WARN] v4 model not configured for role '{role}': {env_var} "
                    "(optional — phase will be skipped if not set)"
                )
            else:
                errors.append(f"Missing model for role '{role}': set {env_var} in .env.")

    if warnings:
        print("\n".join(warnings))

    return len(errors) == 0, errors
