"""Aggregate decision_graph data from cognition snapshots and canonical trace."""
from __future__ import annotations

import json
import os

from harness.paths import CANONICAL_TRACE, COGNITION_DIR

_DECISION_EVENT_TYPES = {
    "option_selected", "option_rejected", "tradeoff_recorded",
    "council_approved", "council_rejected", "decision_graph_recorded",
    "thinking_recorded", "intent_review_completed", "intent_choice",
}


def _load_cognition_snapshots(run_id: str, run_root: str | None) -> list[dict]:
    entries: list[dict] = []
    cognition_root = None
    if run_root:
        candidate = os.path.join(run_root, "cognition")
        if os.path.isdir(candidate):
            cognition_root = candidate
    if cognition_root is None and os.path.isdir(COGNITION_DIR):
        cognition_root = COGNITION_DIR
    if not cognition_root:
        return entries
    for fname in sorted(os.listdir(cognition_root)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(cognition_root, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if doc.get("run_id") and doc.get("run_id") != run_id:
            continue
        graph = doc.get("decision_graph", {})
        entries.append({
            "source": "cognition_snapshot",
            "phase": doc.get("phase", "?"),
            "artifact": f"cognition/{fname}",
            "decision_graph": graph,
        })
    return entries


def _load_trace_events(run_id: str) -> list[dict]:
    if not os.path.exists(CANONICAL_TRACE):
        return []
    events = []
    with open(CANONICAL_TRACE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("run_id") != run_id:
                continue
            if ev.get("event_type") not in _DECISION_EVENT_TYPES:
                continue
            events.append({
                "source": "reasoning_trace",
                "event_id": ev.get("event_id"),
                "phase": ev.get("phase"),
                "event_type": ev.get("event_type"),
                "timestamp": ev.get("timestamp"),
                "artifact": ev.get("artifact"),
                "details": ev.get("details") or {},
            })
    return events


def aggregate_decisions(run_id: str, run_root: str | None = None) -> dict:
    """Build selected/rejected/tradeoffs lists from cognition + trace."""
    snapshots = _load_cognition_snapshots(run_id, run_root)
    events = _load_trace_events(run_id)
    rejected: list[dict] = []
    selected: list[dict] = []
    tradeoffs: list[dict] = []

    def _extend_from_graph(graph: dict, phase: str | None) -> None:
        for item in graph.get("rejected") or []:
            if isinstance(item, dict):
                rejected.append({**item, "phase": phase})
        for item in graph.get("selected") or []:
            if isinstance(item, dict):
                selected.append({**item, "phase": phase})
        for item in graph.get("tradeoffs") or []:
            if isinstance(item, dict):
                tradeoffs.append({**item, "phase": phase})

    for snap in snapshots:
        _extend_from_graph(snap.get("decision_graph") or {}, snap.get("phase"))

    for ev in events:
        graph = (ev.get("details") or {}).get("decision_graph")
        if isinstance(graph, dict):
            _extend_from_graph(graph, ev.get("phase"))

    def _item_key(item: dict, kind: str) -> tuple:
        return (
            kind,
            item.get("phase"),
            item.get("id"),
            item.get("name"),
            item.get("rationale") or item.get("reason"),
            item.get("accepted"),
            item.get("sacrificed"),
        )

    def _dedupe(items: list[dict], kind: str) -> list[dict]:
        seen: set[tuple] = set()
        out: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = _item_key(item, kind)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return {
        "run_id": run_id,
        "snapshots": snapshots,
        "events": events,
        "rejected": _dedupe(rejected, "rejected"),
        "selected": _dedupe(selected, "selected"),
        "tradeoffs": _dedupe(tradeoffs, "tradeoffs"),
    }
