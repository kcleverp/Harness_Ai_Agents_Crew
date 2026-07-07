"""
cognitive_logger.py — Persist thinking traces and decision graphs.

- thinking_trace.jsonl: append-only free-form CoT (B layer)
- current/cognition/*.json: per-phase decision_graph snapshots (file fallback for Neo4j)
"""
import datetime
import json
import os
import uuid

from harness.audit_hooks import log_reasoning_event
from harness.cognitive_parser import truncate_thinking
from harness.paths import COGNITION_DIR, THINKING_TRACE


def _ensure_dirs():
    os.makedirs(os.path.dirname(THINKING_TRACE), exist_ok=True)
    os.makedirs(COGNITION_DIR, exist_ok=True)


def log_thinking(
    run_id: str,
    phase: str,
    thinking_text: str,
    artifact: str | None = None,
) -> None:
    if not thinking_text:
        return
    _ensure_dirs()
    record = {
        "run_id": run_id,
        "phase": phase,
        "artifact": artifact,
        "thinking": truncate_thinking(thinking_text),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(THINKING_TRACE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_decision_graph_snapshot(run_id: str, phase: str, graph: dict) -> str:
    """Write decision_graph to current/cognition/; return relative path."""
    if not graph:
        return ""
    _ensure_dirs()
    fname = f"{phase.lower()}_{run_id[:8]}_{uuid.uuid4().hex[:6]}.json"
    rel = f"current/cognition/{fname}"
    abs_path = os.path.join(COGNITION_DIR, fname)
    payload = {"run_id": run_id, "phase": phase, "decision_graph": graph}
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return rel


def log_decision_graph_event(
    run_id: str,
    phase: str,
    graph: dict,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit canonical event + file snapshot; return event_id."""
    if not graph:
        return None
    snapshot = save_decision_graph_snapshot(run_id, phase, graph)
    rejected = graph.get("rejected", [])
    selected = graph.get("selected", [])
    tradeoffs = graph.get("tradeoffs", [])
    return log_reasoning_event(
        run_id=run_id,
        phase=phase,
        event_type="decision_graph_recorded",
        domain="decision",
        category="tradeoff",
        artifact=snapshot or None,
        details={
            "selected_count": len(selected) if isinstance(selected, list) else 0,
            "rejected_count": len(rejected) if isinstance(rejected, list) else 0,
            "tradeoff_count": len(tradeoffs) if isinstance(tradeoffs, list) else 0,
            "decision_graph": graph,
        },
        parent_event_id=parent_event_id,
    )


def record_cognitive_output(
    run_id: str,
    phase: str,
    thinking_text: str,
    decision_graph: dict,
    artifact: str | None = None,
    parent_event_id: str | None = None,
) -> str | None:
    """Log thinking + decision graph; return graph event_id."""
    log_thinking(run_id, phase, thinking_text, artifact=artifact)
    graph_event_id = log_decision_graph_event(
        run_id, phase, decision_graph, parent_event_id=parent_event_id,
    )
    if thinking_text:
        log_reasoning_event(
            run_id=run_id,
            phase=phase,
            event_type="thinking_recorded",
            domain="decision",
            category="selection",
            artifact=artifact,
            details={"thinking": truncate_thinking(thinking_text)},
            parent_event_id=parent_event_id,
        )
    return graph_event_id
