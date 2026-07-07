"""PM Reconstruction Layer — critique → persona / problem / opportunity."""
from __future__ import annotations

import json
import os

from harness.audit_hooks import log_pm_audit, log_pm_audit_event, log_reasoning_event
from harness.confidence_scoring import merge_confidence
from harness.llm_factory import build_pm_reconstruction_llm
from harness.paths import CURRENT_DIR
from harness.pm_brief import sync_legacy_upstream_files
from harness.prompt_loader import load_prompt
from harness.safe_file_tools import write_workspace_file

PM_BRIEF_REL = "current/discovery/pm_brief.json"
_SYSTEM = load_prompt("pm_reconstruction_system")


def reconstruction_enabled() -> bool:
    mode = os.getenv("PM_RECONSTRUCTION", "on").strip().lower()
    if mode in ("off", "0", "false", "skip"):
        return False
    model = (
        os.getenv("OPENROUTER_MODEL_PM_RECON", "").strip()
        or os.getenv("OPENROUTER_MODEL_USER_DEF", "").strip()
        or os.getenv("OPENROUTER_MODEL_STRATEGIC_QA", "").strip()
    )
    return bool(model)


def _parse_brief(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        doc = json.loads(cleaned)
        if isinstance(doc, dict):
            return doc
    except json.JSONDecodeError:
        pass
    return {}


def _compute_brief_confidence(brief: dict) -> float:
    base = 0.45
    persona = brief.get("persona") or {}
    if persona.get("name") and persona.get("job_to_be_done"):
        base += 0.20
    if persona.get("current_solution") and persona.get("success_metric"):
        base += 0.10
    if brief.get("problem_statement") and "because" in str(brief["problem_statement"]).lower():
        base += 0.15
    opp = brief.get("opportunity") or {}
    if opp.get("opportunity_score") is not None:
        base += 0.10
    return merge_confidence(base, brief.get("confidence"))


def run_pm_reconstruction(
    kernel_data: dict,
    run_id: str = "",
    intent_review: dict | None = None,
) -> dict:
    """Generate pm_brief.json and sync legacy upstream artifact paths."""
    if not reconstruction_enabled():
        log_pm_audit("PMReconstruction | Status=SKIPPED | Reason=PM_RECONSTRUCTION off or no model")
        return {"skipped": True}

    os.makedirs(os.path.join(CURRENT_DIR, "discovery"), exist_ok=True)
    log_pm_audit_event("PMReconstruction", "START", run_id=run_id, output=PM_BRIEF_REL)

    kernel_payload = {
        k: kernel_data.get(k, [])
        for k in ("core_thesis", "non_negotiables", "anti_patterns", "founder_convictions")
    }
    review = intent_review or {}
    problems = review.get("problems") or []

    context = (
        f"## Founder Kernel\n{json.dumps(kernel_payload, indent=2, ensure_ascii=False)}\n\n"
        f"## Intent Review\n"
        f"verdict: {review.get('verdict', 'unknown')}\n"
        f"confidence: {review.get('confidence')}\n\n"
        f"problems:\n{json.dumps(problems, indent=2, ensure_ascii=False)}\n\n"
        f"user_analysis: {review.get('user_analysis', '')}\n"
        f"problem_analysis: {review.get('problem_analysis', '')}\n"
        f"opportunity_analysis: {review.get('opportunity_analysis', '')}\n"
    )

    llm = build_pm_reconstruction_llm()
    raw = llm.call([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Reconstruct the PM brief:\n\n{context}"},
    ])
    brief = _parse_brief(raw)
    if not brief.get("persona"):
        log_pm_audit("PMReconstruction | Status=PARSE_WARN | persona missing — partial brief")
    brief["confidence"] = _compute_brief_confidence(brief)
    brief["run_id"] = run_id
    brief["source"] = "pm_reconstruction"

    write_workspace_file(PM_BRIEF_REL, json.dumps(brief, indent=2, ensure_ascii=False))
    sync_legacy_upstream_files(brief)

    log_reasoning_event(
        run_id=run_id,
        phase="PMReconstruction",
        event_type="pm_reconstruction_completed",
        domain="discovery",
        category="opportunity",
        artifact=PM_BRIEF_REL,
        details={
            "persona_name": (brief.get("persona") or {}).get("name"),
            "opportunity_score": (brief.get("opportunity") or {}).get("opportunity_score"),
            "recommended_direction": (brief.get("opportunity") or {}).get("recommended_direction"),
            "confidence": brief.get("confidence"),
            "ko_summary": brief.get("ko_summary"),
        },
    )
    log_pm_audit_event(
        "PMReconstruction", "END",
        output=PM_BRIEF_REL,
        summary_ko=brief.get("ko_summary"),
        run_id=run_id,
    )
    return brief
