# Feature Specification: Daily S3 Backup with Telegram Notification

**Feature Branch**: `001-s3-backup-telegram`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "Crie um sistema de backup diário para N buckets S3, com notificação no Telegram. Fonte: N buckets S3, lista via config externa (sem hardcode). Destino: storage local (volume/NAS). Execução: container Docker com supercronic, frequência diária horário configurável. Notificação: uma mensagem consolidada ao Telegram ao final da execução. Script Python único orquestra tudo, lendo buckets de .env. Sync via `aws s3 sync` (subprocess) para aproveitar comportamento incremental. Falha em um bucket não interrompe os demais. Resumo final com OK/falhas enviado ao Telegram. Logging estruturado em arquivo + stdout. Credenciais só via env vars. Exit code != 0 se algum bucket falhar. Credenciais AWS de IAM read-only (GetObject + ListBucket) restrito aos buckets do backup."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scheduled incremental backup of all configured buckets (Priority: P1)

As the operator, I configure a list of N S3 buckets and their local destination paths, and the
system automatically syncs each bucket to local/NAS storage once a day, incrementally (only
new/changed objects are transferred on subsequent runs).

**Why this priority**: This is the core value of the feature — without it there is no backup at all.

**Independent Test**: Configure two buckets in `.env`, run the orchestration script once manually.
Verify both buckets' objects appear under their configured local paths. Run it a second time and
verify (via `aws s3 sync` output/logs) that only changed objects are transferred, not a full
re-copy.

**Acceptance Scenarios**:

1. **Given** a `.env` listing 3 buckets with valid read-only AWS credentials, **When** the daily
   job runs, **Then** all 3 buckets are synced to their configured local destination paths.
2. **Given** a bucket already backed up once with no new objects added, **When** the job runs
   again, **Then** `aws s3 sync` transfers zero new objects (incremental behavior), and this is
   reflected in the per-bucket log/duration.
3. **Given** the operator adds a 4th bucket to `.env` and restarts the container, **When** the next
   scheduled run happens, **Then** the 4th bucket is also backed up — with no code change.

---

### User Story 2 - Isolated failure handling per bucket (Priority: P1)

As the operator, if one bucket fails to sync (e.g. access denied, bucket doesn't exist, network
error), the other buckets must still be processed, and I must be able to see exactly which
bucket(s) failed and why.

**Why this priority**: A single misconfigured bucket must not silently take down backups for every
other bucket — this is a core reliability requirement called out explicitly by the user.

**Independent Test**: Configure 3 buckets where one has an invalid/nonexistent name. Run the job.
Verify the 2 valid buckets are still synced successfully, the invalid one is recorded as failed
with its error message, and the process exit code is non-zero.

**Acceptance Scenarios**:

1. **Given** 3 configured buckets where bucket B does not exist, **When** the job runs, **Then**
   buckets A and C are synced successfully, bucket B is recorded as failed with an error message,
   and the script exits with a non-zero exit code.
2. **Given** all configured buckets sync successfully, **When** the job completes, **Then** the
   script exits with code 0.

---

### User Story 3 - Consolidated Telegram notification (Priority: P2)

As the operator, I receive exactly one Telegram message per run summarizing the outcome (counts of
OK/failed buckets, and the error for each failure), instead of being spammed with one message per
bucket.

**Why this priority**: Operability — without this, failures could go unnoticed, but it's secondary
to the backup itself actually working.

**Independent Test**: Run the job with a mix of successful and failing buckets against a real (or
test) Telegram bot/chat. Verify exactly one message arrives, containing correct OK/fail counts and
per-failure error detail.

**Acceptance Scenarios**:

1. **Given** a run with 2 successes and 1 failure, **When** the run completes, **Then** exactly one
   Telegram message is sent containing "2 OK", "1 failed", and the failing bucket's name + error.
2. **Given** a run with all buckets successful, **When** the run completes, **Then** one Telegram
   message is sent summarizing success with no error details.
3. **Given** the Telegram API is unreachable, **When** the run completes, **Then** the backup
   result itself (success/failure per bucket, exit code) is unaffected — the notification failure
   is logged but does not mask or override the backup outcome.

---

### User Story 4 - Scheduled unattended execution in Docker (Priority: P2)

As the operator, I deploy one Docker container that runs the backup automatically every day at a
configurable time, without an external scheduler, and its logs are visible via `docker logs`.

**Why this priority**: Required for this to run unattended in production; without it, the script
would need to be triggered manually or by external infrastructure the user explicitly wants to
avoid.

**Independent Test**: Build and start the container with a schedule set a few minutes in the
future. Verify the job fires automatically at that time and its output appears in `docker logs`.

**Acceptance Scenarios**:

1. **Given** a container started with `BACKUP_SCHEDULE_CRON` set, **When** that time is reached,
   **Then** the backup job runs automatically and its output is visible via `docker logs`.
2. **Given** the container receives a stop signal (`docker stop`), **When** the signal arrives,
   **Then** the scheduler and any in-flight job shut down cleanly (no orphaned/zombie processes).

---

### Edge Cases

- A bucket listed in config is empty → sync succeeds trivially, reported as OK with 0 objects.
- Local destination path does not exist yet → created automatically before sync.
- Local destination volume is full or unwritable → sync for that bucket fails, isolated per US2,
  reported as a failure with the underlying error.
- `.env` defines zero buckets → job logs a warning and exits non-zero (nothing to back up is
  treated as a misconfiguration, not a silent no-op).
- Duplicate bucket entries in config → each is processed independently as configured (no dedup
  magic); if this produces confusing double-counting the log makes it visible.
- AWS credentials invalid/expired → every bucket fails; summary and Telegram message clearly show
  an auth-related error rather than a generic failure.
- Telegram credentials missing/invalid → the run still completes and exit code still reflects
  backup success/failure; the notification failure itself is logged.
- A sync exceeds the time available before the next scheduled run → out of scope for v1 (assumed
  daily volume fits within the interval); no overlap/locking mechanism required beyond what
  `supercronic` itself provides.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST read the list of buckets to back up (bucket name + local destination
  path) from environment variables (`.env`), supporting an arbitrary number N of buckets, without
  any code change required to add or remove a bucket.
- **FR-002**: The system MUST sync each configured bucket to its local destination path using the
  AWS CLI's `aws s3 sync`, invoked as a subprocess, to get incremental (only new/changed objects)
  transfer behavior.
- **FR-003**: A failure syncing one bucket MUST NOT prevent the remaining configured buckets from
  being processed.
- **FR-004**: For each bucket, the system MUST record success/failure, duration, and — on
  failure — the error detail.
- **FR-005**: At the end of a run, the system MUST send exactly one Telegram message summarizing
  the run: count of successful buckets, count of failed buckets, and the error for each failed
  bucket.
- **FR-006**: The system MUST log structured events to both a log file and stdout.
- **FR-007**: All credentials (AWS access key/secret, Telegram bot token/chat id) MUST be supplied
  only via environment variables — never hardcoded in source or config files committed to the
  repository.
- **FR-008**: The process MUST exit with a non-zero exit code if any configured bucket failed to
  sync, and exit code 0 only if all buckets succeeded.
- **FR-009**: The backup job MUST run automatically once per day inside a Docker container, at a
  time configurable via environment variable, using `supercronic` as the in-container scheduler
  (not classic cron), so job output streams to the container's stdout and OS signals are handled
  correctly.
- **FR-010**: The AWS credentials used MUST belong to an IAM principal restricted to read-only
  access (`s3:GetObject`, `s3:ListBucket`) scoped to only the buckets used for this backup; the
  recommended IAM policy MUST be documented for the operator to apply (this system does not create
  IAM resources itself).

### Key Entities

- **Bucket backup target**: one configured S3 bucket paired with a local destination directory —
  the unit of work for a single sync.
- **Run summary**: the aggregate result of one full execution — list of per-bucket outcomes
  (success/failure, duration, error if any), overall counts, and timestamp — used to build the
  Telegram message and the exit code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding or removing a bucket from the backup set requires only an edit to `.env` and a
  container restart — zero source code changes.
- **SC-002**: When re-run with no new objects in any bucket, a run transfers 0 bytes/objects across
  all buckets (true incremental behavior), verifiable from the sync logs.
- **SC-003**: In a run where 1 of N configured buckets fails, the other N-1 still complete
  successfully, and this is reflected correctly in both the logs and the Telegram summary.
- **SC-004**: Every run produces exactly one Telegram message, never zero (silent failure) and
  never more than one (message-per-bucket spam).
- **SC-005**: The backup runs unattended daily without any external scheduler or manual trigger,
  confirmed by log entries appearing at the configured time across at least 2 consecutive days.

## Assumptions

- The destination is a local filesystem path mounted into the container (bind mount or NAS mount
  already present on the host) — the system does not manage mounting the NAS itself.
- One daily run per bucket is sufficient; sub-daily scheduling is out of scope for v1 but the cron
  expression is configurable enough to support it later.
- A single existing Telegram bot (token) and a single destination chat id are used — multi-chat
  fan-out notification is out of scope.
- The AWS CLI (`awscli`) is available in the container image; the system does not reimplement S3
  transfer logic itself.
- Retention/rotation of old local backups (e.g. deleting backups older than N days) is out of scope
  for v1 — `aws s3 sync` naturally mirrors the bucket's current state without pruning history.
- Buckets are all in a region reachable with a single set of AWS credentials/region configuration
  (no per-bucket credential overrides needed).
