import pytest
from unittest.mock import patch

from src.s3_backup.config import BucketTarget
from src.s3_backup.summary import BucketResult
from src.s3_backup.main import main


@pytest.fixture(autouse=True)
def _writable_log_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_LOG_FILE", str(tmp_path / "backup.log"))


def _run_main():
    with pytest.raises(SystemExit) as exc_info:
        main()
    return exc_info.value.code


@patch("src.s3_backup.main.send_telegram_message")
@patch("src.s3_backup.main.sync_bucket")
@patch("src.s3_backup.main.load_bucket_targets")
def test_main_exit_code_all_success(mock_load, mock_sync, mock_telegram):
    mock_load.return_value = [BucketTarget(name="b1", dest_path="/backup/b1")]
    mock_sync.return_value = BucketResult(
        name="b1", success=True, duration_seconds=1.0, error=None
    )
    mock_telegram.return_value = True

    assert _run_main() == 0
    mock_telegram.assert_called_once()


@patch("src.s3_backup.main.send_telegram_message")
@patch("src.s3_backup.main.sync_bucket")
@patch("src.s3_backup.main.load_bucket_targets")
def test_main_exit_code_one_failure(mock_load, mock_sync, mock_telegram):
    mock_load.return_value = [
        BucketTarget(name="b1", dest_path="/backup/b1"),
        BucketTarget(name="b2", dest_path="/backup/b2"),
    ]
    mock_sync.side_effect = [
        BucketResult(name="b1", success=True, duration_seconds=1.0, error=None),
        BucketResult(name="b2", success=False, duration_seconds=1.0, error="boom"),
    ]
    mock_telegram.return_value = True

    assert _run_main() == 1
    mock_telegram.assert_called_once()


@patch("src.s3_backup.main.send_telegram_message")
@patch("src.s3_backup.main.load_bucket_targets")
def test_main_exit_code_zero_buckets(mock_load, mock_telegram):
    mock_load.return_value = []

    assert _run_main() == 1
    mock_telegram.assert_not_called()


@patch("src.s3_backup.main.send_telegram_message")
@patch("src.s3_backup.main.sync_bucket")
@patch("src.s3_backup.main.load_bucket_targets")
def test_main_isolates_unexpected_exception_from_sync_bucket(
    mock_load, mock_sync, mock_telegram
):
    mock_load.return_value = [
        BucketTarget(name="b1", dest_path="/backup/b1"),
        BucketTarget(name="b2", dest_path="/backup/b2"),
    ]
    mock_sync.side_effect = [
        RuntimeError("unexpected bug"),
        BucketResult(name="b2", success=True, duration_seconds=1.0, error=None),
    ]
    mock_telegram.return_value = True

    assert _run_main() == 1
    assert mock_sync.call_count == 2
    mock_telegram.assert_called_once()


@patch("src.s3_backup.main.send_telegram_message")
@patch("src.s3_backup.main.sync_bucket")
@patch("src.s3_backup.main.load_bucket_targets")
def test_main_telegram_failure_does_not_change_exit_code(
    mock_load, mock_sync, mock_telegram
):
    mock_load.return_value = [BucketTarget(name="b1", dest_path="/backup/b1")]
    mock_sync.return_value = BucketResult(
        name="b1", success=True, duration_seconds=1.0, error=None
    )
    mock_telegram.return_value = False

    assert _run_main() == 0
