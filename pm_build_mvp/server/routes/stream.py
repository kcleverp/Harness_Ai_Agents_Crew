"""
SSE endpoint: GET /runs/{run_id}/events

Delivery contract:
1. Subscribe to the live event_stream FIRST (no gap window).
2. Backfill all events for run_id already in reasoning_trace.jsonl.
3. Switch to live delivery, deduplicating by event_id.
4. When the run reaches a terminal state and the queue is drained,
   emit `event: end` and close.

Each SSE message is `data: <canonical event JSON>\n\n`. The reconnect story
is the same path: backfill covers everything missed while disconnected.
"""
import json
import os
import queue

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from harness import event_stream
from harness.paths import CANONICAL_TRACE
from server.run_manager import manager

router = APIRouter()

_TERMINAL = {"complete", "failed", "rejected"}


def _backfill_events(run_id: str) -> list[dict]:
    if not os.path.exists(CANONICAL_TRACE):
        return []
    events = []
    with open(CANONICAL_TRACE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("run_id") == run_id:
                events.append(event)
    return events


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _event_generator(run_id: str):
    q = event_stream.subscribe()
    seen: set[str] = set()
    try:
        for event in _backfill_events(run_id):
            eid = event.get("event_id")
            if eid:
                seen.add(eid)
            yield _sse(event)

        idle_ticks = 0
        while True:
            try:
                event = q.get(timeout=1.0)
                idle_ticks = 0
            except queue.Empty:
                idle_ticks += 1
                handle = manager.get(run_id)
                # handle is None → archived run (backfill-only): end after drain.
                if handle is None or handle.status() in _TERMINAL:
                    yield "event: end\ndata: {}\n\n"
                    return
                # keepalive comment every ~15s so proxies don't kill the stream
                if idle_ticks % 15 == 0:
                    yield ": keepalive\n\n"
                continue

            if event.get("run_id") != run_id:
                continue
            eid = event.get("event_id")
            if eid and eid in seen:
                continue
            if eid:
                seen.add(eid)
            yield _sse(event)
    finally:
        event_stream.unsubscribe(q)


@router.get("/runs/{run_id}/events")
def stream_run_events(run_id: str):
    if manager.get(run_id) is None:
        # Allow streaming archived runs that exist only in the canonical trace.
        if not _backfill_events(run_id):
            raise HTTPException(status_code=404, detail=f"No events found for run_id: {run_id}")
    return StreamingResponse(
        _event_generator(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
