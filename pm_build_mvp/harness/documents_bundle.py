"""Assemble Velog-style document bundle from run workspace artifacts."""
from __future__ import annotations

import json
import os


def _read_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _read_text(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _first_ko(*sources: dict | None) -> str | None:
    for src in sources:
        if not src:
            continue
        ko = src.get("ko_summary")
        if isinstance(ko, str) and ko.strip():
            return ko.strip()
    return None


def _strategic_ko_blocks(strategic: dict) -> list[dict]:
    blocks: list[dict] = []
    for key, label in (("founder_preservation", "Founder Preservation"), ("market_viability", "Market Viability")):
        block = strategic.get(key) or {}
        ko = block.get("ko_summary")
        if isinstance(ko, str) and ko.strip():
            blocks.append({"label": label, "text": ko.strip()})
    return blocks


def _section_has_ko(section: dict) -> bool:
    body = section.get("body")
    if isinstance(body, str) and body.strip():
        return True
    if not isinstance(body, dict):
        return False
    if isinstance(body.get("ko_summary"), str) and body["ko_summary"].strip():
        return True
    summaries = body.get("ko_summaries")
    return isinstance(summaries, list) and len(summaries) > 0


def build_documents_bundle(run_root: str, run_id: str) -> dict:
    checkpoint = _read_json(os.path.join(run_root, "docs", "concept_checkpoint.json")) or {}
    council = _read_json(os.path.join(run_root, "decision", "council_decision.json")) or {}
    backlog = _read_json(os.path.join(run_root, "tech", "backlog.json")) or {}
    validation = _read_json(os.path.join(run_root, "validation", "validation_strategy.json")) or {}
    idea_meta = _read_json(os.path.join(run_root, "docs", "idea_meta.json")) or {}
    strategic = _read_json(os.path.join(run_root, "qa", "strategic_qa_result.json")) or {}
    product_qa = _read_json(os.path.join(run_root, "qa", "product_qa_result.json")) or {}

    summary_md = (
        _read_text(os.path.join(run_root, "docs", "founder_summary_ko.md"))
        or _read_text(os.path.join(run_root, "docs", "founder_summary.md"))
        or ""
    )

    title = checkpoint.get("recommended_direction") or council.get("ko_summary") or "MVP Planning Brief"
    if isinstance(title, str) and len(title) > 80:
        title = title[:77] + "…"

    tasks = backlog.get("tasks") or []
    task_preview = [
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "owner": t.get("owner"),
            "priority": t.get("priority"),
        }
        for t in tasks[:8]
        if isinstance(t, dict)
    ]

    failed_strategic = [
        c for checks in (
            (strategic.get("founder_preservation") or {}).get("checks") or [],
            (strategic.get("market_viability") or {}).get("checks") or [],
        )
        for c in checks
        if isinstance(c, dict) and (not c.get("passed", True) or c.get("severity") in ("warn", "high"))
    ]

    sections = []

    pm_brief = _read_json(os.path.join(run_root, "discovery", "pm_brief.json"))
    user_model = _read_json(os.path.join(run_root, "user", "user_model.json"))
    problem_doc = _read_json(os.path.join(run_root, "opportunity", "problem_statement.json"))
    opp_doc = _read_json(os.path.join(run_root, "opportunity", "opportunity_model.json"))

    persona_body = (pm_brief or {}).get("persona") or (user_model or {}).get("persona")
    if persona_body:
        sections.append({
            "id": "persona",
            "title": "Persona",
            "kind": "persona",
            "body": {
                **persona_body,
                "ko_summary": (pm_brief or user_model or {}).get("ko_summary"),
                "confidence": (pm_brief or user_model or {}).get("confidence"),
            },
        })

    problem_body = pm_brief if pm_brief and pm_brief.get("problem_statement") else problem_doc
    if problem_body and (problem_body.get("problem_statement") or problem_body.get("pain_points")):
        sections.append({
            "id": "problem",
            "title": "Problem Discovery",
            "kind": "problem",
            "body": {
                "problem_statement": problem_body.get("problem_statement"),
                "pain_points": problem_body.get("pain_points") or [],
                "friction": problem_body.get("friction") or [],
                "ko_summary": problem_body.get("ko_summary"),
                "confidence": problem_body.get("confidence"),
            },
        })

    opp_body = (pm_brief or {}).get("opportunity") if pm_brief else opp_doc
    if opp_body and any(opp_body.get(k) for k in ("opportunity_score", "market_size", "recommended_direction")):
        opp_payload = dict(opp_body)
        if not _first_ko(opp_payload):
            ko = _first_ko(pm_brief, opp_doc)
            if ko:
                opp_payload["ko_summary"] = ko
        sections.append({
            "id": "opportunity",
            "title": "Opportunity Sizing",
            "kind": "opportunity",
            "body": opp_payload,
        })

    if summary_md.strip():
        sections.append({"id": "summary", "title": "Executive Summary", "kind": "markdown", "body": summary_md})

    if checkpoint:
        checkpoint_payload = dict(checkpoint)
        ko = _first_ko(checkpoint, pm_brief, idea_meta, council)
        if ko and not _first_ko(checkpoint_payload):
            checkpoint_payload["ko_summary"] = ko
        sections.append({"id": "concept", "title": "Concept Checkpoint", "kind": "checkpoint", "body": checkpoint_payload})

    if idea_meta:
        sections.append({"id": "idea", "title": "Idea Loop", "kind": "idea", "body": idea_meta})

    council_conf = (council.get("confidence") or {}).get("final_confidence")
    if council:
        sections.append({
            "id": "council",
            "title": "MVP Council Verdict",
            "kind": "council",
            "body": {**council, "final_confidence": council_conf},
        })

    if task_preview:
        sections.append({
            "id": "backlog",
            "title": "Dev Backlog",
            "kind": "backlog",
            "body": {"tasks": task_preview, "total": len(tasks)},
        })

    if product_qa:
        sections.append({"id": "product-qa", "title": "Product QA", "kind": "qa", "body": product_qa})

    if strategic:
        ko_blocks = _strategic_ko_blocks(strategic)
        sections.append({
            "id": "strategic-qa",
            "title": "Strategic QA",
            "kind": "strategic_qa",
            "body": {
                **strategic,
                "highlights": failed_strategic,
                "ko_summaries": ko_blocks,
                "ko_summary": " ".join(b["text"] for b in ko_blocks) if ko_blocks else None,
            },
        })

    if validation and (validation.get("core_hypothesis") or validation.get("next_experiments")):
        sections.append({"id": "validation", "title": "Validation Strategy", "kind": "validation", "body": validation})

    with_ko = sum(1 for s in sections if _section_has_ko(s))
    if with_ko == 0:
        translation_status = "pending"
    elif with_ko >= len(sections):
        translation_status = "ok"
    else:
        translation_status = "partial"

    return {
        "run_id": run_id,
        "title": title,
        "subtitle": checkpoint.get("target_user") or "",
        "verdict": council.get("verdict"),
        "confidence": council_conf,
        "sections": sections,
        "translation_status": translation_status,
        "ko_summary": _first_ko(pm_brief, council, idea_meta, validation),
    }
