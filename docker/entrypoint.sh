#!/bin/sh
set -eu

BACKUP_SCHEDULE_CRON="${BACKUP_SCHEDULE_CRON:-0 3 * * *}"

CRONTAB_PATH=/app/docker/crontab.rendered
sed "s#__BACKUP_SCHEDULE_CRON__#${BACKUP_SCHEDULE_CRON}#" \
    /app/docker/crontab.template > "$CRONTAB_PATH"

echo "Scheduled backup: '${BACKUP_SCHEDULE_CRON}'"

# exec replaces this shell so supercronic runs as PID 1 and receives
# signals (SIGTERM from `docker stop`) directly instead of a wrapper
# process swallowing them.
exec supercronic "$CRONTAB_PATH"
