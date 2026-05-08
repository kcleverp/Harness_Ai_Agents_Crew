"""
telemetry_projection.py — Batch projections from the canonical telemetry stream.

Architecture:
  canonical stream (reasoning_trace.jsonl)
    └── projections/  (semantic slices — regenerable, non-canonical)
          ├── runtime.log      domain=workflow
          ├── decisions.log    domain=decision
          └── qa.log           domain=qa | domain=system (kernel/integrity)
    └── views/        (human-readable rendering — regenerable, non-canonical)
          ├── pretty.log       human-readable multiline export
          └── lineage_index.md chronological lineage table

Regeneration policy:
  - Projections are disposable. Delete and regenerate at any time.
  - Canonical stream is the single source of truth and is never touched.
  - Regeneration is deterministic: same canonical input → same output.
  - Triggers: manual, post-run batch, post schema/taxonomy change.

Usage:
  from harness.telemetry_projection import generate_all_projections
  generate_all_projections()                        # full stream
  generate_all_projections(run_id="abc123")         # single run slice
"""

from __future__ import annotations

import json
import os
from typing import Optional

_LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
_PROJ_DIR = os.path.join(_LOG_DIR, "projections")
_VIEW_DIR = os.path.join(_LOG_DIR, "views")
_CANONICAL = os.path.join(_LOG_DIR, "reasoning_trace.jsonl")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    os.makedirs(_PROJ_DIR, exist_ok=True)
    os.makedirs(_VIEW_DIR, exist_ok=True)


def _load_events(run_id: Optional[str] = None) -> list[dict]:
    """Load events from canonical stream. Skips malformed lines silently."""
    if not os.path.exists(_CANONICAL):
        return []
    events: list[dict] = []
    with open(_CANONICAL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run_id is None or ev.get("run_id") == run_id:
                events.append(ev)
    return events


def _fmt_event(ev: dict) -> str:
    """Single-line summary for projection text output."""
    ts = ev.get("timestamp", "?")
    run = ev.get("run_id", "?")[:8]
    phase = ev.get("phase", "?")
    domain = ev.get("domain", "?")
    category = ev.get("category", "?")
    event_type = ev.get("event_type", "?")
    artifact = ev.get("artifact") or ""
    artifact_part = f" artifact={artifact}" if artifact else ""
    return f"[{ts}] run={run} phase={phase} {domain}/{category}/{event_type}{artifact_part}"


def _write_projection(path: str, header: str, events: list[dict]) -> int:
    """Write events to a projection file. Returns event count written."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {header}\n")
        f.write(f"# Generated from canonical stream. Non-canonical — regenerable.\n")
        f.write(f"# event_count={len(events)}\n\n")
        for ev in events:
            f.write(_fmt_event(ev) + "\n")
    return len(events)


# ---------------------------------------------------------------------------
# F3 — Semantic projections (runtime / decisions / qa)
# ---------------------------------------------------------------------------

def generate_runtime_projection(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """Projection: domain=workflow events (run lifecycle, phase boundaries).

    Filters by domain directly — does not infer meaning from phase names.
    Returns number of events written.
    """
    _ensure_dirs()
    events = [ev for ev in _load_events(run_id) if ev.get("domain") == "workflow"]
    path = output_path or os.path.join(_PROJ_DIR, "runtime.log")
    return _write_projection(path, "Runtime Projection  [domain=workflow]", events)


def generate_decisions_projection(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """Projection: domain=decision events (selections, rejections, tradeoffs, council).

    Filters by domain directly — does not infer meaning from phase names.
    Returns number of events written.
    """
    _ensure_dirs()
    events = [ev for ev in _load_events(run_id) if ev.get("domain") == "decision"]
    path = output_path or os.path.join(_PROJ_DIR, "decisions.log")
    return _write_projection(path, "Decisions Projection  [domain=decision]", events)


def generate_qa_projection(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """Projection: domain=qa and domain=system events (validation, patching, integrity, kernel).

    system/kernel events are included because integrity violations are trust-boundary
    breaches, not routine workflow lifecycle events.
    Returns number of events written.
    """
    _ensure_dirs()
    events = [
        ev for ev in _load_events(run_id)
        if ev.get("domain") in ("qa", "system")
    ]
    path = output_path or os.path.join(_PROJ_DIR, "qa.log")
    return _write_projection(path, "QA Projection  [domain=qa | domain=system]", events)


# ---------------------------------------------------------------------------
# F4 — Views (lineage_index + pretty)
# ---------------------------------------------------------------------------

def generate_lineage_index(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """View: chronological Markdown table of all events in the canonical stream.

    Columns (chronological order, earliest first):
      timestamp | run_id (short) | phase | domain/category | event_type | artifact | parent_event_id (short)

    This is a view (rendering), not a semantic projection.
    Returns number of rows written.
    """
    _ensure_dirs()
    events = _load_events(run_id)
    events_sorted = sorted(events, key=lambda e: e.get("timestamp", ""))

    path = output_path or os.path.join(_VIEW_DIR, "lineage_index.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Lineage Index\n\n")
        f.write("> Generated from canonical stream. Non-canonical — regenerable.\n")
        f.write(f"> event_count={len(events_sorted)}\n\n")
        f.write("| timestamp | run_id | phase | domain/category | event_type | artifact | parent |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for ev in events_sorted:
            ts       = ev.get("timestamp", "")
            run      = (ev.get("run_id") or "")[:8]
            phase    = ev.get("phase", "")
            dom_cat  = f"{ev.get('domain','?')}/{ev.get('category','?')}"
            et       = ev.get("event_type", "")
            artifact = ev.get("artifact") or ""
            parent   = (ev.get("parent_event_id") or "")[:8]
            f.write(f"| {ts} | {run} | {phase} | {dom_cat} | {et} | {artifact} | {parent} |\n")

    return len(events_sorted)


def generate_pretty_view(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """View: human-readable multiline export of canonical stream.

    Format per event:
        RUN=<run_id[:8]>  PHASE=<phase>
        [<domain>/<category>/<event_type>]  artifact=<artifact>  ts=<timestamp>
        parent=<parent_event_id[:8] or ->
        details: <key=value ...>
        ---

    Canonical compact JSONL is preserved; this view is for operator readability only.
    Returns number of events written.
    """
    _ensure_dirs()
    events = _load_events(run_id)
    events_sorted = sorted(events, key=lambda e: e.get("timestamp", ""))

    path = output_path or os.path.join(_VIEW_DIR, "pretty.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Pretty View — canonical stream export\n")
        f.write(f"# Non-canonical. Regenerable. event_count={len(events_sorted)}\n\n")
        for ev in events_sorted:
            run      = (ev.get("run_id") or "")[:8]
            phase    = ev.get("phase", "?")
            domain   = ev.get("domain", "?")
            category = ev.get("category", "?")
            et       = ev.get("event_type", "?")
            ts       = ev.get("timestamp", "?")
            artifact = ev.get("artifact") or "-"
            parent   = (ev.get("parent_event_id") or "-")
            if parent != "-":
                parent = parent[:8]
            details  = ev.get("details") or {}

            f.write(f"RUN={run}  PHASE={phase}\n")
            f.write(f"[{domain}/{category}/{et}]  artifact={artifact}  ts={ts}\n")
            f.write(f"parent={parent}\n")
            if details:
                detail_str = "  ".join(f"{k}={v}" for k, v in details.items() if v is not None)
                f.write(f"details: {detail_str}\n")
            f.write("---\n")

    return len(events_sorted)


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def generate_all_projections(run_id: Optional[str] = None) -> dict[str, int]:
    """Generate all projections and views from the canonical stream.

    Args:
        run_id: If set, slices only events from that run.
                If None, processes the full stream.

    Returns:
        dict of name → event_count written.
          projections: runtime, decisions, qa
          views:       lineage_index, pretty
    """
    return {
        "runtime":       generate_runtime_projection(run_id),
        "decisions":     generate_decisions_projection(run_id),
        "qa":            generate_qa_projection(run_id),
        "lineage_index": generate_lineage_index(run_id),
        "pretty":        generate_pretty_view(run_id),
    }
