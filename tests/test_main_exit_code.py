import pytest
from src.s3_backup.summary import BucketResult, RunSummary


def test_exit_code_all_success():
    """Test that exit code is 0 when all buckets succeed."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=True, duration_seconds=1.5),
    ]
    summary = RunSummary(results=results)

    exit_code = 0 if all(r.success for r in summary.results) else 1
    assert exit_code == 0


def test_exit_code_one_failure():
    """Test that exit code is 1 when at least one bucket fails."""
    results = [
        BucketResult("bucket-1", success=True, duration_seconds=1.0),
        BucketResult("bucket-2", success=False, duration_seconds=1.5, error="Failed"),
    ]
    summary = RunSummary(results=results)

    exit_code = 0 if all(r.success for r in summary.results) else 1
    assert exit_code == 1


def test_exit_code_all_failures():
    """Test that exit code is 1 when all buckets fail."""
    results = [
        BucketResult("bucket-1", success=False, duration_seconds=1.0, error="Failed 1"),
        BucketResult("bucket-2", success=False, duration_seconds=1.5, error="Failed 2"),
    ]
    summary = RunSummary(results=results)

    exit_code = 0 if all(r.success for r in summary.results) else 1
    assert exit_code == 1
