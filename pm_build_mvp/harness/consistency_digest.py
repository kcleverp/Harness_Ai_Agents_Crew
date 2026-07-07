"""Compact cross-document digest for Consistency Guardrail (token savings)."""
from __future__ import annotations

import json


def _heading_outline(md: str, max_headings: int = 12) -> str:
    lines = []
    for line in md.splitlines():
        if line.startswith("#"):
            lines.append(line.strip())
        if len(lines) >= max_headings:
            break
    return "\n".join(lines) if lines else md[:800]


def _backlog_digest(raw: str) -> str:
    if raw.startswith("Error:"):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000]
    tasks = data.get("tasks") or []
    lines = [f"tasks: {len(tasks)}"]
    for t in tasks[:20]:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        title = (t.get("title") or "")[:80]
        pri = t.get("priority", "?")
        ac = t.get("acceptance_criteria") or []
        ac_preview = ac[0][:60] if ac else ""
        lines.append(f"- {tid} | {pri} | {title} | AC: {ac_preview}")
    if len(tasks) > 20:
        lines.append(f"... +{len(tasks) - 20} more tasks")
    return "\n".join(lines)


def _validation_digest(raw: str) -> str:
    if raw.startswith("Error:"):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:1500]
    lines = []
    for hyp in (data.get("core_hypothesis") or [])[:8]:
        if isinstance(hyp, dict):
            lines.append(
                f"- {hyp.get('id', '?')}: {hyp.get('statement', '')[:100]} "
                f"| KPI: {hyp.get('kpi', '')[:60]}"
            )
    for fm in (data.get("failure_modes") or [])[:5]:
        if isinstance(fm, dict):
            lines.append(f"- fail: {(fm.get('mode') or fm.get('name') or '')[:80]}")
        elif isinstance(fm, str):
            lines.append(f"- fail: {fm[:80]}")
    return "\n".join(lines) if lines else json.dumps(data, ensure_ascii=False)[:1500]


def build_consistency_digest(
    feature_spec: str,
    backlog_raw: str,
    validation_raw: str,
    founder_summary: str,
    kernel_data: dict | None = None,
) -> str:
    """Structured summary for alignment checks — not full document bodies."""
    parts = []
    if kernel_data:
        payload = {k: v for k, v in kernel_data.items() if k != "kernel_hash"}
        parts.append(f"## Founder Kernel (compact)\n{json.dumps(payload, ensure_ascii=False)[:1200]}")

    parts.append(f"## Feature Spec (outline)\n{_heading_outline(feature_spec)}")
    parts.append(f"## Backlog (task digest)\n{_backlog_digest(backlog_raw)}")
    parts.append(f"## Validation (hypothesis digest)\n{_validation_digest(validation_raw)}")
    summary_lines = founder_summary.splitlines()[:25]
    parts.append(f"## Founder Summary (excerpt)\n" + "\n".join(summary_lines))
    return "\n\n".join(parts)
