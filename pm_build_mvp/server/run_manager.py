"""
run_manager.py — Owns workflow execution threads for the FastAPI server.

Constraints:
- Exactly ONE run may be active at a time. The core engine works on the shared
  workspace/current/ directory, so concurrent runs would corrupt each other.
- run_planning() is executed on a daemon thread; the server process must stay
  importable/responsive while the workflow runs.

Status model (GET /runs/{id}):
  running          thread alive, no pending founder gate
  awaiting_choice  thread alive, intent review written, founder choice missing
  complete         finished with ok=True
  rejected         finished, founder rejected at intent gate (result.rejected)
  failed           finished with ok=False or raised an exception
"""
import datetime
import os
import threading
import uuid
from typing import Optional

# Single source of truth for the gate handshake paths.
from harness.intent_review import _CHOICE_ABS as FOUNDER_CHOICE_FILE
from harness.intent_review import _REVIEW_ABS as INTENT_REVIEW_FILE


class RunHandle:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.thread: Optional[threading.Thread] = None
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.started_at = datetime.datetime.now().isoformat(timespec="seconds")
        self.finished_at: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def status(self) -> str:
        if self.is_running:
            if os.path.exists(INTENT_REVIEW_FILE) and not os.path.exists(FOUNDER_CHOICE_FILE):
                return "awaiting_choice"
            return "running"
        if self.error is not None:
            return "failed"
        if self.result is not None:
            if self.result.get("rejected"):
                return "rejected"
            return "complete" if self.result.get("ok") else "failed"
        return "failed"

    def payload(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class RunManager:
    def __init__(self):
        self._runs: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

    def active_run(self) -> Optional[RunHandle]:
        with self._lock:
            for handle in self._runs.values():
                if handle.is_running:
                    return handle
        return None

    def start_run(self) -> RunHandle:
        """Spawn a workflow thread. Raises RuntimeError when a run is active."""
        with self._lock:
            for handle in self._runs.values():
                if handle.is_running:
                    raise RuntimeError(
                        f"Run {handle.run_id} is still active. "
                        "Only one run at a time is supported (shared workspace/current)."
                    )
            run_id = str(uuid.uuid4())
            handle = RunHandle(run_id)
            self._runs[run_id] = handle

        def _target():
            try:
                # Import inside the thread so server startup never fails on
                # workflow-side import errors (missing prompts, etc.).
                from workflows.planning_workflow import run_planning
                handle.result = run_planning(run_id=run_id)
            except Exception as exc:  # surfaced via GET /runs/{id}
                handle.error = f"{type(exc).__name__}: {exc}"
            finally:
                handle.finished_at = datetime.datetime.now().isoformat(timespec="seconds")

        thread = threading.Thread(target=_target, name=f"run-{run_id[:8]}", daemon=True)
        handle.thread = thread
        thread.start()
        return handle

    def get(self, run_id: str) -> Optional[RunHandle]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[dict]:
        with self._lock:
            handles = list(self._runs.values())
        return [h.payload() for h in sorted(handles, key=lambda h: h.started_at, reverse=True)]


# Module-level singleton shared by all routes.
manager = RunManager()
