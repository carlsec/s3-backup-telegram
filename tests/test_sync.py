import threading
from unittest.mock import patch, MagicMock
import pytest
import time

from src.s3_backup.config import BucketTarget
from src.s3_backup.summary import BucketResult
from src.s3_backup import sync as sync_module
from src.s3_backup.sync import sync_bucket


class _FakePopen:
    """Minimal stand-in for subprocess.Popen streaming stdout line by line."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(line + "\n" for line in lines)
        self._returncode = returncode

    def wait(self):
        return self._returncode

    def kill(self):
        pass


class _HangingFakePopen:
    """Simulates a process whose stdout never yields until kill() is called."""

    def __init__(self):
        self._killed = threading.Event()
        self.stdout = self._stdout_gen()

    def _stdout_gen(self):
        self._killed.wait(timeout=5)
        return
        yield  # pragma: no cover - makes this a generator

    def kill(self):
        self._killed.set()

    def wait(self):
        self._killed.wait(timeout=5)
        return -9


def test_sync_bucket_success(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen([])

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is True
        assert result.error is None
        assert result.duration_seconds >= 0

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        assert call_args[0][0] == [
            "s5cmd",
            "sync",
            "s3://test-bucket/*",
            f"{tmp_path}/",
        ]


def test_sync_bucket_never_passes_delete_flag(tmp_path):
    """Pull-only backup: --delete must never be part of the sync command."""
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen([])

        sync_bucket(target)

        cmd = mock_popen.call_args[0][0]
        assert "--delete" not in cmd


def test_sync_bucket_creates_destination():
    target = BucketTarget(name="test-bucket", dest_path="/tmp/test-backup-new")

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        with patch("src.s3_backup.sync.os.makedirs") as mock_makedirs:
            mock_popen.return_value = _FakePopen([])

            sync_bucket(target)

            mock_makedirs.assert_called_once_with("/tmp/test-backup-new", exist_ok=True)


def test_sync_bucket_failure_on_nonzero_exit(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen(
            ['ERROR "cp s3://test-bucket/x x": AccessDenied'], returncode=1
        )

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is False
        assert "AccessDenied" in result.error


def test_sync_bucket_failure_detected_even_with_zero_exit_code(tmp_path):
    """
    Real s5cmd behavior: it can exit 0 even when the whole sync failed (e.g.
    invalid credentials) — an ERROR line must be treated as a failure
    regardless of the process's own exit code.
    """
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen(
            ['ERROR "sync s3://test-bucket/* /backup/": InvalidAccessKeyId: ...'],
            returncode=0,
        )

        result = sync_bucket(target)

        assert result.success is False
        assert "InvalidAccessKeyId" in result.error


def test_sync_bucket_os_error(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = OSError("s5cmd not found")

        result = sync_bucket(target)

        assert result.name == "test-bucket"
        assert result.success is False
        assert "s5cmd not found" in result.error


def test_sync_bucket_measures_duration(tmp_path):
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        with patch("src.s3_backup.sync.time.time") as mock_time:
            mock_time.side_effect = [100.0, 105.5]
            mock_popen.return_value = _FakePopen([])

            result = sync_bucket(target)

            assert result.duration_seconds == 5.5


def test_sync_bucket_counts_new_objects_and_bytes(tmp_path):
    """New objects downloaded this run are counted, with their real size on disk."""
    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))

    file_a = tmp_path / "a.txt"
    file_a.write_bytes(b"x" * 100)
    file_b = tmp_path / "b.txt"
    file_b.write_bytes(b"y" * 250)

    lines = [
        f"cp s3://my-bucket/a.txt {file_a}",
        f"cp s3://my-bucket/b.txt {file_b}",
    ]

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen(lines)

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

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        result = sync_bucket(target)

        mock_popen.assert_not_called()
        assert result.success is False
        assert "mount" in result.error.lower()


def test_sync_bucket_shrink_guard_allows_normal_growth(tmp_path):
    """A destination that's still close to its previous size syncs normally."""
    from src.s3_backup import backup_state

    existing = tmp_path / "existing.txt"
    existing.write_bytes(b"z" * 900)
    backup_state.write_state(str(tmp_path), 1000)

    target = BucketTarget(name="my-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _FakePopen([])

        result = sync_bucket(target)

        mock_popen.assert_called_once()
        assert result.success is True


def test_sync_bucket_watchdog_kills_hung_process(tmp_path, monkeypatch):
    """
    s5cmd has no built-in timeout and can hang forever (e.g. a stalled
    credential lookup). The watchdog must kill it and report a clear
    failure instead of blocking the whole run indefinitely.
    """
    monkeypatch.setattr(sync_module, "SYNC_TIMEOUT_SECONDS", 0.05)
    target = BucketTarget(name="test-bucket", dest_path=str(tmp_path))

    with patch("src.s3_backup.sync.subprocess.Popen") as mock_popen:
        mock_popen.return_value = _HangingFakePopen()

        started = time.time()
        result = sync_bucket(target)
        elapsed = time.time() - started

        assert result.success is False
        assert "timeout" in result.error.lower() or "timed" in result.error.lower() or "hang" in result.error.lower()
        assert elapsed < 3, "watchdog should kill the hung process well within a few seconds"
