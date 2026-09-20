import os
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import time

from src.s3_backup.config import BucketTarget
from src.s3_backup.summary import BucketResult
from src.s3_backup.sync import sync_bucket


def test_sync_bucket_success(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is True
        assert result.error is None
        assert result.duration_seconds >= 0

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == [
            "aws",
            "s3",
            "sync",
            "s3://test-bucket",
            str(tmp_path),
        ]


def test_sync_bucket_never_passes_delete_flag(tmp_path):
    """Pull-only backup: --delete must never be part of the sync command."""
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        sync_bucket(target)

        cmd = mock_run.call_args[0][0]
        assert "--delete" not in cmd


def test_sync_bucket_creates_destination():
    target = BucketTarget(name="test-bucket", dest_path="/tmp/test-backup-new")

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        with patch("src.s3_backup.sync.os.makedirs") as mock_makedirs:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            sync_bucket(target)

            mock_makedirs.assert_called_once_with("/tmp/test-backup-new", exist_ok=True)


def test_sync_bucket_failure(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="aws", stderr="Access Denied"
        )

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is False
        assert "Access Denied" in result.error or "returncode" in result.error


def test_sync_bucket_os_error(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("Permission denied")

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is False
        assert "Permission denied" in result.error


def test_sync_bucket_measures_duration(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        with patch("src.s3_backup.sync.time.time") as mock_time:
            mock_time.side_effect = [100.0, 105.5]
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = sync_bucket(target)

            assert result.duration_seconds == 5.5


def test_sync_bucket_calls_subprocess_with_correct_args(tmp_path):
    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        sync_bucket(target)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["check"] is True
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True


def test_sync_bucket_counts_new_objects_and_bytes(tmp_path):
    """New objects downloaded this run are counted, with their real size on disk."""
    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))

    file_a = tmp_path / "a.txt"
    file_a.write_bytes(b"x" * 100)
    file_b = tmp_path / "b.txt"
    file_b.write_bytes(b"y" * 250)

    stdout = (
        f"download: s3://my-bucket/a.txt to {file_a}\n"
        f"download: s3://my-bucket/b.txt to {file_b}\n"
    )

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=stdout, stderr="")

        result = sync_bucket(target)

        assert result.objects_transferred == 2
        assert result.bytes_transferred == 350
        assert result.total_local_bytes == 350


def test_sync_bucket_shrink_guard_skips_sync_when_destination_looks_wiped(tmp_path):
    """
    If a previous run recorded e.g. 1GB on disk and the destination now looks
    almost empty, the sync must be refused instead of quietly "backing up"
    into what is probably an unmounted/wrong volume.
    """
    from src.s3_backup import backup_state

    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))
    backup_state.write_state(str(tmp_path), 1_000_000_000)

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        result = sync_bucket(target)

        mock_run.assert_not_called()
        assert result.success is False
        assert "mount" in result.error.lower()


def test_sync_bucket_shrink_guard_allows_normal_growth(tmp_path):
    """A destination that's still close to its previous size syncs normally."""
    from src.s3_backup import backup_state

    existing = tmp_path / "existing.txt"
    existing.write_bytes(b"z" * 900)
    backup_state.write_state(str(tmp_path), 1000)

    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = sync_bucket(target)

        mock_run.assert_called_once()
        assert result.success is True
