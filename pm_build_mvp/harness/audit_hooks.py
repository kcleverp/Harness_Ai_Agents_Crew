import json
import os
import uuid
import datetime
import warnings
from typing import Optional

from harness.telemetry_schema import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Transition compatibility policy
#
# The following phase-centric log files are in TRANSITION (deprecated):
#   decision_history.log  blueprint_logic.log  creative_process.log  patch_actions.log
#
# These files continue to be written for backward compatibility during the
# transition period, but callers SHOULD pass run_id so that the canonical
# stream (reasoning_trace.jsonl) is the primary write target.
#
# Transition end: when all callers pass run_id, legacy file writes will be removed.
# ---------------------------------------------------------------------------

_DEPRECATED_DIRECT_LOGS = frozenset({
    "decision_history.log",
    "blueprint_logic.log",
    "creative_process.log",
    "patch_actions.log",
})

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
os.makedirs(LOG_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Core append primitive
# ---------------------------------------------------------------------------

def append_log(filename: str, message: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LOG_DIR, filename), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


# ---------------------------------------------------------------------------
# Internal formatter
# Assembles key=value pairs into a single pipe-delimited line.
# None values are skipped so callers don't need to guard every field.
# ---------------------------------------------------------------------------

def _fmt(**kwargs) -> str:
    return " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)


# ---------------------------------------------------------------------------
# Canonical stream — reasoning_trace.jsonl
#
# PRIMARY write target for all structured events (schema v1).
# Append-only. One JSON object per line.
# Supports causality chain via parent_event_id.
#
# domain/category taxonomy (declared by event, not inferred by projection):
#   workflow/lifecycle | decision/selection | decision/tradeoff
#   qa/validation | qa/patching | qa/integrity | qa/escalation | qa/consistency
#   system/kernel | system/config | patch/repair | translation/sync
# ---------------------------------------------------------------------------

def log_reasoning_event(
    run_id: str,
    phase: str,
    event_type: str,
    artifact: Optional[str] = None,
    details: Optional[dict] = None,
    parent_event_id: Optional[str] = None,
    domain: Optional[str] = None,
    category: Optional[str] = None,
    related_event_ids: Optional[list] = None,
) -> str:
    """Append one structured event to reasoning_trace.jsonl (canonical stream).

    Returns event_id for causality chaining (pass as parent_event_id downstream).
    The file is append-only and must never be truncated or rewritten.

    domain/category embed event meaning per schema v1.
    Defaults to workflow/lifecycle for legacy callers that omit them.
    related_event_ids is reserved for future DAG lineage (default []).
    """
    event_id = str(uuid.uuid4())
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "parent_event_id": parent_event_id,
        "related_event_ids": related_event_ids if related_event_ids is not None else [],
        "run_id": run_id,
        "phase": phase,
        "domain": domain or "workflow",
        "category": category or "lifecycle",
        "event_type": event_type,
        "artifact": artifact,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "details": details or {},
    }
    line = json.dumps(record, ensure_ascii=False)
    with open(os.path.join(LOG_DIR, "reasoning_trace.jsonl"), "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return event_id


# ---------------------------------------------------------------------------
# Technical logs — run_summary.log
# ---------------------------------------------------------------------------

def log_run_summary(
    success: bool,
    files: list,
    task_count: int,
    risk_score: int,
    patch_attempts: int = 0,
    risk_reasons_count: int = 0,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    status = "SUCCESS" if success else "FAILED"
    msg = (
        f"Status={status} | Files={len(files)} | Tasks={task_count} | "
        f"Risk={risk_score} | Patches={patch_attempts} | RiskReasons={risk_reasons_count}"
    )
    append_log("run_summary.log", msg)

    if run_id:
        log_reasoning_event(
            run_id=run_id,
            phase="summary",
            event_type="run_end",
            domain="workflow",
            category="lifecycle",
            details={
                "status": status,
                "files": len(files),
                "tasks": task_count,
                "risk_score": risk_score,
                "patch_attempts": patch_attempts,
                "risk_reasons_count": risk_reasons_count,
            },
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Technical logs — validation_failures.log
# ---------------------------------------------------------------------------

def log_validation_error(
    filename: str,
    path: str,
    reason: str,
    attempt: int,
    error_code: str = "SCHEMA_MISMATCH",
    run_id: Optional[str] = None,
    phase: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    msg = _fmt(File=filename, Path=path, Code=error_code, Reason=reason, Attempt=attempt)
    append_log("validation_failures.log", msg)

    if run_id:
        log_reasoning_event(
            run_id=run_id,
            phase=phase or "validation",
            event_type="schema_mismatch",
            domain="qa",
            category="validation",
            artifact=filename,
            details={"path": path, "reason": reason, "attempt": attempt, "error_code": error_code},
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Technical logs — patch_actions.log
# ---------------------------------------------------------------------------

def log_patch_action(
    filename: str,
    patch_target: str,
    result: str,
    error_code: str = "PATCH_ATTEMPT",
    run_id: Optional[str] = None,
    phase: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    """Record a patch operation.

    Canonical emit (when run_id provided): domain=qa, category=patching.
    Legacy text log (patch_actions.log) written for compatibility — DEPRECATED.
    Pass run_id to suppress this warning and emit to canonical stream only.
    """
    msg = _fmt(File=filename, Target=patch_target, Code=error_code, Result=result)
    append_log("patch_actions.log", msg)
    if not run_id:
        warnings.warn(
            "log_patch_action called without run_id — writing to legacy patch_actions.log only. "
            "Pass run_id to emit to canonical stream.",
            DeprecationWarning, stacklevel=2,
        )

    if run_id:
        event_type = "patch_applied" if "success" in result.lower() else "patch_failed"
        log_reasoning_event(
            run_id=run_id,
            phase=phase or "patching",
            event_type=event_type,
            domain="qa",
            category="patching",
            artifact=filename,
            details={"patch_target": patch_target, "result": result, "error_code": error_code},
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Operational logs — pm_audit.log
# ---------------------------------------------------------------------------

def log_pm_audit(message: str):
    """Free-form audit message. Kept for backward compat and simple status lines."""
    append_log("pm_audit.log", message)


def log_pm_audit_event(
    phase: str,
    status: str,
    model: Optional[str] = None,
    selected: Optional[str] = None,
    rejected: Optional[str] = None,
    risk: Optional[str] = None,
    output: Optional[str] = None,
    summary_ko: Optional[str] = None,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    """Structured phase lifecycle event.

    Canonical emit (when run_id provided): domain=workflow, category=lifecycle.
    Legacy text log (pm_audit.log) always written for compatibility.
    """
    msg = _fmt(
        Phase=phase, Status=status, Model=model,
        Selected=selected, Rejected=rejected,
        Risk=risk, Output=output, SummaryKo=summary_ko,
    )
    append_log("pm_audit.log", msg)

    if run_id:
        event_type = "phase_start" if status.upper() == "START" else "phase_end"
        log_reasoning_event(
            run_id=run_id,
            phase=phase,
            event_type=event_type,
            domain="workflow",
            category="lifecycle",
            artifact=output,
            details={
                "status": status, "model": model,
                "selected": selected, "rejected": rejected,
                "risk": risk, "summary_ko": summary_ko,
            },
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Operational logs — decision_history.log
# ---------------------------------------------------------------------------

def log_decision_history(
    phase: str,
    rejected: str,
    reason: Optional[str] = None,
    risk: Optional[str] = None,
    summary_ko: Optional[str] = None,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    """Record a rejected option and its rationale.

    Canonical emit (when run_id provided): domain=decision, category=selection.
    Legacy text log (decision_history.log) written for compatibility — DEPRECATED.
    Pass run_id to suppress this warning and emit to canonical stream only.
    """
    msg = _fmt(Phase=phase, Rejected=rejected, Reason=reason, Risk=risk, SummaryKo=summary_ko)
    append_log("decision_history.log", msg)
    if not run_id:
        warnings.warn(
            "log_decision_history called without run_id — writing to legacy decision_history.log only. "
            "Pass run_id to emit to canonical stream.",
            DeprecationWarning, stacklevel=2,
        )

    if run_id:
        log_reasoning_event(
            run_id=run_id,
            phase=phase,
            event_type="option_rejected",
            domain="decision",
            category="selection",
            details={"rejected": rejected, "reason": reason, "risk": risk, "summary_ko": summary_ko},
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Operational logs — blueprint_logic.log
# ---------------------------------------------------------------------------

def log_blueprint_logic(
    phase: str,
    selected: Optional[str] = None,
    rejected: Optional[str] = None,
    trade_off: Optional[str] = None,
    reason: Optional[str] = None,
    summary_ko: Optional[str] = None,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    """Record Decision-phase structural/technical choices.

    Canonical emit (when run_id provided): domain=decision, category=tradeoff.
    Legacy text log (blueprint_logic.log) written for compatibility — DEPRECATED.
    Pass run_id to suppress this warning and emit to canonical stream only.
    """
    msg = _fmt(
        Phase=phase, Selected=selected, Rejected=rejected,
        TradeOff=trade_off, Reason=reason, SummaryKo=summary_ko,
    )
    append_log("blueprint_logic.log", msg)
    if not run_id:
        warnings.warn(
            "log_blueprint_logic called without run_id — writing to legacy blueprint_logic.log only. "
            "Pass run_id to emit to canonical stream.",
            DeprecationWarning, stacklevel=2,
        )

    if run_id:
        log_reasoning_event(
            run_id=run_id,
            phase=phase,
            event_type="tradeoff_recorded",
            domain="decision",
            category="tradeoff",
            details={
                "selected": selected, "rejected": rejected,
                "trade_off": trade_off, "reason": reason, "summary_ko": summary_ko,
            },
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Operational logs — creative_process.log
# ---------------------------------------------------------------------------

def log_creative_process(
    phase: str,
    selected: Optional[str] = None,
    rejected: Optional[str] = None,
    reason: Optional[str] = None,
    summary_ko: Optional[str] = None,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
):
    """Record Creative Production narrative direction choices.

    Canonical emit (when run_id provided): domain=decision, category=selection.
    Legacy text log (creative_process.log) written for compatibility — DEPRECATED.
    Pass run_id to suppress this warning and emit to canonical stream only.
    """
    msg = _fmt(Phase=phase, Selected=selected, Rejected=rejected, Reason=reason, SummaryKo=summary_ko)
    append_log("creative_process.log", msg)
    if not run_id:
        warnings.warn(
            "log_creative_process called without run_id — writing to legacy creative_process.log only. "
            "Pass run_id to emit to canonical stream.",
            DeprecationWarning, stacklevel=2,
        )

    if run_id:
        log_reasoning_event(
            run_id=run_id,
            phase=phase,
            event_type="option_selected",
            domain="decision",
            category="selection",
            details={"selected": selected, "rejected": rejected, "reason": reason, "summary_ko": summary_ko},
            parent_event_id=parent_event_id,
        )


# ---------------------------------------------------------------------------
# Integrity / override events — reasoning_trace.jsonl only
# ---------------------------------------------------------------------------

def log_system_integrity_alert(
    run_id: str,
    phase: str,
    claim: str,
    source_ref: str,
    parent_event_id: Optional[str] = None,
) -> str:
    """Trust boundary breach (fabricated founder evidence).

    domain=qa / category=integrity / event_type=system_integrity_alert.
    Triggers immediate reject — NOT escalation.
    """
    return log_reasoning_event(
        run_id=run_id,
        phase=phase,
        event_type="system_integrity_alert",
        domain="qa",
        category="integrity",
        artifact="evidence_binding",
        details={
            "violation": "fabricated_founder_evidence",
            "claim": claim,
            "source_ref": source_ref,
            "action": "immediate_reject",
        },
        parent_event_id=parent_event_id,
    )


def log_founder_override(
    run_id: str,
    phase: str,
    reason: str,
    override_details: Optional[dict] = None,
    parent_event_id: Optional[str] = None,
) -> str:
    """Founder override event (AI average prevention).

    domain=system / category=kernel / event_type=founder_override.
    """
    return log_reasoning_event(
        run_id=run_id,
        phase=phase,
        event_type="founder_override",
        domain="system",
        category="kernel",
        artifact="founder_kernel",
        details={"reason": reason, **(override_details or {})},
        parent_event_id=parent_event_id,
    )
