"""
Agent profile endpoint for Live Feed detail panel.
"""
from fastapi import APIRouter, HTTPException, Query

from harness.agent_profile import build_agent_profile, phases_for_role_title
from harness.role_registry import resolve_role
from server.routes.workspace import _resolve_run_root

router = APIRouter()


@router.get("/runs/{run_id}/agent-profile")
def get_agent_profile(
    run_id: str,
    phase: str | None = Query(None),
    role: str | None = Query(None, description="Korean role title, e.g. 수석 아키텍트"),
):
    phases: list[str] = []
    if phase:
        phases = [phase]
    elif role:
        phases = phases_for_role_title(role)
        if not phases:
            raise HTTPException(status_code=404, detail=f"Unknown role: {role}")
    else:
        raise HTTPException(status_code=400, detail="Provide phase or role query parameter.")

    try:
        run_root, label = _resolve_run_root(run_id)
    except HTTPException:
        run_root = None
        label = "trace_only"

    profile = build_agent_profile(run_id, phases, run_root)
    profile["root"] = label
    profile["role_title_ko"] = resolve_role(phases[0])["title_ko"]
    return profile
