"""
Workspace artifact endpoints.

GET /runs/{run_id}/workspace        → file tree for the run
GET /runs/{run_id}/workspace/file   → single file content (?path=relative)

Run root resolution: archived snapshot (workspace/archive/*_{run_id[:8]})
is preferred because it is immutable; the live workspace/current/ is used
for runs that have not been archived yet (running / awaiting_choice).

Path policy mirrors safe_file_tools: .md/.json only, no traversal outside
the resolved run root.
"""
import os

from fastapi import APIRouter, HTTPException

from harness.paths import ARCHIVE_DIR, CURRENT_DIR
from server.run_manager import manager

router = APIRouter()

_ALLOWED_EXTENSIONS = (".md", ".json")


def _resolve_run_root(run_id: str) -> tuple[str, str]:
    """Return (abs_root, label). Raises 404 when the run has no workspace."""
    suffix = f"_{run_id[:8]}"
    if os.path.isdir(ARCHIVE_DIR):
        matches = sorted(d for d in os.listdir(ARCHIVE_DIR)
                         if d.endswith(suffix) and os.path.isdir(os.path.join(ARCHIVE_DIR, d)))
        if matches:
            name = matches[-1]
            return os.path.join(ARCHIVE_DIR, name), f"archive/{name}"
    if manager.get(run_id) is not None:
        return CURRENT_DIR, "current"
    raise HTTPException(status_code=404, detail=f"No workspace found for run_id: {run_id}")


def _list_files(root: str) -> list[dict]:
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith(_ALLOWED_EXTENSIONS):
                continue
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
            files.append({
                "path": rel_path,
                "name": fname,
                "dir": os.path.dirname(rel_path).replace("\\", "/"),
                "ext": os.path.splitext(fname)[1].lstrip("."),
                "size": os.path.getsize(abs_path),
            })
    files.sort(key=lambda f: (f["dir"], f["name"]))
    return files


@router.get("/runs/{run_id}/workspace")
def get_workspace_tree(run_id: str):
    root, label = _resolve_run_root(run_id)
    return {"run_id": run_id, "root": label, "files": _list_files(root)}


@router.get("/runs/{run_id}/workspace/file")
def get_workspace_file(run_id: str, path: str):
    root, label = _resolve_run_root(run_id)
    abs_target = os.path.abspath(os.path.join(root, path))
    try:
        inside = os.path.commonpath([root, abs_target]) == root
    except ValueError:
        inside = False
    if not inside:
        raise HTTPException(status_code=403, detail="Path traversal outside run workspace.")
    if not abs_target.endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=403, detail="Only .md/.json files are readable.")
    if not os.path.isfile(abs_target):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    with open(abs_target, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "run_id": run_id,
        "root": label,
        "path": path.replace("\\", "/"),
        "ext": os.path.splitext(abs_target)[1].lstrip("."),
        "content": content,
    }
