"""
Decisions timeline endpoint — cognition snapshots + canonical trace events.
"""
import json
import os

from fastapi import APIRouter, HTTPException

from harness.batch_translator import ensure_decisions_korean_if_needed, load_decisions_ko
from harness.decisions_aggregate import aggregate_decisions
from server.routes.workspace import _resolve_run_root

router = APIRouter()


def _merge_ko_fields(agg: dict, ko_doc: dict | None) -> dict:
    if not ko_doc:
        return agg
    result = dict(agg)
    result["selected_ko"] = ko_doc.get("selected_ko") or []
    result["rejected_ko"] = ko_doc.get("rejected_ko") or []
    result["tradeoffs_ko"] = ko_doc.get("tradeoffs_ko") or []
    result["translation_status"] = "ok" if not ko_doc.get("structure_warnings") else "partial"
    return result


@router.get("/runs/{run_id}/decisions")
def get_decisions(run_id: str):
    try:
        run_root, label = _resolve_run_root(run_id)
    except HTTPException:
        run_root = None
        label = "trace_only"

    agg = aggregate_decisions(run_id, run_root)
    if not agg["snapshots"] and not agg["events"] and not agg["selected"] and not agg["rejected"]:
        raise HTTPException(status_code=404, detail=f"No decision data for run_id: {run_id}")

    ko_doc = ensure_decisions_korean_if_needed(run_id, run_root)
    payload = _merge_ko_fields(agg, ko_doc)
    payload["root"] = label
    return payload
