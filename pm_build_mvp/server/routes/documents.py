"""Velog-style structured document bundle for a run."""
from fastapi import APIRouter, HTTPException

from harness.batch_translator import ensure_decisions_korean_if_needed
from harness.documents_bundle import build_documents_bundle
from server.routes.workspace import _resolve_run_root
router = APIRouter()


@router.get("/runs/{run_id}/documents")
def get_run_documents(run_id: str):
    try:
        run_root, label = _resolve_run_root(run_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"No documents found for run_id: {run_id}")
    bundle = build_documents_bundle(run_root, run_id)
    ensure_decisions_korean_if_needed(run_id, run_root)
    bundle["root"] = label
    if not bundle["sections"]:
        raise HTTPException(status_code=404, detail="Run has no readable documents yet.")
    return bundle
