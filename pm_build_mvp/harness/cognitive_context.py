"""
cognitive_context.py — Inject recent rejected decisions into downstream prompts.

Token budget: last 5 rejected alternatives from cognition snapshots + canonical trace.
"""
import json
import os

from harness.paths import CANONICAL_TRACE, COGNITION_DIR

_REJECTED_LIMIT = 5


def _load_rejected_from_cognition() -> list[dict]:
    if not os.path.isdir(COGNITION_DIR):
        return []
    entries: list[tuple[str, dict]] = []
    for fname in os.listdir(COGNITION_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(COGNITION_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        graph = doc.get("decision_graph", {})
        for item in graph.get("rejected", []) or []:
            if isinstance(item, dict):
                entries.append((fname, item))
    entries.sort(key=lambda x: x[0], reverse=True)
    return [e[1] for e in entries[:_REJECTED_LIMIT]]


def _load_rejected_from_trace(run_id: str | None) -> list[dict]:
    if not run_id or not os.path.exists(CANONICAL_TRACE):
        return []
    rejected: list[dict] = []
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
            graph = (ev.get("details") or {}).get("decision_graph")
            if isinstance(graph, dict):
                for item in graph.get("rejected", []) or []:
                    if isinstance(item, dict):
                        rejected.append(item)
            elif ev.get("event_type") == "option_rejected":
                d = ev.get("details") or {}
                rejected.append({
                    "name": d.get("rejected"),
                    "reason": d.get("reason"),
                })
    return rejected[-_REJECTED_LIMIT:]


def build_cognitive_context(run_id: str | None = None) -> str:
    """Return markdown block of recent rejected alternatives for prompt injection."""
    items = _load_rejected_from_cognition()
    if not items:
        items = _load_rejected_from_trace(run_id)
    if not items:
        return ""
    lines = ["## Recent Rejected Alternatives (cognitive memory)", ""]
    for i, item in enumerate(items[:_REJECTED_LIMIT], 1):
        name = item.get("name") or item.get("id") or f"option-{i}"
        reason = item.get("reason") or item.get("rationale") or ""
        conflict = item.get("conflicts_with") or ""
        lines.append(f"{i}. **{name}** — {reason}")
        if conflict:
            lines.append(f"   - conflicts_with: {conflict}")
    return "\n".join(lines)
