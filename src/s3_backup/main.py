import sys

from src.s3_backup.logging_setup import setup_logging, get_logger
from src.s3_backup.config import load_bucket_targets
from src.s3_backup.sync import sync_bucket
from src.s3_backup.summary import BucketResult, RunSummary
from src.s3_backup.telegram import send_telegram_message


def main():
    """Orchestrate the full backup run."""
    setup_logging()
    logger = get_logger()

    logger.info("Starting S3 backup run")

    try:
        targets = load_bucket_targets()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    if len(targets) == 0:
        logger.warning("No buckets configured (BACKUP_BUCKET_* env vars not found)")
        sys.exit(1)

    logger.info(f"Loaded {len(targets)} bucket(s) to sync")

    results = []
    for target in targets:
        try:
            result = sync_bucket(target)
            results.append(result)
        except Exception as e:
            logger.error(
                f"Unexpected error syncing bucket {target.name}: {e}",
                exc_info=True,
            )
            results.append(
                BucketResult(
                    name=target.name,
                    success=False,
                    duration_seconds=0,
                    error=str(e),
                )
            )

    summary = RunSummary(results=results)
    logger.info(summary.to_log_string())

    message = summary.to_telegram_message()
    send_telegram_message(message)

    exit_code = 0 if all(r.success for r in results) else 1
    logger.info(f"Backup run complete, exit code: {exit_code}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
