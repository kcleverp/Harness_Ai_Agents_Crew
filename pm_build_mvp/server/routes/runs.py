"""Run lifecycle endpoints: start a workflow run, query its status."""
from fastapi import APIRouter, HTTPException

from harness.llm_factory import validate_llm_env
from harness.prompt_loader import validate_prompt_files, WORKFLOW_REQUIRED_PROMPTS
from server.run_manager import manager

router = APIRouter()


@router.post("/runs", status_code=201)
def start_run():
    ok, env_errors = validate_llm_env()
    if not ok:
        raise HTTPException(status_code=400, detail={"reason": "llm_env_invalid", "errors": env_errors})

    missing_prompts = validate_prompt_files(WORKFLOW_REQUIRED_PROMPTS)
    if missing_prompts:
        raise HTTPException(
            status_code=400,
            detail={"reason": "prompts_missing", "errors": [f"prompts/{n}.md" for n in missing_prompts]},
        )

    try:
        handle = manager.start_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return handle.payload()


@router.get("/runs")
def list_runs():
    return {"runs": manager.list_runs()}


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    handle = manager.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")
    return handle.payload()
