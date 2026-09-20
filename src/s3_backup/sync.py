import os
import re
import subprocess
import time

from src.s3_backup import backup_state
from src.s3_backup.config import BucketTarget
from src.s3_backup.summary import BucketResult
from src.s3_backup.logging_setup import get_logger

SHRINK_GUARD_RATIO = float(
    os.getenv("BACKUP_SHRINK_GUARD_RATIO", str(backup_state.DEFAULT_SHRINK_GUARD_RATIO))
)

_DOWNLOAD_LINE_RE = re.compile(r"^download: s3://\S+ to (.+)$")


def sync_bucket(target: BucketTarget) -> BucketResult:
    """
    Sync a single S3 bucket to a local destination path.

    Creates the destination path if it doesn't exist, runs aws s3 sync,
    and returns a BucketResult with success/failure, duration, and transfer
    stats. On any error, catches it and returns a failed result without
    raising.
    """
    logger = get_logger()

    os.makedirs(target.dest_path, exist_ok=True)

    size_before = backup_state.compute_dir_size_bytes(target.dest_path)
    previous_total = backup_state.read_previous_total_bytes(target.dest_path)

    if previous_total is not None and backup_state.looks_suspiciously_smaller(
        size_before, previous_total, SHRINK_GUARD_RATIO
    ):
        error_msg = (
            f"destination has {size_before} bytes but the last successful run "
            f"recorded {previous_total} bytes — "
            f"this usually means the volume/NAS mount is missing or wrong. "
            f"Sync SKIPPED to avoid backing up onto a lost mount."
        )
        logger.error(f"Refusing to sync bucket {target.name}: {error_msg}")
        return BucketResult(
            name=target.name,
            success=False,
            duration_seconds=0,
            error=error_msg,
        )

    logger.info(f"Starting sync for bucket: {target.name}")

    # Pull-only backup: never pass --delete. If an object is removed from S3,
    # the local copy must be kept, never deleted, per explicit requirement.
    cmd = [
        "aws",
        "s3",
        "sync",
        f"s3://{target.name}",
        target.dest_path,
    ]
    assert "--delete" not in cmd

    start_time = time.time()

    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        duration = time.time() - start_time

        objects_transferred = 0
        bytes_transferred = 0
        for line in proc.stdout.splitlines():
            match = _DOWNLOAD_LINE_RE.match(line)
            if not match:
                continue
            objects_transferred += 1
            try:
                bytes_transferred += os.path.getsize(match.group(1))
            except OSError:
                pass

        total_local_bytes = backup_state.compute_dir_size_bytes(target.dest_path)
        backup_state.write_state(target.dest_path, total_local_bytes)

        logger.info(
            f"Successfully synced bucket {target.name} in {duration:.2f}s "
            f"(+{objects_transferred} objects, +{bytes_transferred} bytes, "
            f"{total_local_bytes} bytes total)"
        )
        return BucketResult(
            name=target.name,
            success=True,
            duration_seconds=duration,
            error=None,
            objects_transferred=objects_transferred,
            bytes_transferred=bytes_transferred,
            total_local_bytes=total_local_bytes,
        )
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        error_msg = e.stderr or f"AWS command failed with returncode {e.returncode}"
        logger.error(f"Failed to sync bucket {target.name}: {error_msg}")
        return BucketResult(
            name=target.name,
            success=False,
            duration_seconds=duration,
            error=error_msg,
        )
    except OSError as e:
        duration = time.time() - start_time
        error_msg = str(e)
        logger.error(f"OS error syncing bucket {target.name}: {error_msg}")
        return BucketResult(
            name=target.name,
            success=False,
            duration_seconds=duration,
            error=error_msg,
        )
