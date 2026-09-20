from dataclasses import dataclass, field
from datetime import datetime, UTC


def human_readable_bytes(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


@dataclass
class BucketResult:
    """Result of syncing a single bucket."""
    name: str
    success: bool
    duration_seconds: float
    error: str | None = None
    objects_transferred: int = 0
    bytes_transferred: int = 0
    total_local_bytes: int = 0


@dataclass
class RunSummary:
    """Summary of a complete backup run."""
    results: list[BucketResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def ok_count(self) -> int:
        """Count of successfully synced buckets."""
        return sum(1 for r in self.results if r.success)

    def failed_count(self) -> int:
        """Count of failed bucket syncs."""
        return sum(1 for r in self.results if not r.success)

    def _bucket_line(self, r: BucketResult) -> str:
        if r.success:
            return (
                f"{r.name}: OK, +{r.objects_transferred} new object(s) "
                f"({human_readable_bytes(r.bytes_transferred)}), "
                f"{human_readable_bytes(r.total_local_bytes)} total on disk"
            )
        return f"{r.name}: FAILED - {r.error}"

    def to_log_string(self) -> str:
        """Format the summary for logging."""
        lines = [
            f"Run Summary ({self.timestamp.isoformat()})",
            f"OK: {self.ok_count()}, Failed: {self.failed_count()}",
        ]
        for r in self.results:
            lines.append(f"  - {self._bucket_line(r)}")
        return "\n".join(lines)

    def to_telegram_message(self) -> str:
        """Format the summary for Telegram notification, one line per bucket."""
        lines = [
            "S3 Backup Summary",
            f"OK: {self.ok_count()} | Failed: {self.failed_count()}",
            "",
        ]
        for r in self.results:
            prefix = "✅" if r.success else "❌"
            lines.append(f"{prefix} {self._bucket_line(r)}")
        return "\n".join(lines)
