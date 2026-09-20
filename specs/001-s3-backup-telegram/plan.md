# Implementation Plan: Daily S3 Backup with Telegram Notification

**Branch**: `001-s3-backup-telegram` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-s3-backup-telegram/spec.md`

## Summary

A single Python orchestration script reads N bucket→local-path mappings from environment
variables, runs `aws s3 sync` (subprocess) per bucket with per-bucket try/except isolation, builds
one run summary, and sends it as a single Telegram message. The script runs inside a Docker
container under `supercronic` on a configurable daily cron schedule, with structured logging to
file + stdout. AWS/Telegram credentials come only from environment variables (`.env`, not baked
into the image).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: AWS CLI v2 (`aws s3 sync` via subprocess — no boto3 S3 transfer
reimplementation, per spec), `requests` (Telegram Bot API call), `PyYAML` not needed (config is
env-based per user requirement), stdlib `logging`, `subprocess`, `os`, `dataclasses`.

**Storage**: Local filesystem (bind-mounted host volume / NAS mount) as backup destination; no
database.

**Testing**: `pytest` for the orchestration logic (bucket list parsing, summary building, exit
code logic), with `aws s3 sync` and Telegram calls mocked via `unittest.mock`. No live AWS/Telegram
calls in automated tests.

**Target Platform**: Linux container (Docker), amd64/arm64.

**Project Type**: Single containerized CLI/batch job (no web/mobile split).

**Performance Goals**: Not latency-sensitive; one run/day. Bounded by network transfer + S3 API
throughput, not by the orchestrator itself.

**Constraints**: Must not hardcode credentials or bucket names anywhere in source; must isolate
per-bucket failures; must send exactly one Telegram message per run; must exit non-zero on any
bucket failure; scheduler must handle signals correctly (supercronic, not vixie-cron).

**Scale/Scope**: N buckets, N defined purely by `.env` content — no fixed upper bound in code.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No project constitution exists yet for this repository (fresh single-feature repo — `/speckit.constitution`
was not run since this is a one-off infrastructure script project, not a multi-feature product).
Applying the global engineering rules from `CLAUDE.md` as the gate instead:

- No dead code / no speculative abstraction → single script, no framework, no plugin system. PASS.
- Credentials never hardcoded → all secrets via env vars, `.env` git-ignored, README documents
  required vars only. PASS.
- Real error handling, no swallowed exceptions → per-bucket try/except captures and logs the
  actual exception; nothing is silently ignored. PASS.
- Least-privilege AWS access → IAM policy documented in README restricted to
  `s3:GetObject`+`s3:ListBucket` on the specific bucket ARNs. PASS.

No violations — Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-s3-backup-telegram/
├── plan.md              # This file
├── tasks.md             # Phase 2 output (/speckit-tasks)
└── (research.md / data-model.md / contracts/ omitted — no unresolved unknowns,
     no persistent data model beyond an in-memory run summary; quickstart lives in README.md)
```

### Source Code (repository root)

```text
backup-test/
├── src/
│   └── s3_backup/
│       ├── __init__.py
│       ├── main.py          # entrypoint: orchestrates the full run
│       ├── config.py        # reads BUCKET_* env vars into BucketTarget list
│       ├── sync.py          # runs `aws s3 sync` per bucket, captures result
│       ├── summary.py       # RunSummary dataclass + formatting for Telegram/log
│       ├── telegram.py      # sends the consolidated message via Bot API
│       └── logging_setup.py # configures file + stdout structured logging
├── tests/
│   ├── test_config.py
│   ├── test_sync.py
│   ├── test_summary.py
│   └── test_telegram.py
├── docker/
│   ├── Dockerfile
│   ├── crontab              # supercronic schedule (templated by entrypoint)
│   └── entrypoint.sh        # renders cron schedule from env, execs supercronic
├── .env.example
├── requirements.txt
└── README.md
```

**Structure Decision**: Single Python package (`src/s3_backup/`) — Option 1 (single project) from
the template, since this is one containerized batch job, not a web app or multi-platform product.
Docker-specific files are isolated under `docker/` to keep the Python package framework-agnostic
and independently testable with `pytest` outside the container.

## Complexity Tracking

*No violations — table intentionally empty.*
