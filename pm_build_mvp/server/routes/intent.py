"""
Intent Review Gate endpoints (Layer 0.5 file handshake).

GET  /runs/{run_id}/intent-review   → review document written by the gate
POST /runs/{run_id}/intent-choice   → founder decision; writes founder_choice.json
                                      which the polling gate consumes.
"""
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harness.batch_translator import (
    ensure_intent_review_korean_if_needed,
    merge_intent_review_display,
)
from harness.intent_review import _CHOICE_ABS, _REVIEW_ABS
from server.run_manager import manager

router = APIRouter()

_VALID_CHOICES = ("proceed", "reject", "edit")
_KERNEL_CONTENT_KEYS = ("core_thesis", "non_negotiables", "anti_patterns", "founder_convictions")


class IntentChoice(BaseModel):
    choice: str
    reason: str | None = None
    kernel: dict | None = None  # required when choice == "edit"


@router.get("/runs/{run_id}/intent-review")
def get_intent_review(run_id: str):
    if not os.path.exists(_REVIEW_ABS):
        raise HTTPException(status_code=404, detail="No intent review available.")
    with open(_REVIEW_ABS, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("run_id") != run_id:
        raise HTTPException(
            status_code=409,
            detail=f"Intent review belongs to run {doc.get('run_id')}, not {run_id}.",
        )

    review_ko = ensure_intent_review_korean_if_needed(doc, run_id)
    if review_ko:
        doc["review_ko"] = review_ko
        doc["review"] = merge_intent_review_display(doc.get("review") or {}, review_ko)
        doc["translation_status"] = "ok"
    else:
        doc["translation_status"] = "pending"

    return doc


@router.post("/runs/{run_id}/intent-choice")
def post_intent_choice(run_id: str, body: IntentChoice):
    handle = manager.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")
    if handle.status() != "awaiting_choice":
        raise HTTPException(
            status_code=409,
            detail=f"Run is not awaiting a founder choice (status={handle.status()}).",
        )

    if body.choice not in _VALID_CHOICES:
        raise HTTPException(status_code=422, detail=f"choice must be one of {_VALID_CHOICES}")
    if body.choice == "edit":
        if not body.kernel or not any(k in body.kernel for k in _KERNEL_CONTENT_KEYS):
            raise HTTPException(
                status_code=422,
                detail=f"choice=edit requires a kernel object with at least one of {_KERNEL_CONTENT_KEYS}",
            )

    payload = {"choice": body.choice, "reason": body.reason, "kernel": body.kernel}

    # Atomic write: the gate polls this path every second and tolerates
    # partial reads, but temp+replace removes the race entirely.
    tmp_path = _CHOICE_ABS + ".tmp"
    os.makedirs(os.path.dirname(_CHOICE_ABS), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, indent=2, ensure_ascii=False))
    os.replace(tmp_path, _CHOICE_ABS)

    return {"ok": True, "choice": body.choice}
