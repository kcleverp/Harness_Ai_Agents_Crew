"""Batch Korean translation for intent review and decisions (display sidecars only)."""
from __future__ import annotations

import json
import os
import re
import threading

from harness.audit_hooks import log_pm_audit, log_reasoning_event
from harness.decisions_aggregate import aggregate_decisions
from harness.llm_factory import build_translator_llm_from_env
from harness.paths import CURRENT_DIR, LOG_DIR
from harness.prompt_loader import load_prompt
from harness.safe_file_tools import write_workspace_file

INTENT_REVIEW_KO_REL = "current/kernel/founder_intent_review_ko.json"
INTENT_REVIEW_KO_ABS = os.path.join(CURRENT_DIR, "kernel", "founder_intent_review_ko.json")
DECISIONS_KO_DIR = os.path.join(LOG_DIR, "decisions_ko")
_INTENT_KO_LOCK = threading.Lock()

_INTENT_TRANSLATABLE_KEYS = (
    "user_analysis", "problem_analysis", "opportunity_analysis",
    "coherence_analysis", "ko_summary",
)
_PROBLEM_TEXT_KEYS = ("issue",)


def _decisions_ko_abs(run_id: str) -> str:
    os.makedirs(DECISIONS_KO_DIR, exist_ok=True)
    return os.path.join(DECISIONS_KO_DIR, f"{run_id}.json")


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _call_json_translator(payload: dict, run_id: str = "", artifact: str = "") -> dict | None:
    persona = load_prompt("translator_json")
    llm = build_translator_llm_from_env()
    messages = [
        {"role": "system", "content": persona},
        {
            "role": "user",
            "content": (
                "Translate the string values in this JSON into Korean following all rules "
                "in your persona. Return the complete JSON object with identical structure.\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]
    try:
        raw = llm.call(messages)
    except Exception as exc:
        log_pm_audit(f"[batch_translator] LLM call failed: {exc}")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_failed",
                domain="translation", category="sync",
                artifact=artifact, details={"reason": "llm_call_failed", "error": str(exc)},
            )
        return None

    if not raw or not raw.strip():
        return None

    try:
        return json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        log_pm_audit(f"[batch_translator] JSON parse failed: {exc}")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_failed",
                domain="translation", category="sync",
                artifact=artifact, details={"reason": "json_parse_failed", "error": str(exc)},
            )
        return None


def _validate_same_structure(source: dict, translated: dict) -> list[str]:
    warnings: list[str] = []
    if set(source.keys()) != set(translated.keys()):
        warnings.append(f"top-level keys mismatch: {set(source.keys())} vs {set(translated.keys())}")
        return warnings

    for key, src_val in source.items():
        dst_val = translated.get(key)
        if isinstance(src_val, list) and isinstance(dst_val, list):
            if len(src_val) != len(dst_val):
                warnings.append(f"{key} array length EN={len(src_val)} KO={len(dst_val)}")
                continue
            for i, (src_item, dst_item) in enumerate(zip(src_val, dst_val)):
                if isinstance(src_item, dict) and isinstance(dst_item, dict):
                    src_id = src_item.get("id")
                    dst_id = dst_item.get("id")
                    if src_id is not None and src_id != dst_id:
                        warnings.append(f"{key}[{i}] id mismatch: {src_id} vs {dst_id}")
        elif type(src_val) is not type(dst_val):
            warnings.append(f"{key} type mismatch: {type(src_val).__name__} vs {type(dst_val).__name__}")
    return warnings


def _extract_intent_payload(review: dict) -> dict:
    payload: dict = {}
    for key in _INTENT_TRANSLATABLE_KEYS:
        val = review.get(key)
        if isinstance(val, str) and val.strip():
            payload[key] = val
    problems = []
    for p in review.get("problems") or []:
        if isinstance(p, dict) and isinstance(p.get("issue"), str) and p["issue"].strip():
            problems.append({"issue": p["issue"]})
    if problems:
        payload["problems"] = problems
    warnings = []
    for w in review.get("structural_warnings") or []:
        if isinstance(w, dict) and isinstance(w.get("issue"), str) and w["issue"].strip():
            warnings.append({"issue": w["issue"]})
    if warnings:
        payload["structural_warnings"] = warnings
    return payload


def _merge_intent_translation(review: dict, translated: dict) -> dict:
    merged = dict(review)
    for key in _INTENT_TRANSLATABLE_KEYS:
        if key in translated and isinstance(translated[key], str):
            merged[key] = translated[key]
    for src_list, dst_key in (
        (translated.get("problems"), "problems"),
        (translated.get("structural_warnings"), "structural_warnings"),
    ):
        if not isinstance(src_list, list):
            continue
        target = merged.get(dst_key) or []
        if not isinstance(target, list):
            continue
        for i, tr_item in enumerate(src_list):
            if i >= len(target) or not isinstance(tr_item, dict):
                continue
            if isinstance(tr_item.get("issue"), str):
                target[i] = {**target[i], "issue": tr_item["issue"]}
        merged[dst_key] = target
    return merged


def ensure_intent_review_korean(review_doc: dict, run_id: str = "") -> None:
    """Translate intent review text fields; write founder_intent_review_ko.json."""
    with _INTENT_KO_LOCK:
        try:
            rid = review_doc.get("run_id", run_id)
            if rid and not intent_review_ko_stale(rid):
                log_pm_audit("[batch_translator] SKIP: intent review KO is fresh")
                return

            review = review_doc.get("review") or {}
            payload = _extract_intent_payload(review)
            if not payload:
                log_pm_audit("[batch_translator] SKIP: intent review has no translatable fields")
                return

            translated = _call_json_translator(payload, run_id=run_id, artifact=INTENT_REVIEW_KO_REL)
            if translated is None:
                return

            warnings = _validate_same_structure(payload, translated)
            if warnings:
                for w in warnings:
                    log_pm_audit(f"[batch_translator] INTENT_STRUCTURE_MISMATCH: {w}")
                translated = _call_json_translator(payload, run_id=run_id, artifact=INTENT_REVIEW_KO_REL)
                if translated is None:
                    return
                warnings = _validate_same_structure(payload, translated)
                if warnings:
                    log_pm_audit("[batch_translator] INTENT translation failed validation after retry")
                    return

            review_ko = _merge_intent_translation(review, translated)
            ko_doc = {
                "run_id": review_doc.get("run_id", run_id),
                "review_ko": review_ko,
            }
            write_workspace_file(INTENT_REVIEW_KO_REL, json.dumps(ko_doc, indent=2, ensure_ascii=False))
            log_pm_audit("[batch_translator] wrote founder_intent_review_ko.json")
            if run_id:
                log_reasoning_event(
                    run_id=run_id, phase="Translation", event_type="translation_generated",
                    domain="translation", category="sync",
                    artifact=INTENT_REVIEW_KO_REL,
                    details={"target": "intent_review", "structure_warnings": warnings},
                )
        except Exception as exc:
            log_pm_audit(f"[batch_translator] UNEXPECTED ERROR in ensure_intent_review_korean: {exc}")


def _decisions_translate_payload(agg: dict) -> dict:
    selected = [
        {k: item[k] for k in ("id", "name", "rationale") if k in item and item[k]}
        for item in agg.get("selected") or []
        if isinstance(item, dict)
    ]
    rejected = [
        {k: item[k] for k in ("id", "name", "reason") if k in item and item[k]}
        for item in agg.get("rejected") or []
        if isinstance(item, dict)
    ]
    tradeoffs = [
        {k: item[k] for k in ("accepted", "sacrificed", "reason") if k in item and item[k]}
        for item in agg.get("tradeoffs") or []
        if isinstance(item, dict)
    ]
    payload: dict = {}
    if selected:
        payload["selected"] = selected
    if rejected:
        payload["rejected"] = rejected
    if tradeoffs:
        payload["tradeoffs"] = tradeoffs
    return payload


def ensure_decisions_korean(run_id: str, run_root: str | None = None) -> None:
    """Aggregate decisions and write logs/decisions_ko/{run_id}.json."""
    try:
        agg = aggregate_decisions(run_id, run_root)
        payload = _decisions_translate_payload(agg)
        if not payload:
            log_pm_audit(f"[batch_translator] SKIP: no decision text for run {run_id}")
            return

        ko_path = _decisions_ko_abs(run_id)
        translated = _call_json_translator(payload, run_id=run_id, artifact=ko_path)
        if translated is None:
            return

        warnings = _validate_same_structure(payload, translated)
        if warnings:
            for w in warnings:
                log_pm_audit(f"[batch_translator] DECISIONS_STRUCTURE_MISMATCH: {w}")
            translated = _call_json_translator(payload, run_id=run_id, artifact=ko_path)
            if translated is None:
                return
            warnings = _validate_same_structure(payload, translated)
            if warnings:
                log_pm_audit("[batch_translator] DECISIONS translation failed validation after retry")
                return

        ko_doc = {
            "run_id": run_id,
            "selected_ko": translated.get("selected") or [],
            "rejected_ko": translated.get("rejected") or [],
            "tradeoffs_ko": translated.get("tradeoffs") or [],
            "structure_warnings": warnings,
        }
        os.makedirs(DECISIONS_KO_DIR, exist_ok=True)
        with open(ko_path, "w", encoding="utf-8") as f:
            json.dump(ko_doc, f, indent=2, ensure_ascii=False)
        log_pm_audit(f"[batch_translator] wrote {ko_path}")
        log_reasoning_event(
            run_id=run_id, phase="Translation", event_type="translation_generated",
            domain="translation", category="sync",
            artifact=ko_path,
            details={"target": "decisions", "structure_warnings": warnings},
        )
    except Exception as exc:
        log_pm_audit(f"[batch_translator] UNEXPECTED ERROR in ensure_decisions_korean: {exc}")


def merge_intent_review_display(review: dict, review_ko: dict) -> dict:
    """Merge KO sidecar into review for UI display."""
    return _merge_intent_translation(review, review_ko)


def intent_review_ko_stale(run_id: str) -> bool:
    """True when KO sidecar is missing, wrong run, or older than EN review."""
    if not os.path.exists(INTENT_REVIEW_KO_ABS):
        return True
    ko_doc = load_intent_review_ko()
    if not ko_doc or ko_doc.get("run_id") != run_id:
        return True
    review_abs = os.path.join(CURRENT_DIR, "kernel", "founder_intent_review.json")
    try:
        if os.path.getmtime(review_abs) > os.path.getmtime(INTENT_REVIEW_KO_ABS):
            return True
    except OSError:
        pass
    return False


def ensure_intent_review_korean_if_needed(review_doc: dict, run_id: str) -> dict | None:
    """Translate when stale; return review_ko dict or None."""
    if intent_review_ko_stale(run_id):
        ensure_intent_review_korean(review_doc, run_id=run_id)
    ko_doc = load_intent_review_ko()
    if ko_doc and ko_doc.get("run_id") == run_id:
        return ko_doc.get("review_ko")
    return None


def load_intent_review_ko() -> dict | None:
    if not os.path.exists(INTENT_REVIEW_KO_ABS):
        return None
    try:
        with open(INTENT_REVIEW_KO_ABS, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def ensure_decisions_korean_if_needed(run_id: str, run_root: str | None = None) -> dict | None:
    """Translate decisions when sidecar missing; return ko doc or None."""
    existing = load_decisions_ko(run_id)
    if existing:
        return existing
    ensure_decisions_korean(run_id, run_root=run_root)
    return load_decisions_ko(run_id)


def load_decisions_ko(run_id: str) -> dict | None:
    path = _decisions_ko_abs(run_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
