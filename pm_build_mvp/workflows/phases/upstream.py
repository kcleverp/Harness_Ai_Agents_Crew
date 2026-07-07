"""
upstream.py — Layer 1~3 discovery phases (proceed-guarded, optional).

Skipped when OPENROUTER_MODEL_USER_DEF is unset (falls back to raw_ideas.md idea loop).
"""
import glob
import json
import os

from harness.audit_hooks import log_pm_audit, log_pm_audit_event, log_reasoning_event
from harness.cognitive_logger import record_cognitive_output
from harness.cognitive_validate import call_with_cognitive_retry
from harness.confidence_scoring import (
    compute_opportunity_confidence,
    compute_problem_discovery_confidence,
    compute_user_definition_confidence,
)
from harness.cognitive_utils import append_cognitive_contract, cognitive_enabled, inject_cognitive_context
from harness.kernel_guard import inject_kernel_guard
from harness.llm_factory import (
    build_opportunity_sizing_llm,
    build_problem_discovery_llm,
    build_user_definition_llm,
)
from harness.paths import OPP_DIR, SIGNALS_DIR, USER_DIR
from harness.prompt_loader import load_prompt
from harness.safe_file_tools import read_workspace_file, write_workspace_file

_USER_DEF_SYSTEM = load_prompt("user_definition_system")
_PROBLEM_SYSTEM = load_prompt("problem_discovery_system")
_OPP_SYSTEM = load_prompt("opportunity_sizing_system")


def _parse_json_phase(raw: str, fallback: dict, phase_label: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        log_pm_audit(f"{phase_label} | JSON parse failed — using fallback")
    return fallback


def _collect_signals() -> str:
    if not os.path.isdir(SIGNALS_DIR):
        return "(no signals/ directory — using kernel context only)"
    parts = []
    for pattern in ("*.md", "*.json"):
        for path in sorted(glob.glob(os.path.join(SIGNALS_DIR, pattern))):
            name = os.path.basename(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    parts.append(f"### signals/{name}\n{f.read()}")
            except OSError:
                continue
    return "\n\n".join(parts) if parts else "(signals/ empty)"


def upstream_enabled() -> bool:
    mode = os.getenv("PM_UPSTREAM_MODE", "on").strip().lower()
    if mode in ("off", "0", "false", "skip"):
        return False
    return bool(os.getenv("OPENROUTER_MODEL_USER_DEF", "").strip())


def run_user_definition(kernel_data: dict, run_id: str = "") -> dict:
    if not upstream_enabled():
        log_pm_audit("UserDefinition | Status=SKIPPED | Reason=OPENROUTER_MODEL_USER_DEF not configured")
        return {"skipped": True}

    os.makedirs(USER_DIR, exist_ok=True)
    phase_event = log_pm_audit_event(
        "UserDefinition", "START",
        run_id=run_id, output="current/user/user_model.json",
    )

    signals = _collect_signals()
    system = append_cognitive_contract(inject_kernel_guard(_USER_DEF_SYSTEM, kernel_data))
    user_content = inject_cognitive_context(
        run_id,
        f"Define the user model from these inputs:\n\n{signals}",
    )

    llm = build_user_definition_llm()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
    if cognitive_enabled():
        raw, cognitive = call_with_cognitive_retry(llm, messages, "UserDefinition")
        record_cognitive_output(
            run_id, "UserDefinition", cognitive.thinking_text, cognitive.decision_graph,
            artifact="current/user/user_model.json", parent_event_id=phase_event,
        )
        artifact_body = cognitive.artifact_body
    else:
        raw = llm.call(messages)
        artifact_body = raw

    result = _parse_json_phase(
        artifact_body,
        {"icp": "", "personas": [], "jtbd": [], "customer_segments": []},
        "UserDefinition",
    )
    result["confidence"] = compute_user_definition_confidence(result)
    write_workspace_file("current/user/user_model.json", json.dumps(result, indent=2, ensure_ascii=False))

    log_reasoning_event(
        run_id=run_id, phase="UserDefinition", event_type="user_model_generated",
        domain="discovery", category="user", artifact="current/user/user_model.json",
        details={"ko_summary": result.get("ko_summary"), "confidence": result.get("confidence")},
        parent_event_id=phase_event,
    )
    log_pm_audit_event("UserDefinition", "END", output="current/user/user_model.json", run_id=run_id)
    return result


def run_problem_discovery(run_id: str = "") -> dict:
    if not upstream_enabled():
        return {"skipped": True}

    os.makedirs(OPP_DIR, exist_ok=True)
    phase_event = log_pm_audit_event(
        "ProblemDiscovery", "START",
        run_id=run_id, output="current/opportunity/problem_statement.json",
    )

    user_model_raw = read_workspace_file("current/user/user_model.json")
    if user_model_raw.startswith("Error:"):
        log_pm_audit("ProblemDiscovery | Status=SKIPPED | Reason=user_model.json missing")
        return {"skipped": True}

    system = append_cognitive_contract(_PROBLEM_SYSTEM)
    llm = build_problem_discovery_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Extract problem statement from user model:\n\n{user_model_raw}"},
    ]
    if cognitive_enabled():
        raw, cognitive = call_with_cognitive_retry(llm, messages, "ProblemDiscovery")
        record_cognitive_output(
            run_id, "ProblemDiscovery", cognitive.thinking_text, cognitive.decision_graph,
            artifact="current/opportunity/problem_statement.json", parent_event_id=phase_event,
        )
        artifact_body = cognitive.artifact_body
    else:
        raw = llm.call(messages)
        artifact_body = raw

    result = _parse_json_phase(
        artifact_body,
        {"pain_points": [], "problem_statement": ""},
        "ProblemDiscovery",
    )
    result["confidence"] = compute_problem_discovery_confidence(result)
    write_workspace_file(
        "current/opportunity/problem_statement.json",
        json.dumps(result, indent=2, ensure_ascii=False),
    )

    log_reasoning_event(
        run_id=run_id, phase="ProblemDiscovery", event_type="problem_statement_created",
        domain="discovery", category="problem",
        artifact="current/opportunity/problem_statement.json",
        details={"ko_summary": result.get("ko_summary"), "confidence": result.get("confidence")},
        parent_event_id=phase_event,
    )
    log_pm_audit_event(
        "ProblemDiscovery", "END",
        output="current/opportunity/problem_statement.json", run_id=run_id,
    )
    return result


def run_opportunity_sizing(kernel_data: dict, run_id: str = "") -> dict:
    if not os.getenv("OPENROUTER_MODEL_OPPORTUNITY", "").strip():
        log_pm_audit("OpportunitySizing | Status=SKIPPED | Reason=OPENROUTER_MODEL_OPPORTUNITY not configured")
        return {"skipped": True}

    os.makedirs(OPP_DIR, exist_ok=True)
    phase_event = log_pm_audit_event(
        "OpportunitySizing", "START",
        run_id=run_id, output="current/opportunity/opportunity_model.json",
    )

    problem_raw = read_workspace_file("current/opportunity/problem_statement.json")
    if problem_raw.startswith("Error:"):
        log_pm_audit("OpportunitySizing | Status=SKIPPED | Reason=problem_statement.json missing")
        return {"skipped": True}

    system = append_cognitive_contract(inject_kernel_guard(_OPP_SYSTEM, kernel_data))
    llm = build_opportunity_sizing_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Size this opportunity:\n\n{problem_raw}"},
    ]
    if cognitive_enabled():
        raw, cognitive = call_with_cognitive_retry(llm, messages, "OpportunitySizing")
        record_cognitive_output(
            run_id, "OpportunitySizing", cognitive.thinking_text, cognitive.decision_graph,
            artifact="current/opportunity/opportunity_model.json", parent_event_id=phase_event,
        )
        artifact_body = cognitive.artifact_body
    else:
        raw = llm.call(messages)
        artifact_body = raw

    result = _parse_json_phase(
        artifact_body,
        {"priority_score": 0, "recommended_direction": "investigate"},
        "OpportunitySizing",
    )
    result["confidence"] = compute_opportunity_confidence(result)
    write_workspace_file(
        "current/opportunity/opportunity_model.json",
        json.dumps(result, indent=2, ensure_ascii=False),
    )

    log_reasoning_event(
        run_id=run_id, phase="OpportunitySizing", event_type="opportunity_scored",
        domain="discovery", category="opportunity",
        artifact="current/opportunity/opportunity_model.json",
        details={
            "priority_score": result.get("priority_score"),
            "recommended_direction": result.get("recommended_direction"),
            "confidence": result.get("confidence"),
            "ko_summary": result.get("ko_summary"),
        },
        parent_event_id=phase_event,
    )
    log_pm_audit_event(
        "OpportunitySizing", "END",
        output="current/opportunity/opportunity_model.json", run_id=run_id,
    )
    return result
