---

description: "Task list for Daily S3 Backup with Telegram Notification"
---

# Tasks: Daily S3 Backup with Telegram Notification

**Input**: Design documents from `/specs/001-s3-backup-telegram/`

**Prerequisites**: plan.md, spec.md

**Tests**: Included — orchestration logic (config parsing, sync isolation, summary/exit code) is
correctness-critical and mockable without live AWS/Telegram calls, per plan.md Testing section.

**Organization**: Tasks are grouped by user story (US1–US4 from spec.md) to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Single project, per plan.md: `src/s3_backup/`, `tests/`, `docker/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create project structure per plan.md: `src/s3_backup/`, `tests/`, `docker/`
- [ ] T002 Create `requirements.txt` with `requests` (Telegram) and `pytest` (dev/test only)
- [ ] T003 [P] Create `.gitignore` covering `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
      local backup data dirs
- [ ] T004 [P] Create `.env.example` documenting every required env var: `AWS_ACCESS_KEY_ID`,
      `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
      `BACKUP_SCHEDULE_CRON`, `BACKUP_BUCKET_1_NAME`/`BACKUP_BUCKET_1_DEST` (and `_2`, `_3`, ...
      pattern) — placeholder/example values only, never real credentials

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented

- [ ] T005 Implement `src/s3_backup/logging_setup.py`: configure a logger that writes structured
      (timestamp, level, bucket, message) records to both stdout and a log file at a path from
      `BACKUP_LOG_FILE` (default `/var/log/s3-backup/backup.log`)
- [ ] T006 [P] Implement `src/s3_backup/config.py`: `BucketTarget` dataclass (`name`, `dest_path`)
      and a `load_bucket_targets(env) -> list[BucketTarget]` function that scans env vars matching
      `BACKUP_BUCKET_<N>_NAME` / `BACKUP_BUCKET_<N>_DEST` for arbitrary N (no fixed upper bound),
      raising a clear config error if a `_NAME` has no matching `_DEST` or vice versa
- [ ] T007 [P] Implement `src/s3_backup/summary.py`: `BucketResult` dataclass (`name`, `success`,
      `duration_seconds`, `error: str | None`) and `RunSummary` dataclass with a method to compute
      `ok_count`/`failed_count` and render both a log-friendly string and a Telegram-friendly
      message (bucket counts + per-failure name/error)
- [ ] T008 [P] Write `tests/test_config.py`: given env vars for 3 buckets (`BACKUP_BUCKET_1..3`),
      `load_bucket_targets` returns 3 `BucketTarget`s in order; given zero `BACKUP_BUCKET_*` vars,
      it returns an empty list; given a `_NAME` without a matching `_DEST`, it raises

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Scheduled incremental backup of all configured buckets (Priority: P1) 🎯 MVP

**Goal**: Sync N configured buckets to local/NAS paths incrementally via `aws s3 sync`.

**Independent Test**: Configure 2 buckets in `.env`, run `python -m s3_backup.main` once; verify
objects land under the configured local paths; run again and verify (from logs) no re-transfer of
unchanged objects.

### Tests for User Story 1

- [ ] T009 [P] [US1] Write `tests/test_sync.py`: `sync_bucket(target)` builds the correct
      `["aws", "s3", "sync", f"s3://{name}", dest_path]` command, invokes it via
      `subprocess.run` (mocked), creates `dest_path` first if missing, and returns a successful
      `BucketResult` with a measured `duration_seconds` when the subprocess exit code is 0

### Implementation for User Story 1

- [ ] T010 [US1] Implement `src/s3_backup/sync.py`: `sync_bucket(target: BucketTarget) ->
      BucketResult` — ensures `dest_path` exists (`os.makedirs(..., exist_ok=True)`), runs
      `aws s3 sync s3://<name> <dest_path> --only-show-errors` via `subprocess.run(..., check=True,
      capture_output=True, text=True)`, times the call, logs start/end per bucket via
      `logging_setup`
- [ ] T011 [US1] Implement `src/s3_backup/main.py` skeleton: load env (`python-dotenv` optional —
      read directly from `os.environ` since the container/host already provides `.env`), call
      `config.load_bucket_targets`, loop and call `sync.sync_bucket` for each target sequentially,
      collect `BucketResult`s into a list
- [ ] T012 [US1] In `main.py`, if `load_bucket_targets` returns an empty list, log a warning
      "no buckets configured" and exit with a non-zero code (per spec.md Edge Cases) before
      attempting any sync or notification

**Checkpoint**: User Story 1 is independently testable — buckets sync incrementally end-to-end.

---

## Phase 4: User Story 2 - Isolated failure handling per bucket (Priority: P1)

**Goal**: One bucket's failure must not stop the others, and must be recorded with its error.

**Independent Test**: Configure 3 buckets where one name is invalid; run the job; verify the other
2 succeed, the invalid one is recorded failed with its error, and process exit code is non-zero.

### Tests for User Story 2

- [ ] T013 [P] [US2] Extend `tests/test_sync.py`: when the mocked `subprocess.run` raises
      `subprocess.CalledProcessError` (or exits non-zero), `sync_bucket` catches it and returns a
      `BucketResult(success=False, error=<stderr/exception text>)` instead of raising
- [ ] T014 [P] [US2] Write `tests/test_main_exit_code.py`: given a list of `BucketResult`s with at
      least one `success=False`, the orchestrator's computed exit code is non-zero; given all
      `success=True`, exit code is 0

### Implementation for User Story 2

- [ ] T015 [US2] In `src/s3_backup/sync.py`, wrap the `subprocess.run` call in `sync_bucket` with
      try/except catching `subprocess.CalledProcessError` and `OSError`, logging the bucket name +
      error, and returning a failed `BucketResult` — never let one bucket's exception propagate out
      of `sync_bucket`
- [ ] T016 [US2] In `src/s3_backup/main.py`, wrap each per-bucket `sync.sync_bucket(target)` call in
      its own try/except as a second isolation layer (belt-and-suspenders per spec FR-003), so a
      bug in `sync_bucket` itself still can't abort the loop; append a failed `BucketResult` on
      unexpected exception
- [ ] T017 [US2] In `main.py`, after the loop, compute `exit_code = 0 if all(r.success for r in
      results) else 1` and use it as the process exit code (`sys.exit(exit_code)`) at the end of
      `main()`, after notification (US3) has been attempted

**Checkpoint**: User Stories 1 and 2 both work — isolated failures, correct exit codes.

---

## Phase 5: User Story 3 - Consolidated Telegram notification (Priority: P2)

**Goal**: Exactly one Telegram message per run summarizing OK/failed counts and errors.

**Independent Test**: Run with a mix of successes/failures against a mocked Telegram API call;
verify exactly one HTTP call is made with the correct summary text.

### Tests for User Story 3

- [ ] T018 [P] [US3] Write `tests/test_telegram.py`: `send_telegram_message(text)` performs exactly
      one `requests.post` to `https://api.telegram.org/bot<TOKEN>/sendMessage` with `chat_id` and
      `text` from env/args (mocked `requests.post`); on a non-200 response or `requests` exception,
      it logs the failure and returns `False` without raising
- [ ] T019 [P] [US3] Extend `tests/test_summary.py`: `RunSummary.to_telegram_message()` on 2
      OK / 1 failed renders text containing "2" OK-count, "1" failed-count, and the failing
      bucket's name + error string; on all-OK it renders no error detail section

### Implementation for User Story 3

- [ ] T020 [US3] Implement `src/s3_backup/telegram.py`: `send_telegram_message(text: str) -> bool`
      reading `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from env, POSTing to the Bot API with a
      timeout, catching `requests.RequestException` and non-2xx responses, logging failure, and
      returning `False` on any failure (never raises)
- [ ] T021 [US3] Implement `RunSummary.to_telegram_message()` in `src/s3_backup/summary.py` per
      T019's expected format
- [ ] T022 [US3] In `src/s3_backup/main.py`, after all buckets are processed, build the `RunSummary`
      from the collected `BucketResult`s, call `telegram.send_telegram_message(summary
      .to_telegram_message())` exactly once, and log (but do not let it change) the backup exit
      code if the Telegram call itself fails (per spec.md US3 acceptance scenario 3)

**Checkpoint**: All P1/P2 stories work together — backup runs, isolates failures, notifies once.

---

## Phase 6: User Story 4 - Scheduled unattended execution in Docker (Priority: P2)

**Goal**: One container runs the backup daily via supercronic at a configurable time, with clean
signal handling and logs visible via `docker logs`.

**Independent Test**: Build and start the container with `BACKUP_SCHEDULE_CRON` set a few minutes
ahead; verify the job fires automatically and output appears in `docker logs`; `docker stop` exits
cleanly.

### Implementation for User Story 4

- [ ] T023 [US4] Create `docker/Dockerfile`: base on `python:3.12-slim`, install AWS CLI v2
      (official installer, not `pip install awscli`, to match `aws s3 sync` behavior used in
      production), install `supercronic` (pinned version + checksum verification) from its GitHub
      release binary, `COPY` `src/` and `requirements.txt`, `pip install -r requirements.txt`,
      `COPY docker/entrypoint.sh` and set it executable, `ENTRYPOINT ["/entrypoint.sh"]`
- [ ] T024 [US4] Create `docker/crontab.template` with a single line placeholder:
      `__BACKUP_SCHEDULE_CRON__ python -m s3_backup.main >> /proc/1/fd/1 2>>/proc/1/fd/2`
- [ ] T025 [US4] Create `docker/entrypoint.sh`: `set -euo pipefail`; validate `BACKUP_SCHEDULE_CRON`
      is set (default to `"0 3 * * *"` — daily at 03:00 — if unset, per spec.md "configurable
      schedule"); `sed` the value into `docker/crontab.template` → `/etc/supercronic/crontab`;
      `exec supercronic /etc/supercronic/crontab` (exec, not a backgrounded process, so supercronic
      is PID 1 and receives `SIGTERM` directly from `docker stop`)
- [ ] T026 [US4] Add a `docker-compose.yml` (or documented `docker run` invocation in README)
      showing: `.env` file mount via `env_file`, a bind/NAS mount for each configured
      `BACKUP_BUCKET_<N>_DEST` path, and a mount for the log file directory

**Checkpoint**: Full system runs unattended in a container with daily scheduling.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T027 [P] Write `README.md`: env var reference table, `.env.example` usage, how to run
      locally (`pip install -r requirements.txt && python -m s3_backup.main`), how to build/run the
      Docker container, and the **recommended read-only IAM policy** (JSON) scoped to
      `s3:GetObject` + `s3:ListBucket` on the specific bucket ARNs used for backup (per spec.md
      FR-010) — explicitly note credentials must never be committed to the repo
- [ ] T028 [P] Add `src/s3_backup/__init__.py` package marker and ensure `python -m s3_backup.main`
      works as the documented entrypoint
- [ ] T029 Run the full `pytest` suite (all of `tests/`) and fix any failures surfaced across the
      integration of US1–US3
- [ ] T030 Manually validate the Independent Test steps for all 4 user stories end-to-end (real or
      throwaway AWS test buckets + a test Telegram bot), confirming SC-001 through SC-005 from
      spec.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (config/summary/logging
  are used by every story).
- **User Story 1 (Phase 3)**: Depends on Foundational only.
- **User Story 2 (Phase 4)**: Depends on Foundational + US1's `sync.py`/`main.py` skeleton (extends
  the same files) — implement after US1.
- **User Story 3 (Phase 5)**: Depends on Foundational + US1's `main.py` (adds the notification
  call at the end of the same orchestration loop) — implement after US1, can run in parallel with
  US2 conceptually but touches `main.py` too, so sequence after US2 to avoid merge churn.
- **User Story 4 (Phase 6)**: Depends on US1–US3 being complete (it packages the working script);
  independent of their internals otherwise — could be built in parallel by someone else.
- **Polish (Phase 7)**: Depends on all desired stories being complete.

### Parallel Opportunities

- T003, T004 in parallel (Setup).
- T006, T007, T008 in parallel (Foundational — different files).
- T009 can be written while T005–T008 are in progress (different file).
- T013, T014 in parallel (US2 tests).
- T018, T019 in parallel (US3 tests).
- Phase 6 (Docker) can be developed in parallel with Phases 4–5 by a second contributor, since it
  only depends on US1's module layout existing, not on US2/US3 logic — but final `T029`/`T030`
  validation must wait for everything.
- T027, T028 in parallel (Polish).

---

## Implementation Strategy

### MVP First

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: incremental sync works end-to-end for N buckets from `.env`.
3. This alone is a usable local backup tool (manually invoked).

### Incremental Delivery

1. Foundation → US1 (backup works) → US2 (resilient to per-bucket failure) → US3 (notified) → US4
   (unattended in Docker) → Polish.
2. Each story adds value without breaking the previous one; US1+US2+US3 together fully satisfy the
   spec's functional requirements even before Dockerization (US4) is done.
