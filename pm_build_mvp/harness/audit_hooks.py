import json
import os
import uuid
import datetime
from typing import Optional

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
# Technical logs (English / structured — no Korean translation)
# ---------------------------------------------------------------------------

def log_run_summary(
    success: bool,
    files: list,
    task_count: int,
    risk_score: int,
    patch_attempts: int = 0,
    risk_reasons_count: int = 0,
):
    status = "SUCCESS" if success else "FAILED"
    msg = (
        f"Status={status} | Files={len(files)} | Tasks={task_count} | "
        f"Risk={risk_score} | Patches={patch_attempts} | RiskReasons={risk_reasons_count}"
    )
    append_log("run_summary.log", msg)


def log_validation_error(
    filename: str,
    path: str,
    reason: str,
    attempt: int,
    error_code: str = "SCHEMA_MISMATCH",
):
    msg = _fmt(File=filename, Path=path, Code=error_code, Reason=reason, Attempt=attempt)
    append_log("validation_failures.log", msg)


def log_patch_action(
    filename: str,
    patch_target: str,
    result: str,
    error_code: str = "PATCH_ATTEMPT",
):
    msg = _fmt(File=filename, Target=patch_target, Code=error_code, Result=result)
    append_log("patch_actions.log", msg)


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
):
    """Structured phase lifecycle event for pm_audit.log.

    Typical use:
        log_pm_audit_event("IdeaLoop", "START", model="gemini-2.5-flash,gpt-4o-mini")
        log_pm_audit_event("IdeaLoop", "END",
                           selected="task CRUD MVP",
                           rejected="referral,billing",
                           risk="auth scope unclear",
                           summary_ko="핵심 기능은 CRUD 중심 MVP로 정리함")
    """
    msg = _fmt(
        Phase=phase,
        Status=status,
        Model=model,
        Selected=selected,
        Rejected=rejected,
        Risk=risk,
        Output=output,
        SummaryKo=summary_ko,
    )
    append_log("pm_audit.log", msg)


# ---------------------------------------------------------------------------
# Operational logs — decision_history.log
# ---------------------------------------------------------------------------

def log_decision_history(
    phase: str,
    rejected: str,
    reason: Optional[str] = None,
    risk: Optional[str] = None,
    summary_ko: Optional[str] = None,
):
    """Record a rejected option and its rationale.

    Typical use:
        log_decision_history("Synthesis",
                             rejected="subscription billing",
                             reason="non-MVP scope",
                             risk="payment complexity",
                             summary_ko="결제 기능은 MVP 범위 초과로 제외")
    """
    msg = _fmt(
        Phase=phase,
        Rejected=rejected,
        Reason=reason,
        Risk=risk,
        SummaryKo=summary_ko,
    )
    append_log("decision_history.log", msg)


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
):
    """Record Decision-phase structural/technical choices.

    Typical use:
        log_blueprint_logic("Decision",
                            selected="Supabase",
                            rejected="Firebase",
                            reason="faster MVP backend alignment",
                            summary_ko="Supabase가 MVP 구현 속도 면에서 더 적합")
    """
    msg = _fmt(
        Phase=phase,
        Selected=selected,
        Rejected=rejected,
        TradeOff=trade_off,
        Reason=reason,
        SummaryKo=summary_ko,
    )
    append_log("blueprint_logic.log", msg)


# ---------------------------------------------------------------------------
# Operational logs — creative_process.log
# ---------------------------------------------------------------------------

def log_creative_process(
    phase: str,
    selected: Optional[str] = None,
    rejected: Optional[str] = None,
    reason: Optional[str] = None,
    summary_ko: Optional[str] = None,
):
    """Record Creative Production narrative direction choices.

    Typical use:
        log_creative_process("CreativeProd",
                             selected="clarity over feature breadth",
                             summary_ko="기능 나열보다 핵심 사용 흐름 설명을 우선")
    """
    msg = _fmt(
        Phase=phase,
        Selected=selected,
        Rejected=rejected,
        Reason=reason,
        SummaryKo=summary_ko,
    )
    append_log("creative_process.log", msg)


# ---------------------------------------------------------------------------
# Structured Decision Memory — reasoning_trace.jsonl
#
# Append-only, one JSON object per line.
# Supports causality links via parent_event_id.
# Query keys: run_id, phase, artifact, event_type
#
# Event types:
#   critique_generated | conflict_detected | escalation_triggered
#   founder_override | system_integrity_alert | validation_warning
#   council_approved | council_rejected | kernel_hash_verified
#   kernel_hash_mismatch | confidence_penalty_applied
# ---------------------------------------------------------------------------

def log_reasoning_event(
    run_id: str,
    phase: str,
    event_type: str,
    artifact: Optional[str] = None,
    details: Optional[dict] = None,
    parent_event_id: Optional[str] = None,
) -> str:
    """Append one structured reasoning event to reasoning_trace.jsonl.

    Returns the generated event_id so the caller can pass it as
    parent_event_id to downstream events (causality chain).

    The file is append-only and must never be truncated or rewritten.
    """
    event_id = str(uuid.uuid4())
    record = {
        "event_id": event_id,
        "parent_event_id": parent_event_id,
        "run_id": run_id,
        "phase": phase,
        "event_type": event_type,
        "artifact": artifact,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "details": details or {},
    }
    line = json.dumps(record, ensure_ascii=False)
    with open(os.path.join(LOG_DIR, "reasoning_trace.jsonl"), "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return event_id


def log_system_integrity_alert(
    run_id: str,
    phase: str,
    claim: str,
    source_ref: str,
    parent_event_id: Optional[str] = None,
) -> str:
    """Record a fabricated founder evidence violation.

    This is classified as event_type='system_integrity_alert' and
    triggers an immediate reject — NOT escalation.
    """
    return log_reasoning_event(
        run_id=run_id,
        phase=phase,
        event_type="system_integrity_alert",
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
    """Record a founder override event (AI average prevention)."""
    return log_reasoning_event(
        run_id=run_id,
        phase=phase,
        event_type="founder_override",
        artifact="founder_kernel",
        details={"reason": reason, **(override_details or {})},
        parent_event_id=parent_event_id,
    )
