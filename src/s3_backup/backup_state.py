import json
import os
from pathlib import Path

STATE_FILENAME = ".s3_backup_state.json"


def dir_has_entries(dest_path: str) -> bool:
    """
    Cheap, O(1)-ish check for "does this directory have anything in it at
    all" — stops at the first entry found instead of walking the whole tree.
    Used by the shrink guard instead of a full recursive size scan, which is
    prohibitively slow once a bucket has hundreds of thousands of objects.
    """
    try:
        with os.scandir(dest_path) as it:
            for entry in it:
                if entry.name != STATE_FILENAME:
                    return True
        return False
    except OSError:
        return False


def compute_dir_size_bytes(dest_path: str) -> int:
    """
    Total size in bytes of everything currently under dest_path, via a full
    recursive walk. Expensive for huge trees (hundreds of thousands of
    files) — only meant for a bucket's very first backup (no incremental
    baseline yet) or an operator-triggered recount, never the common case.
    """
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
