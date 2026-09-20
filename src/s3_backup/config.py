import os
from dataclasses import dataclass


@dataclass
class BucketTarget:
    """Represents a single S3 bucket to back up."""
    name: str
    dest_path: str


def load_bucket_targets(env: dict = None) -> list[BucketTarget]:
    """
    Load bucket targets from environment variables.

    Scans for env vars matching the pattern:
    - BACKUP_BUCKET_<N>_NAME=<bucket-name>
    - BACKUP_BUCKET_<N>_DEST=<local-path>

    Returns a list of BucketTarget objects in ascending order by N.
    Raises ValueError if a NAME has no matching DEST or vice versa.
    """
    if env is None:
        env = os.environ

    bucket_indices = set()
    names = {}
    dests = {}

    for key, value in env.items():
        if key.startswith("BACKUP_BUCKET_") and key.endswith("_NAME"):
            parts = key.split("_")
            if len(parts) == 4:
                try:
                    idx = int(parts[2])
                    bucket_indices.add(idx)
                    names[idx] = value
                except (ValueError, IndexError):
                    pass
        elif key.startswith("BACKUP_BUCKET_") and key.endswith("_DEST"):
            parts = key.split("_")
            if len(parts) == 4:
                try:
                    idx = int(parts[2])
                    bucket_indices.add(idx)
                    dests[idx] = value
                except (ValueError, IndexError):
                    pass

    for idx in bucket_indices:
        if idx not in names:
            raise ValueError(
                f"BACKUP_BUCKET_{idx}_DEST is defined but BACKUP_BUCKET_{idx}_NAME is missing"
            )
        if idx not in dests:
            raise ValueError(
                f"BACKUP_BUCKET_{idx}_NAME is defined but BACKUP_BUCKET_{idx}_DEST is missing"
            )

    targets = []
    for idx in sorted(bucket_indices):
        targets.append(BucketTarget(name=names[idx], dest_path=dests[idx]))

    return targets
