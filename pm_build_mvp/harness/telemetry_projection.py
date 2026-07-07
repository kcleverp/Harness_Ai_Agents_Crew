"""
telemetry_projection.py — Batch projections from the canonical telemetry stream.

═══════════════════════════════════════════════════════════════
 ARCHITECTURE
═══════════════════════════════════════════════════════════════

  canonical stream (reasoning_trace.jsonl)          ← IMMUTABLE
    ├── projections/  [semantic slices]              ← disposable, regenerable
    │     ├── runtime.log      domain=workflow
    │     ├── decisions.log    domain=decision
    │     └── qa.log           domain=qa | domain=system
    └── views/        [human-readable rendering]     ← disposable, regenerable
          ├── pretty.log       multiline human export
          └── lineage_index.md chronological table

Layer definitions:
  Canonical   — append-only source of truth. Never rewritten or deleted.
  Projections — semantic slices filtered by domain/category/event_type.
                Meaning is read from the event itself, never inferred from phase.
  Views       — rendering artifacts for operator readability. Not queryable.

═══════════════════════════════════════════════════════════════
 PROJECTION REGENERATION POLICY  (v1)
═══════════════════════════════════════════════════════════════

  1. DISPOSABILITY
     Projections and views are disposable artifacts.
     They may be deleted and regenerated from the canonical stream at any time
     without loss of information.

  2. IMMUTABILITY OF SOURCE
     The canonical stream (reasoning_trace.jsonl) is append-only and immutable.
     No projection operation may modify, truncate, or rewrite this file.

  3. DETERMINISM
     Regeneration MUST be deterministic:
       same canonical input + same projection version → hash-equivalent output.
     Sort key: (timestamp, event_id) — stable regardless of insertion order.

  4. SEMANTIC ISOLATION
     Projections filter events by domain/category/event_type directly.
     They MUST NOT infer event meaning from phase names or log file origins.

  5. REGENERATION TRIGGERS
     a. Manual     — operator calls generate_all_projections() at any time.
     b. Post-run   — called automatically at end of run_planning() execution.
     c. Schema change — after taxonomy/schema_version update, regenerate full stream.

  6. VERSION BOUNDARY
     If projection logic changes (new filter, new format), regenerate all projections
     from the full canonical stream before deploying the new version.
     Old projection files from a prior version are not forward-compatible.

  7. SCOPE
     Current scope: batch/post-processing only.
     Real-time streaming projection is out of scope for this version.

═══════════════════════════════════════════════════════════════
 USAGE
═══════════════════════════════════════════════════════════════

  from harness.telemetry_projection import generate_all_projections

  generate_all_projections()                  # full stream
  generate_all_projections(run_id="abc123")   # single run slice
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import warnings
from typing import Optional

from harness.telemetry_schema import is_valid_event

from harness.paths import LOG_DIR as _LOG_DIR, PROJ_DIR as _PROJ_DIR, VIEW_DIR as _VIEW_DIR, CANONICAL_TRACE as _CANONICAL

# Increment when projection format or filter logic changes so operators can
# trace hash differences back to a code version rather than data changes.
PROJECTION_VERSION = "1.0"


def _canonical_file_hash() -> str:
    """SHA-256 of the raw canonical stream bytes. Returns 'none' if file absent."""
    if not os.path.exists(_CANONICAL):
        return "none"
    h = hashlib.sha256()
    with open(_CANONICAL, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    os.makedirs(_PROJ_DIR, exist_ok=True)
    os.makedirs(_VIEW_DIR, exist_ok=True)


def _load_events(run_id: Optional[str] = None) -> list[dict]:
    """Load events from canonical stream. Skips and warns on malformed lines."""
    if not os.path.exists(_CANONICAL):
        return []
    events: list[dict] = []
    with open(_CANONICAL, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.warn(
                    f"reasoning_trace.jsonl line {lineno}: malformed JSON skipped — {exc}",
                    stacklevel=2,
                )
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
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")
    canonical_hash = _canonical_file_hash()
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"# projection_version={PROJECTION_VERSION}"
            f" generated_at={generated_at}"
            f" source_canonical_hash={canonical_hash}\n"
        )
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


_COGNITION_EVENT_TYPES = frozenset({
    "thinking_recorded", "decision_graph_recorded",
})


def generate_cognition_projection(
    run_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> int:
    """Projection: cognitive memory events (thinking + decision_graph).

    Filters by event_type directly — disposable debug slice of canonical stream.
    Returns number of events written.
    """
    _ensure_dirs()
    events = [
        ev for ev in _load_events(run_id)
        if ev.get("event_type") in _COGNITION_EVENT_TYPES
    ]
    path = output_path or os.path.join(_PROJ_DIR, "cognition.log")
    return _write_projection(path, "Cognition Projection  [thinking | decision_graph]", events)


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
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")
    canonical_hash = _canonical_file_hash()
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"<!-- projection_version={PROJECTION_VERSION}"
            f" generated_at={generated_at}"
            f" source_canonical_hash={canonical_hash} -->\n\n"
        )
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
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")
    canonical_hash = _canonical_file_hash()
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"# projection_version={PROJECTION_VERSION}"
            f" generated_at={generated_at}"
            f" source_canonical_hash={canonical_hash}\n"
        )
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
          projections: runtime, decisions, qa, cognition
          views:       lineage_index, pretty
    """
    return {
        "runtime":       generate_runtime_projection(run_id),
        "decisions":     generate_decisions_projection(run_id),
        "qa":            generate_qa_projection(run_id),
        "cognition":     generate_cognition_projection(run_id),
        "lineage_index": generate_lineage_index(run_id),
        "pretty":        generate_pretty_view(run_id),
    }
