"""Validate cognitive blocks and retry LLM calls on critical phases."""
from __future__ import annotations

from harness.cognitive_parser import PhaseCognitiveResult, parse_phase_response
from harness.cognitive_utils import cognitive_enabled

CRITICAL_PHASES = frozenset({
    "IntentReview",
    "UserDefinition",
    "ProblemDiscovery",
    "OpportunitySizing",
    "Decision",
    "DecisionCouncil",
})


def validate_decision_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    if not graph:
        return ["decision_graph missing or empty"]
    selected = graph.get("selected")
    if not isinstance(selected, list) or len(selected) == 0:
        errors.append("decision_graph.selected must contain at least 1 item")
    else:
        for i, item in enumerate(selected):
            if not isinstance(item, dict):
                errors.append(f"selected[{i}] must be an object")
                continue
            if not (item.get("rationale") or "").strip():
                errors.append(f"selected[{i}] missing rationale")
    rejected = graph.get("rejected")
    if rejected is not None and not isinstance(rejected, list):
        errors.append("decision_graph.rejected must be an array")
    tradeoffs = graph.get("tradeoffs")
    if tradeoffs is not None and not isinstance(tradeoffs, list):
        errors.append("decision_graph.tradeoffs must be an array")
    return errors


def validate_cognitive_output(cognitive: PhaseCognitiveResult, phase: str) -> list[str]:
    errors: list[str] = []
    if phase in CRITICAL_PHASES and not (cognitive.thinking_text or "").strip():
        errors.append("thinking block missing or empty")
    errors.extend(validate_decision_graph(cognitive.decision_graph))
    return errors


def call_with_cognitive_retry(
    llm,
    messages: list[dict],
    phase: str,
    *,
    max_attempts: int = 2,
) -> tuple[str, PhaseCognitiveResult]:
    """Call LLM; on critical phases retry when cognitive blocks are invalid."""
    raw = llm.call(messages)
    cognitive = parse_phase_response(raw, phase)
    if not cognitive_enabled() or phase not in CRITICAL_PHASES:
        return raw, cognitive

    errors = validate_cognitive_output(cognitive, phase)
    attempt = 1
    while errors and attempt < max_attempts:
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (
                "Your response failed cognitive validation. Fix and resend the FULL response:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\n\nRequired: <thinking> block, then <decision_graph> with at least one "
                "selected item including rationale, then the final artifact."
            )},
        ]
        raw = llm.call(retry_messages)
        cognitive = parse_phase_response(raw, phase)
        errors = validate_cognitive_output(cognitive, phase)
        attempt += 1

    return raw, cognitive
