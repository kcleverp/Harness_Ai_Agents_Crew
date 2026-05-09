import os
import shutil
import datetime

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../workspace"))
CURRENT_DIR = os.path.join(WORKSPACE_DIR, "current")
ARCHIVE_DIR = os.path.join(WORKSPACE_DIR, "archive")

def get_next_run_id() -> int:
    if not os.path.exists(ARCHIVE_DIR):
        return 1
    dirs =[d for d in os.listdir(ARCHIVE_DIR) if os.path.isdir(os.path.join(ARCHIVE_DIR, d))]
    run_count = sum(1 for d in dirs if "_run_" in d)
    return run_count + 1

def create_archive_snapshot(custom_tag: str = None, run_id: str = ""):
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    rid_suffix = f"_{run_id[:8]}" if run_id else ""
    if custom_tag:
        snapshot_name = f"{ts}_{custom_tag}{rid_suffix}"
    else:
        seq = get_next_run_id()
        snapshot_name = f"{ts}_run_{seq:03d}{rid_suffix}"

    snapshot_path = os.path.join(ARCHIVE_DIR, snapshot_name)
    shutil.copytree(CURRENT_DIR, snapshot_path)
    return snapshot_path
