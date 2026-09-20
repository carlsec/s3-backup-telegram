import pytest
from src.s3_backup.config import BucketTarget, load_bucket_targets


def test_load_bucket_targets_three_buckets():
    """Test loading 3 buckets from env vars."""
    env = {
        "BACKUP_BUCKET_1_NAME": "bucket-1",
        "BACKUP_BUCKET_1_DEST": "/backup/1",
        "BACKUP_BUCKET_2_NAME": "bucket-2",
        "BACKUP_BUCKET_2_DEST": "/backup/2",
        "BACKUP_BUCKET_3_NAME": "bucket-3",
        "BACKUP_BUCKET_3_DEST": "/backup/3",
    }

    targets = load_bucket_targets(env)

    assert len(targets) == 3
    assert targets[0] == BucketTarget("bucket-1", "/backup/1")
    assert targets[1] == BucketTarget("bucket-2", "/backup/2")
    assert targets[2] == BucketTarget("bucket-3", "/backup/3")


def test_load_bucket_targets_empty():
    """Test loading when no buckets are configured."""
    env = {}
    targets = load_bucket_targets(env)
    assert targets == []


def test_load_bucket_targets_name_without_dest():
    """Test that missing DEST for a NAME raises ValueError."""
    env = {
        "BACKUP_BUCKET_1_NAME": "bucket-1",
        "BACKUP_BUCKET_1_DEST": "/backup/1",
        "BACKUP_BUCKET_2_NAME": "bucket-2",
    }

    with pytest.raises(ValueError) as exc_info:
        load_bucket_targets(env)

    assert "BACKUP_BUCKET_2_DEST" in str(exc_info.value)


def test_load_bucket_targets_dest_without_name():
    """Test that missing NAME for a DEST raises ValueError."""
    env = {
        "BACKUP_BUCKET_1_NAME": "bucket-1",
        "BACKUP_BUCKET_1_DEST": "/backup/1",
        "BACKUP_BUCKET_2_DEST": "/backup/2",
    }

    with pytest.raises(ValueError) as exc_info:
        load_bucket_targets(env)

    assert "BACKUP_BUCKET_2_NAME" in str(exc_info.value)


def test_load_bucket_targets_ordered():
    """Test that buckets are returned in ascending order by N."""
    env = {
        "BACKUP_BUCKET_3_NAME": "bucket-3",
        "BACKUP_BUCKET_3_DEST": "/backup/3",
        "BACKUP_BUCKET_1_NAME": "bucket-1",
        "BACKUP_BUCKET_1_DEST": "/backup/1",
        "BACKUP_BUCKET_2_NAME": "bucket-2",
        "BACKUP_BUCKET_2_DEST": "/backup/2",
    }

    targets = load_bucket_targets(env)

    assert len(targets) == 3
    assert targets[0].name == "bucket-1"
    assert targets[1].name == "bucket-2"
    assert targets[2].name == "bucket-3"
