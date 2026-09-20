import json
import os
from pathlib import Path

STATE_FILENAME = ".s3_backup_state.json"
DEFAULT_SHRINK_GUARD_RATIO = 0.5


def compute_dir_size_bytes(dest_path: str) -> int:
    """Total size in bytes of everything currently under dest_path."""
    total = 0
    for root, _dirs, files in os.walk(dest_path):
        for name in files:
            if name == STATE_FILENAME:
                continue
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def read_previous_total_bytes(dest_path: str) -> int | None:
    """Last total size recorded after a successful sync, or None if unknown."""
    state_file = Path(dest_path) / STATE_FILENAME
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text()).get("total_bytes")
    except (json.JSONDecodeError, OSError):
        return None


def write_state(dest_path: str, total_bytes: int) -> None:
    state_file = Path(dest_path) / STATE_FILENAME
    state_file.write_text(json.dumps({"total_bytes": total_bytes}))


def looks_suspiciously_smaller(
    current_bytes: int,
    previous_bytes: int,
    ratio: float = DEFAULT_SHRINK_GUARD_RATIO,
) -> bool:
    """
    True if current_bytes dropped below `ratio` of previous_bytes.

    Catches the case where a NAS/volume mount silently fails to attach and
    the container sees an empty directory instead of the real destination —
    without this, a sync would happily "back up" into that empty directory,
    masking the fact that the real backup history looks gone.
    """
    if previous_bytes <= 0:
        return False
    return current_bytes < previous_bytes * ratio
