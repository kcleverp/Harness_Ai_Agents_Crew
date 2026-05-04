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

def create_archive_snapshot(custom_tag: str = None):
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    if custom_tag:
        snapshot_name = f"{ts}_{custom_tag}"
    else:
        run_id = get_next_run_id()
        snapshot_name = f"{ts}_run_{run_id:03d}"
        
    snapshot_path = os.path.join(ARCHIVE_DIR, snapshot_name)
    os.makedirs(snapshot_path, exist_ok=True)
    
    for filename in os.listdir(CURRENT_DIR):
        src = os.path.join(CURRENT_DIR, filename)
        if os.path.isfile(src):
            shutil.copy2(src, snapshot_path)
            
    return snapshot_path
