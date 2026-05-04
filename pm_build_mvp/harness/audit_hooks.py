import os
import datetime

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
os.makedirs(LOG_DIR, exist_ok=True)

def append_log(filename: str, message: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LOG_DIR, filename), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")

def log_pm_audit(message: str):
    append_log("pm_audit.log", message)

def log_run_summary(success: bool, files: list, task_count: int, risk_score: int, patch_attempts: int = 0, risk_reasons_count: int = 0):
    status = "SUCCESS" if success else "FAILED"
    msg = (
        f"Status: {status} | Files: {len(files)} | Tasks: {task_count} | "
        f"Risk: {risk_score} | Patches: {patch_attempts} | RiskReasons: {risk_reasons_count}"
    )
    append_log("run_summary.log", msg)

def log_validation_error(filename: str, path: str, reason: str, attempt: int, error_code: str = "SCHEMA_MISMATCH"):
    msg = f"File: {filename} | Path: {path} | Code: {error_code} | Reason: {reason} | Attempt: {attempt}"
    append_log("validation_failures.log", msg)

def log_patch_action(filename: str, patch_target: str, result: str, error_code: str = "PATCH_ATTEMPT"):
    msg = f"File: {filename} | Target: {patch_target} | Code: {error_code} | Result: {result}"
    append_log("patch_actions.log", msg)
