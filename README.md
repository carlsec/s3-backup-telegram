# S3 Daily Backup with Telegram Notification

Backs up N S3 buckets to local/NAS storage once a day, incrementally, and sends one
consolidated Telegram message per run.

## How it works

- `src/s3_backup/main.py` orchestrates a run: read bucket config from env → `aws s3 sync` each
  bucket (subprocess) → isolate per-bucket failures → send one Telegram summary → exit non-zero
  if any bucket failed.
- Incremental transfer comes from `aws s3 sync` itself (only new/changed objects are copied on
  each run) — this project does not reimplement S3 diffing.
- **Pull-only, never destructive**: the sync command never passes `--delete` — if an object is
  removed from S3, the local copy is kept, never deleted. This is enforced in code
  (`src/s3_backup/sync.py`), asserted at runtime, and covered by a test that fails the suite if
  `--delete` is ever added back.
- Each run reports, per bucket: how many new objects/bytes were pulled **this run**, and the total
  size currently on disk for that bucket (see [Telegram message](#telegram-message-format) below).
- Inside Docker, [`supercronic`](https://github.com/aptible/supercronic) runs the job on a daily
  schedule, logging to stdout and forwarding signals correctly (unlike classic cron).

## Configuration (environment variables only)

Copy `.env.example` to `.env` and fill in real values. **Never commit `.env`.**

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | yes | Read-only IAM user key (see [IAM policy](#recommended-iam-policy) below) |
| `AWS_SECRET_ACCESS_KEY` | yes | Matching secret key |
| `AWS_DEFAULT_REGION` | yes | Region of the S3 buckets |
| `TELEGRAM_BOT_TOKEN` | yes | Existing bot's token |
| `TELEGRAM_CHAT_ID` | yes | Destination chat id for the summary message |
| `BACKUP_SCHEDULE_CRON` | no (default `0 3 * * *`) | Cron expression, evaluated in container time (UTC unless `TZ` is set) |
| `BACKUP_LOG_FILE` | no (default `/var/log/s3-backup/backup.log`) | Structured log file path (stdout is always used too) |
| `BACKUP_BUCKET_<N>_NAME` / `BACKUP_BUCKET_<N>_DEST` | at least one pair | Bucket name and local destination path, `N = 1, 2, 3, ...` — add or remove pairs to change what gets backed up, no code change needed |
| `BACKUP_SHRINK_GUARD_RATIO` | no (default `0.5`) | Safety threshold — see [Data safety](#data-safety) below |

## Telegram message format

One message per run, one line per bucket:

```
S3 Backup Summary
OK: 4 | Failed: 1

✅ lei-institute-prod-institute-storage: OK, +12 new object(s) (3.4 MB), 1.2 GB total on disk
✅ lei-prod-storage: OK, +0 new object(s) (0 B), 850.0 MB total on disk
✅ pub-lei-prod-storage: OK, +3 new object(s) (120.0 KB), 45.0 MB total on disk
✅ sicon-backups: OK, +1 new object(s) (2.1 MB), 9.8 GB total on disk
❌ pub-lei-institute-prod-institute-storage: FAILED - destination has ... — Sync SKIPPED to avoid backing up onto a lost mount.
```

"new object(s)" and their size are what changed **in this run only**; "total on disk" is the
cumulative size of everything backed up so far for that bucket, computed after each successful
sync.

## Data safety

This backup is designed so that **losing the host volume or NAS mount can never turn into silent
data loss or a corrupted backup**:

1. **Bind mounts only, never named Docker volumes.** `docker-compose.yml` maps real folders next
   to the project (e.g. `./backups/sicon-backups`) into the container — Docker Compose creates
   them on first run and resolves them relative to `docker-compose.yml`'s own location. Docker
   never owns or can delete that data — removing the container, the image, or running
   `docker compose down` (even with `-v`) does not touch it. Never change these to named volumes.
   If you later move the backup to a NAS/other drive, change the paths to point there (an absolute
   Windows path like `D:/backups/sicon-backups` or a mapped drive works the same way) — just keep
   them as plain folder paths, never `docker volume`.
2. **Never `--delete`.** The sync is pull-only: objects removed from S3 are never removed locally.
   This is asserted in code and covered by a test (`test_sync_bucket_never_passes_delete_flag`).
3. **Shrink guard.** Before every sync, the script compares the destination's current size on disk
   against the size it recorded after the *last successful* sync for that bucket (kept in a small
   `.s3_backup_state.json` file inside each destination folder). If the current size is less than
   `BACKUP_SHRINK_GUARD_RATIO` (default 50%) of the last known size, the sync for that bucket is
   **refused** and reported as a failure in the Telegram summary — instead of silently starting a
   fresh, near-empty "backup" into what is almost certainly an unmounted or misconfigured volume.
4. **Operational checklist before starting/restarting the container**:
   - Confirm the NAS/host paths in `docker-compose.yml` are actually mounted on the host
     (`mount | grep nas`, or however your NAS client reports it) before `docker compose up`.
   - Never point two different buckets' `_DEST` at the same host path — that would let one
     bucket's `total_local_bytes` reflect another bucket's data and can trip the shrink guard
     unpredictably.
   - If you deliberately need to reset the guard's baseline (e.g. real storage migration), delete
     that bucket's `.s3_backup_state.json` file — don't just lower `BACKUP_SHRINK_GUARD_RATIO`.

### Adding/removing buckets

Add a new numbered pair to `.env`:

```dotenv
BACKUP_BUCKET_3_NAME=my-third-bucket
BACKUP_BUCKET_3_DEST=/backup/bucket3
```

Mount `/backup/bucket3` to a real host/NAS path in `docker-compose.yml`, then restart the
container. Removing a bucket is the reverse: delete its pair and its volume mount.

## Running locally (without Docker)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)   # or use python-dotenv/direnv
python3 -m src.s3_backup.main
```

## Running with Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

By default, `docker-compose.yml` stores everything in `./backups/<bucket-name>` and `./logs` next
to this project — Docker Compose creates those folders automatically on first run. If you want the
data somewhere else (another drive, a NAS), edit the paths on the left of each `:` in
`docker-compose.yml`'s `volumes:` section — see [Data safety](#data-safety).

To stop cleanly: `docker compose down` (supercronic runs as PID 1 and shuts down promptly on
`SIGTERM`, finishing any in-flight sync first).

## Tests

```bash
python3 -m pytest tests/ -v
```

All AWS/Telegram calls are mocked — no live credentials or network access needed to run the suite.

## Recommended IAM policy

Create a dedicated IAM user (or role) used **only** for this backup, with programmatic access and
**no other permissions**. Restrict it to the exact buckets being backed up — replace
`YOUR-BUCKET-1`, `YOUR-BUCKET-2` below with the real bucket names from your `.env`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBackedUpBuckets",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET-1",
        "arn:aws:s3:::YOUR-BUCKET-2"
      ]
    },
    {
      "Sid": "ReadObjectsInBackedUpBuckets",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET-1/*",
        "arn:aws:s3:::YOUR-BUCKET-2/*"
      ]
    }
  ]
}
```

This grants exactly `s3:ListBucket` (needed for `aws s3 sync` to enumerate objects) and
`s3:GetObject` (needed to download them) — no write, delete, or bucket-management permissions, and
scoped only to the buckets actually used by this backup.

**Never commit AWS keys.** Provide them only via `.env` (git-ignored) or your orchestrator's
secret store. Rotate the key immediately if it is ever exposed (e.g. pasted in chat, committed, or
shared as a file).
