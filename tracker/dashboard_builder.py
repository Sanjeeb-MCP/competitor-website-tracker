"""Builds the static dashboard by copying data files to docs/."""

import json
import logging
import os
import shutil

from tracker.state_manager import DATA_DIR

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
DOCS_DATA_DIR = os.path.join(DOCS_DIR, "data")


def build_dashboard() -> None:
    """Copy data files to docs/data/ for the static dashboard."""
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)

    for filename in ["state.json", "changes.json"]:
        src = os.path.join(DATA_DIR, filename)
        dst = os.path.join(DOCS_DATA_DIR, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            logger.info("Copied %s to docs/data/", filename)
        else:
            # Write empty defaults so dashboard doesn't 404
            with open(dst, "w") as f:
                if filename == "changes.json":
                    json.dump([], f)
                else:
                    json.dump({"competitors": {}, "run_count": 0}, f)

    logger.info("Dashboard data updated")
