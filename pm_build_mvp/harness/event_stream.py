"""
event_stream.py — In-process pub/sub bridge for canonical telemetry events.

Purpose:
- When the FastAPI server hosts a run, every event written to the canonical
  stream (reasoning_trace.jsonl) is also published here so SSE endpoints can
  push it to connected UIs in real time.
- When the workflow runs standalone (python main.py), the stream is disabled
  and publish() is a no-op — zero overhead, zero behavior change.

Activation:
- env PM_EVENT_STREAM=1  (read once at import), or
- programmatic enable()  (called by server startup, same process).

This module has no third-party dependencies and must stay import-light:
audit_hooks imports it on every workflow run.
"""
import os
import queue
import threading

_MAX_QUEUE_SIZE = 1000

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()
_enabled: bool = os.getenv("PM_EVENT_STREAM", "").lower() in ("1", "true")


def enable() -> None:
    """Turn on event publishing (idempotent). Called by server startup."""
    global _enabled
    _enabled = True


def subscribe() -> queue.Queue:
    """Register a new subscriber queue and return it.

    Caller must call unsubscribe() when done (e.g. SSE client disconnect).
    """
    q: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def publish(event: dict) -> None:
    """Fan out one event dict to all subscribers. No-op when disabled.

    Slow consumers never block the workflow: when a subscriber queue is
    full the event is dropped for that subscriber only (SSE clients can
    recover via jsonl backfill on reconnect).
    """
    if not _enabled:
        return
    with _lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass
