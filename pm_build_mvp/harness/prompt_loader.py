import os

from harness.paths import PROMPTS_DIR as _PROMPTS_DIR, TEMPLATES_DIR as _TEMPLATES_DIR

_prompt_cache: dict[str, str] = {}
_template_cache: dict[str, str] = {}


def validate_prompt_files(names: list[str]) -> list[str]:
    """Return a list of prompt names whose .md files do not exist on disk.

    Use this for preflight checks before workflow execution so that all
    missing files are reported at once rather than failing on the first one.
    """
    return [name for name in names if not os.path.exists(os.path.join(_PROMPTS_DIR, f"{name}.md"))]


# Canonical list of all prompt files required by planning_workflow.
# Used for preflight validation in both main.py and planning_workflow.py.
WORKFLOW_REQUIRED_PROMPTS: list[str] = [
    "idea_gen_system", "idea_critique_system", "idea_revise_system",
    "synthesis_system", "decision_system", "founder_summary_system",
    "feature_spec_system", "tech_gen_system", "tech_review_system",
    "tech_revise_system", "product_qa_system", "strategic_qa_founder_system",
    "strategic_qa_investor_system", "decision_council_system",
    "validation_strategy_system", "failure_scenario_system",
    "consistency_guardrail_system", "escalation_system",
    "founder_intent_review",
    "kernel_guard_header", "kernel_guard_footer",
    "translator_system", "patch_agent",
]


def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/{name}.md.

    Results are cached per process in a prompt-only namespace — each file is
    read exactly once. Raises FileNotFoundError if the prompt file does not exist.
    """
    if name in _prompt_cache:
        return _prompt_cache[name]
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Expected a file named '{name}.md' inside {_PROMPTS_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _prompt_cache[name] = content
    return content


def load_template(name: str) -> str:
    """Load a template file from templates/{name}.

    Results are cached per process in a template-only namespace — isolated from
    the prompt cache to prevent key collisions when names overlap.
    Raises FileNotFoundError if the template file does not exist.
    """
    if name in _template_cache:
        return _template_cache[name]
    path = os.path.join(_TEMPLATES_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Template file not found: {path}\n"
            f"Expected a file named '{name}' inside {_TEMPLATES_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _template_cache[name] = content
    return content
