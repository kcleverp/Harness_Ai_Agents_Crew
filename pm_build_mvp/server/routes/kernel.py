"""
Founder Kernel endpoints.

GET /kernel  → current founder_kernel.json (with hash)
PUT /kernel  → replace the 4 content lists, re-hash, persist.
               Rejected while a run is active: mid-run kernel mutation would
               trip assert_kernel_integrity and kill the pipeline. Use the
               intent gate's edit choice instead during awaiting_choice.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from harness.kernel_guard import load_founder_kernel, save_founder_kernel
from server.run_manager import manager

router = APIRouter()


class KernelBody(BaseModel):
    core_thesis: list[str] = Field(default_factory=list)
    non_negotiables: list[str] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    founder_convictions: list[str] = Field(default_factory=list)


@router.get("/kernel")
def get_kernel():
    return load_founder_kernel()


@router.put("/kernel")
def put_kernel(body: KernelBody):
    active = manager.active_run()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run {active.run_id[:8]} is active (status={active.status()}). "
                "Kernel edits during a run must go through the intent gate (choice=edit)."
            ),
        )
    kernel_data = load_founder_kernel()
    kernel_data["core_thesis"] = body.core_thesis
    kernel_data["non_negotiables"] = body.non_negotiables
    kernel_data["anti_patterns"] = body.anti_patterns
    kernel_data["founder_convictions"] = body.founder_convictions
    save_founder_kernel(kernel_data)
    return kernel_data
