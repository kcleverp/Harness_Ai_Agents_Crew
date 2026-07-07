import json
import re

from harness.audit_hooks import log_pm_audit
from harness.llm_factory import build_technical_review_llm
from harness.safe_file_tools import patch_workspace_json, read_workspace_file


def _strip_json_array(raw: str) -> str:
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def run_patch_crew(file_path: str, errors: list, run_id: str = ""):
    """Apply schema fixes via one direct LLM call + partial JSON patches (no Crew loop)."""
    del run_id  # reserved for future telemetry
    current = read_workspace_file(file_path)
    if current.startswith("Error:"):
        log_pm_audit(f"Patch | Status=SKIP | {current}")
        return None

    error_details = "\n".join(errors)
    patch_llm = build_technical_review_llm()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a JSON schema repair assistant. "
                "Output ONLY a JSON array of minimal patches. No commentary.\n"
                'Each item: {"key_path": "dot.or.index.path", "value": <any JSON value>}\n'
                "Fix ONLY the validation errors listed. Do not rewrite unrelated fields."
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {file_path}\n\n"
                f"Validation errors:\n{error_details}\n\n"
                f"Current JSON:\n{current}\n\n"
                "Return the patches array only."
            ),
        },
    ]

    try:
        raw = patch_llm.call(messages)
    except Exception as exc:
        log_pm_audit(f"Patch | Status=LLM_ERROR | {exc}")
        return None

    try:
        patches = json.loads(_strip_json_array(raw))
    except json.JSONDecodeError as exc:
        log_pm_audit(f"Patch | Status=PARSE_ERROR | {exc}")
        return None

    if not isinstance(patches, list):
        log_pm_audit("Patch | Status=INVALID | expected JSON array")
        return None

    applied = 0
    for item in patches:
        if not isinstance(item, dict):
            continue
        key_path = item.get("key_path")
        if not key_path:
            continue
        value_json = json.dumps(item.get("value"), ensure_ascii=False)
        result = patch_workspace_json(file_path, str(key_path), value_json)
        log_pm_audit(f"Patch | {result}")
        if result.startswith("Success"):
            applied += 1

    log_pm_audit(f"Patch | Status=DONE | applied={applied}/{len(patches)}")
    return {"applied": applied, "total": len(patches)}
