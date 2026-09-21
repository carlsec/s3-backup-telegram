import os
import re
import subprocess
import threading
import time

from src.s3_backup import backup_state
from src.s3_backup.config import BucketTarget
from src.s3_backup.summary import BucketResult
from src.s3_backup.logging_setup import get_logger

SHRINK_GUARD_RATIO = float(
    os.getenv("BACKUP_SHRINK_GUARD_RATIO", str(backup_state.DEFAULT_SHRINK_GUARD_RATIO))
)
SYNC_TIMEOUT_SECONDS = float(os.getenv("BACKUP_SYNC_TIMEOUT_HOURS", "6")) * 3600

_CP_LINE_RE = re.compile(r"^cp (\S+) (.+)$")
_PROGRESS_LOG_EVERY = 500


def sync_bucket(target: BucketTarget) -> BucketResult:
    """
    Sync a single S3 bucket to a local destination path.

    Creates the destination path if it doesn't exist, runs `s5cmd sync`
    (chosen over `aws s3 sync` because it's dramatically faster for buckets
    with hundreds of thousands of objects — see README.md "Why s5cmd"),
    streaming its output line by line so progress is visible in the logs
    while a large sync is still running, instead of going silent for hours.
    Returns a BucketResult with success/failure, duration, and transfer
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
    dest_arg = target.dest_path.rstrip("/") + "/"
    cmd = ["s5cmd", "sync", f"s3://{target.name}/*", dest_arg]
    assert "--delete" not in cmd

    start_time = time.time()
    objects_transferred = 0
    bytes_transferred = 0
    error_lines = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # s5cmd has no built-in timeout, and can hang indefinitely (e.g. a
        # stalled credential lookup) instead of failing fast — this watchdog
        # guarantees one stuck bucket can never block the rest of the run
        # forever.
        timed_out = threading.Event()

        def _kill_on_timeout():
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(SYNC_TIMEOUT_SECONDS, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()

        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue

            match = _CP_LINE_RE.match(line)
            if match:
                objects_transferred += 1
                local_path = match.group(2)
                try:
                    bytes_transferred += os.path.getsize(local_path)
                except OSError:
                    pass
                if objects_transferred % _PROGRESS_LOG_EVERY == 0:
                    logger.info(
                        f"{target.name}: {objects_transferred} objects transferred so far..."
                    )
            elif line.startswith("ERROR"):
                error_lines.append(line)
                logger.warning(f"{target.name}: {line}")

        returncode = proc.wait()
        watchdog.cancel()
        duration = time.time() - start_time

        if timed_out.is_set():
            error_msg = (
                f"sync killed after exceeding BACKUP_SYNC_TIMEOUT_HOURS "
                f"({SYNC_TIMEOUT_SECONDS / 3600:.1f}h) with no completion — "
                f"likely a stalled credential lookup or network hang"
            )
            logger.error(f"Failed to sync bucket {target.name}: {error_msg}")
            return BucketResult(
                name=target.name,
                success=False,
                duration_seconds=duration,
                error=error_msg,
            )

        # s5cmd can exit 0 even when every object failed (e.g. invalid
        # credentials) — the exit code alone is not trustworthy, so a
        # bucket is only considered successful if there were zero ERROR
        # lines in its output too.
        if returncode != 0 or error_lines:
            error_msg = "; ".join(error_lines) or f"s5cmd exited with code {returncode}"
            logger.error(f"Failed to sync bucket {target.name}: {error_msg}")
            return BucketResult(
                name=target.name,
                success=False,
                duration_seconds=duration,
                error=error_msg,
            )

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
