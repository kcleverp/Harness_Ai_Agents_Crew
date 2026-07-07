"""Shared PM_COGNITIVE_MEMORY helpers — single import surface for workflow modules."""
import os

from harness.cognitive_context import build_cognitive_context
from harness.prompt_loader import load_prompt


def cognitive_enabled() -> bool:
    return os.getenv("PM_COGNITIVE_MEMORY", "1").strip() not in ("0", "false", "no")


def append_cognitive_contract(system: str) -> str:
    if not cognitive_enabled():
        return system
    return system + "\n\n" + load_prompt("_cognitive_output_contract")


def inject_cognitive_context(run_id: str, context: str) -> str:
    """Prepend rejected-alternatives block when cognitive memory is on."""
    if not cognitive_enabled():
        return context
    block = build_cognitive_context(run_id)
    if not block:
        return context
    return f"{block}\n\n{context}"
