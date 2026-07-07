"""Post-process translator: keeps founder_summary_ko.md in sync with founder_summary.md.

Entry point: ensure_founder_summary_korean()
  - Called from planning_workflow.run_planning() finally block ONLY.
  - Never part of the PM Crew tasks or agents list.
"""

import os
import re

from harness.paths import WORKSPACE_DIR

from harness.audit_hooks import log_pm_audit, log_reasoning_event
from harness.llm_factory import build_translator_llm_from_env
from harness.prompt_loader import load_prompt
from harness.safe_file_tools import read_workspace_file, write_workspace_file

_EN_PATH = "current/docs/founder_summary.md"
_KO_PATH = "current/docs/founder_summary_ko.md"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_founder_summary_korean(run_id: str = "") -> None:
    """Decide whether (re)generation is needed and run run_translator() if so.

    Evaluation order (first failing condition wins):
      1. EN missing           → log, exit (no translation)
      2. EN read error        → log, exit
      3. EN empty/whitespace  → log, exit (no translation)
      4. KO missing           → translate
      5. KO empty/whitespace  → translate (partial write recovery)
      6. KO read error        → translate (corrupted file recovery)
      7. EN newer than KO     → translate (staleness/drift)
      else                    → KO is valid and fresh, skip
    """
    try:
        _run(reason_check=True, run_id=run_id)
    except Exception as exc:
        # Swallow so the original exception from kickoff/validation is not masked.
        log_pm_audit(f"[translator] UNEXPECTED ERROR in ensure_founder_summary_korean: {exc}")


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def _run(reason_check: bool = True, run_id: str = "") -> None:
    workspace_dir = WORKSPACE_DIR
    en_abs = os.path.join(workspace_dir, _EN_PATH)
    ko_abs = os.path.join(workspace_dir, _KO_PATH)

    # --- Step 1/2/3: EN guard ---
    if not os.path.exists(en_abs):
        log_pm_audit("[translator] SKIP: founder_summary.md not found — no translation performed")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_skipped",
                domain="translation", category="sync",
                artifact=_EN_PATH, details={"reason": "source_not_found"},
            )
        return

    try:
        en_content = _read_abs(en_abs)
    except Exception as exc:
        log_pm_audit(f"[translator] SKIP: cannot read founder_summary.md — {exc}")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_failed",
                domain="translation", category="sync",
                artifact=_EN_PATH, details={"reason": "source_read_error", "error": str(exc)},
            )
        return

    if not en_content.strip():
        log_pm_audit("[translator] SKIP: founder_summary.md is empty — no translation performed")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_skipped",
                domain="translation", category="sync",
                artifact=_EN_PATH, details={"reason": "source_empty"},
            )
        return

    # --- Step 4/5/6/7: KO guard + staleness ---
    reason = _needs_regeneration(en_abs, ko_abs)
    if reason is None:
        log_pm_audit("[translator] OK: founder_summary_ko.md is valid and up-to-date — skipped")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_skipped",
                domain="translation", category="sync",
                artifact=_KO_PATH, details={"reason": "up_to_date"},
            )
        return

    log_pm_audit(f"[translator] REGENERATE: {reason}")
    if run_id:
        log_reasoning_event(
            run_id=run_id, phase="Translation", event_type="translation_stale",
            domain="translation", category="sync",
            artifact=_KO_PATH, details={"reason": reason},
        )
    run_translator(en_content, run_id=run_id)


def _needs_regeneration(en_abs: str, ko_abs: str) -> str | None:
    """Return a reason string if KO needs to be (re)generated, else None."""
    if not os.path.exists(ko_abs):
        return "founder_summary_ko.md does not exist"

    try:
        ko_content = _read_abs(ko_abs)
    except Exception as exc:
        return f"founder_summary_ko.md unreadable ({exc})"

    if not ko_content.strip():
        return "founder_summary_ko.md is empty or whitespace (partial write recovery)"

    # mtime staleness: EN updated after KO was last written
    try:
        if os.path.getmtime(en_abs) > os.path.getmtime(ko_abs):
            return "founder_summary.md is newer than founder_summary_ko.md (staleness)"
    except OSError:
        pass  # mtime unavailable — skip staleness check, keep existing KO

    return None  # KO is valid and fresh


# ---------------------------------------------------------------------------
# Core translation
# ---------------------------------------------------------------------------

def run_translator(en_content: str, run_id: str = "") -> None:
    """Translate en_content and write result to current/docs/founder_summary_ko.md.

    Uses Translator-specific LLM (Gemini Flash or fallback).
    Does NOT use a Crew — single direct LLM call.
    Never touches founder_summary.md.
    """
    persona = load_prompt("translator_system")
    llm = build_translator_llm_from_env()

    messages = [
        {"role": "system", "content": persona},
        {
            "role": "user",
            "content": (
                "Translate the following Markdown document into Korean following all rules "
                "in your persona. Output the translated Markdown body only — no extra text.\n\n"
                f"{en_content}"
            ),
        },
    ]

    try:
        ko_content = llm.call(messages)
    except Exception as exc:
        log_pm_audit(f"[translator] LLM call failed: {exc}")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_failed",
                domain="translation", category="sync",
                artifact=_KO_PATH, details={"reason": "llm_call_failed", "error": str(exc)},
            )
        return

    if not ko_content or not ko_content.strip():
        log_pm_audit("[translator] LLM returned empty response — founder_summary_ko.md NOT written")
        if run_id:
            log_reasoning_event(
                run_id=run_id, phase="Translation", event_type="translation_failed",
                domain="translation", category="sync",
                artifact=_KO_PATH, details={"reason": "llm_empty_response"},
            )
        return

    # Structure validation (lenient: warn only, keep file)
    warnings = _validate_structure(en_content, ko_content)
    if warnings:
        for w in warnings:
            log_pm_audit(f"[translator] TRANSLATION_STRUCTURE_MISMATCH: {w}")

    result = write_workspace_file(_KO_PATH, ko_content)
    log_pm_audit(f"[translator] write result: {result}")
    if run_id:
        log_reasoning_event(
            run_id=run_id, phase="Translation", event_type="translation_generated",
            domain="translation", category="sync",
            artifact=_KO_PATH,
            details={"result": str(result), "structure_warnings": warnings},
        )


# ---------------------------------------------------------------------------
# Structure validation (lenient)
# ---------------------------------------------------------------------------

def _validate_structure(en: str, ko: str) -> list[str]:
    """Compare heading and list counts between EN and KO (code fences excluded).

    Returns a list of warning strings (empty = no issues).
    """
    warnings = []

    en_body = _strip_code_fences(en)
    ko_body = _strip_code_fences(ko)

    en_headings = len(re.findall(r"^#{1,6}\s", en_body, re.MULTILINE))
    ko_headings = len(re.findall(r"^#{1,6}\s", ko_body, re.MULTILINE))
    if en_headings != ko_headings:
        warnings.append(f"heading count EN={en_headings} KO={ko_headings}")

    en_bullets = len(re.findall(r"^[-*+]\s", en_body, re.MULTILINE))
    ko_bullets = len(re.findall(r"^[-*+]\s", ko_body, re.MULTILINE))
    if en_bullets != ko_bullets:
        warnings.append(f"bullet count EN={en_bullets} KO={ko_bullets}")

    en_numbered = len(re.findall(r"^\d+\.\s", en_body, re.MULTILINE))
    ko_numbered = len(re.findall(r"^\d+\.\s", ko_body, re.MULTILINE))
    if en_numbered != ko_numbered:
        warnings.append(f"numbered list count EN={en_numbered} KO={ko_numbered}")

    return warnings


def _strip_code_fences(text: str) -> str:
    """Remove content between ``` fences so they don't skew counts."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_abs(abs_path: str) -> str:
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()
