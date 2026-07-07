"""
intent_review.py — Layer 0.5 Founder Intent Review Gate.

Runs BEFORE the build pipeline. A strong model critiques the founder kernel
(user → problem → opportunity → coherence) and the founder then decides:
proceed / reject / edit kernel & proceed.

Verdict modes (env PM_VERDICT_MODE):
  api           write review json, then poll for founder_choice.json written
                by POST /runs/{id}/intent-choice (FastAPI server). Timeout
                (PM_INTENT_REVIEW_TIMEOUT_SEC, default 600s) counts as reject.
                (default)
  interactive   stdin prompt when a TTY is attached; otherwise falls back
                to auto_proceed (non-interactive batch runs must not hang).
  auto_proceed  record the review, proceed without waiting.

Skip condition: OPENROUTER_MODEL_INTENT_REVIEW unset → gate is skipped
entirely (warn-only optional role, consistent with other v4 phases).

File handshake (no harness→server import; file-centric like the rest):
  current/kernel/founder_intent_review.json   gate output (review + kernel)
  current/kernel/founder_choice.json          founder decision (server/CLI writes)
"""
import json
import os
import sys
import time

from harness.audit_hooks import log_pm_audit, log_pm_audit_event, log_reasoning_event
from harness.cognitive_logger import record_cognitive_output
from harness.cognitive_utils import append_cognitive_contract, cognitive_enabled
from harness.kernel_guard import save_founder_kernel
from harness.llm_factory import build_intent_review_llm
from harness.paths import CURRENT_DIR
from harness.prompt_loader import load_prompt
from harness.batch_translator import ensure_intent_review_korean, load_intent_review_ko
from harness.confidence_scoring import normalize_intent_confidence
from harness.cognitive_validate import call_with_cognitive_retry
from harness.safe_file_tools import write_workspace_file

REVIEW_REL_PATH = "current/kernel/founder_intent_review.json"
CHOICE_REL_PATH = "current/kernel/founder_choice.json"
_REVIEW_ABS = os.path.join(CURRENT_DIR, "kernel", "founder_intent_review.json")
_CHOICE_ABS = os.path.join(CURRENT_DIR, "kernel", "founder_choice.json")

_VALID_CHOICES = ("proceed", "reject", "edit")
_KERNEL_CONTENT_KEYS = ("core_thesis", "non_negotiables", "anti_patterns", "founder_convictions")


def _structural_audit(kernel_data: dict) -> list[dict]:
    """Code-side checks that don't need a model."""
    warnings = []
    for key in _KERNEL_CONTENT_KEYS:
        items = kernel_data.get(key, [])
        if not items:
            warnings.append({
                "area": "structure", "severity": "high",
                "issue": f"kernel.{key} is empty — the guard has nothing to protect",
                "kernel_ref": key,
            })
    total_items = sum(len(kernel_data.get(k, [])) for k in _KERNEL_CONTENT_KEYS)
    if 0 < total_items < 3:
        warnings.append({
            "area": "structure", "severity": "medium",
            "issue": f"kernel has only {total_items} item(s) total — too thin for a meaningful review",
            "kernel_ref": "kernel",
        })
    return warnings


def _parse_review(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "verdict": "proceed_with_concerns",
        "problems": [],
        "parse_failed": True,
        "raw_response": raw[:2000],
    }


def _wait_for_choice_file(timeout_sec: int) -> dict:
    """Poll for founder_choice.json (api mode). Timeout → reject."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if os.path.exists(_CHOICE_ABS):
            try:
                with open(_CHOICE_ABS, "r", encoding="utf-8") as f:
                    choice = json.load(f)
                if choice.get("choice") in _VALID_CHOICES:
                    return choice
            except (json.JSONDecodeError, OSError):
                pass  # partially written — retry next tick
        time.sleep(1.0)
    return {"choice": "reject", "reason": f"intent review timed out after {timeout_sec}s"}


def _interactive_choice() -> dict:
    print("\n=== Founder Intent Review Gate ===")
    print(f"Review saved to {REVIEW_REL_PATH}")
    while True:
        answer = input("Choice [proceed/reject]: ").strip().lower()
        if answer in ("proceed", "reject"):
            return {"choice": answer, "reason": "interactive CLI choice"}
        print("Please type 'proceed' or 'reject'.")


def run_intent_review(kernel_data: dict, run_id: str = "") -> dict:
    """Layer 0.5 gate. Returns:

    {"choice": "proceed"|"reject", "kernel_data": dict, "skipped": bool,
     "verdict": str, "review": dict}

    'edit' choices are resolved internally: the new kernel is saved and the
    returned choice is "proceed" with the updated kernel_data.
    """
    if not os.getenv("OPENROUTER_MODEL_INTENT_REVIEW", "").strip():
        log_pm_audit("IntentReview | Status=SKIPPED | Reason=OPENROUTER_MODEL_INTENT_REVIEW not configured")
        return {"choice": "proceed", "kernel_data": kernel_data, "skipped": True,
                "verdict": "skipped", "review": {}}

    mode = os.getenv("PM_VERDICT_MODE", "api").strip().lower()
    if mode not in ("api", "interactive", "auto_proceed"):
        mode = "api"
    if mode == "interactive" and not sys.stdin.isatty():
        log_pm_audit("IntentReview | Mode=interactive but no TTY — falling back to auto_proceed")
        mode = "auto_proceed"

    log_pm_audit_event(
        "IntentReview", "START",
        model=os.getenv("OPENROUTER_MODEL_INTENT_REVIEW"),
        run_id=run_id,
    )

    # Clear stale handshake files from previous runs BEFORE writing the new
    # review, so the server's awaiting_choice detection has no false window.
    for stale in (_CHOICE_ABS, _REVIEW_ABS):
        if os.path.exists(stale):
            os.remove(stale)

    structural_warnings = _structural_audit(kernel_data)

    kernel_payload = {k: kernel_data.get(k, []) for k in _KERNEL_CONTENT_KEYS}
    llm = build_intent_review_llm()
    system = append_cognitive_contract(load_prompt("founder_intent_review"))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            "Review this founder kernel:\n\n"
            f"{json.dumps(kernel_payload, indent=2, ensure_ascii=False)}"
        )},
    ]
    if cognitive_enabled():
        raw, cognitive = call_with_cognitive_retry(llm, messages, "IntentReview")
        record_cognitive_output(
            run_id, "IntentReview", cognitive.thinking_text, cognitive.decision_graph,
            artifact=REVIEW_REL_PATH,
        )
        review = _parse_review(cognitive.artifact_body)
    else:
        raw = llm.call(messages)
        review = _parse_review(raw)
    review["structural_warnings"] = structural_warnings
    review["confidence"] = normalize_intent_confidence(review)
    verdict = review.get("verdict", "proceed_with_concerns")

    review_doc = {
        "run_id": run_id,
        "mode": mode,
        "kernel": kernel_payload,
        "review": review,
    }
    # Translate before writing review json so awaiting_choice does not open
    # the gate UI (and trigger a second on-demand translation) mid-flight.
    ensure_intent_review_korean(review_doc, run_id=run_id)
    write_workspace_file(REVIEW_REL_PATH, json.dumps(review_doc, indent=2, ensure_ascii=False))
    ko_doc = load_intent_review_ko()
    summary_ko = (ko_doc.get("review_ko") or {}).get("ko_summary") if ko_doc else None

    review_event_id = log_reasoning_event(
        run_id=run_id, phase="IntentReview",
        event_type="intent_review_completed",
        domain="decision", category="selection",
        artifact=REVIEW_REL_PATH,
        details={
            "verdict": verdict,
            "confidence": review.get("confidence"),
            "problem_count": len(review.get("problems", [])),
            "high_severity": sum(1 for p in review.get("problems", []) if p.get("severity") == "high"),
            "structural_warnings": len(structural_warnings),
            "summary_ko": summary_ko,
        },
    )

    # --- Founder decision -------------------------------------------------
    if mode == "api":
        timeout_sec = int(os.getenv("PM_INTENT_REVIEW_TIMEOUT_SEC", "600"))
        choice_doc = _wait_for_choice_file(timeout_sec)
    elif mode == "interactive":
        choice_doc = _interactive_choice()
    else:
        choice_doc = {"choice": "proceed", "reason": "auto_proceed mode"}

    choice = choice_doc.get("choice", "reject")

    # 'edit' → apply new kernel content, then proceed with it.
    if choice == "edit":
        new_kernel_fields = choice_doc.get("kernel") or {}
        for key in _KERNEL_CONTENT_KEYS:
            if key in new_kernel_fields and isinstance(new_kernel_fields[key], list):
                kernel_data[key] = new_kernel_fields[key]
        save_founder_kernel(kernel_data)
        log_pm_audit("IntentReview | Status=KERNEL_EDITED | founder edited kernel at gate")
        choice = "proceed"

    log_reasoning_event(
        run_id=run_id, phase="IntentReview",
        event_type="intent_choice",
        domain="decision", category="selection",
        artifact=CHOICE_REL_PATH if mode == "api" else None,
        details={
            "choice": choice,
            "original_choice": choice_doc.get("choice"),
            "reason": choice_doc.get("reason"),
            "mode": mode,
            "verdict": verdict,
        },
        parent_event_id=review_event_id,
    )
    log_pm_audit_event(
        "IntentReview", "END",
        selected=choice,
        risk=verdict,
        output=REVIEW_REL_PATH,
        summary_ko=summary_ko,
        run_id=run_id,
    )

    return {"choice": choice, "kernel_data": kernel_data, "skipped": False,
            "verdict": verdict, "review": review}
