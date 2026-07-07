"""One-time workspace seeding — raw_ideas.md and founder_kernel.json starters."""
import os
import shutil

from harness.paths import BASE_DIR, TEMPLATES_DIR


def init_workspace() -> None:
    """Create dirs and copy sample files when missing (idempotent)."""
    from harness.paths import ARCHIVE_DIR, CURRENT_DIR, LOG_DIR

    for d in (CURRENT_DIR, ARCHIVE_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)

    raw_ideas_path = os.path.join(BASE_DIR, "workspace", "raw_ideas.md")
    if not os.path.exists(raw_ideas_path):
        shutil.copy2(
            os.path.join(TEMPLATES_DIR, "raw_ideas.sample.md"),
            raw_ideas_path,
        )

    kernel_path = os.path.join(BASE_DIR, "workspace", "founder_kernel.json")
    if not os.path.exists(kernel_path):
        shutil.copy2(
            os.path.join(TEMPLATES_DIR, "founder_kernel.sample.json"),
            kernel_path,
        )
