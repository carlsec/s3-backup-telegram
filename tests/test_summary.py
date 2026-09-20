from src.s3_backup.summary import BucketResult, RunSummary, human_readable_bytes


def test_run_summary_ok_count():
    """Test that ok_count correctly counts successful results."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=False, duration_seconds=2.0, error="Access denied"),
        BucketResult("bucket-3", success=True, duration_seconds=1.5),
    ]
    summary = RunSummary(results=results)

    assert summary.ok_count() == 2


def test_run_summary_failed_count():
    """Test that failed_count correctly counts failed results."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=False, duration_seconds=2.0, error="Access denied"),
        BucketResult("bucket-3", success=True, duration_seconds=1.5),
    ]
    summary = RunSummary(results=results)

    assert summary.failed_count() == 1


def test_run_summary_to_log_string():
    """Test log formatting includes summary and failures."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=False, duration_seconds=2.0, error="Access denied"),
    ]
    summary = RunSummary(results=results)
    log_str = summary.to_log_string()

    assert "OK: 1" in log_str
    assert "Failed: 1" in log_str
    assert "bucket-2" in log_str
    assert "Access denied" in log_str


def test_run_summary_to_telegram_message_with_failures():
    """Test Telegram message format with mixed successes/failures."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=False, duration_seconds=2.0, error="Access denied"),
        BucketResult("bucket-3", success=True, duration_seconds=1.5),
    ]
    summary = RunSummary(results=results)
    msg = summary.to_telegram_message()

    assert "OK: 2" in msg
    assert "Failed: 1" in msg
    assert "bucket-2" in msg
    assert "Access denied" in msg


def test_run_summary_to_telegram_message_all_ok():
    """Test Telegram message format when all buckets succeed."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=True, duration_seconds=2.0),
    ]
    summary = RunSummary(results=results)
    msg = summary.to_telegram_message()

    assert "OK: 2" in msg
    assert "Failed: 0" in msg
    assert "Failed buckets:" not in msg


def test_bucket_result_success():
    """Test BucketResult with success."""
    result = BucketResult("test-bucket", success=True, duration_seconds=5.5)

    assert result.name == "test-bucket"
    assert result.success is True
    assert result.duration_seconds == 5.5
    assert result.error is None


def test_bucket_result_failure():
    """Test BucketResult with failure."""
    result = BucketResult(
        "test-bucket",
        success=False,
        duration_seconds=1.2,
        error="Bucket not found",
    )

    assert result.name == "test-bucket"
    assert result.success is False
    assert result.error == "Bucket not found"


def test_human_readable_bytes():
    assert human_readable_bytes(0) == "0 B"
    assert human_readable_bytes(512) == "512 B"
    assert human_readable_bytes(2048) == "2.0 KB"
    assert human_readable_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_telegram_message_includes_new_objects_and_total():
    """Successful buckets report new objects/bytes this run and total on disk."""
    results = [
        BucketResult(
            "bucket-1",
            success=True,
            duration_seconds=1.0,
            objects_transferred=12,
            bytes_transferred=1024 * 1024,
            total_local_bytes=10 * 1024 * 1024,
        ),
    ]
    msg = RunSummary(results=results).to_telegram_message()

    assert "+12 new object(s)" in msg
    assert "1.0 MB" in msg
    assert "10.0 MB total on disk" in msg
