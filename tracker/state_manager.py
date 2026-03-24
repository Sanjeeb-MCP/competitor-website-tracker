"""JSON state persistence with atomic writes."""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _atomic_write(path: str, data) -> None:
    """Write JSON data atomically using temp file + rename."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def load_state(path: str | None = None) -> dict:
    """Load the current state from JSON. Returns empty state if not found."""
    path = path or os.path.join(DATA_DIR, "state.json")
    if not os.path.exists(path):
        return {
            "last_run": None,
            "run_count": 0,
            "competitors": {},
        }
    with open(path) as f:
        return json.load(f)


def save_state(state: dict, path: str | None = None) -> None:
    """Save the current state to JSON."""
    path = path or os.path.join(DATA_DIR, "state.json")
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(path, state)
    logger.info("State saved to %s", path)


def load_changes(path: str | None = None) -> list:
    """Load the historical changelog from JSON."""
    path = path or os.path.join(DATA_DIR, "changes.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def append_changes(
    new_changes: list[dict],
    path: str | None = None,
    max_entries: int = 5000,
) -> None:
    """Append new changes to the changelog, trimming to max_entries."""
    path = path or os.path.join(DATA_DIR, "changes.json")
    existing = load_changes(path)
    combined = new_changes + existing  # newest first
    combined = combined[:max_entries]
    _atomic_write(path, combined)
    logger.info("Saved %d new changes (%d total)", len(new_changes), len(combined))
