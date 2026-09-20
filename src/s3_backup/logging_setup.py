import logging
import os
from pathlib import Path


def setup_logging():
    """Configure structured logging to both stdout and a log file."""
    log_file = os.getenv("BACKUP_LOG_FILE", "/var/log/s3-backup/backup.log")

    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger("s3_backup")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger():
    """Get the configured logger instance."""
    return logging.getLogger("s3_backup")
