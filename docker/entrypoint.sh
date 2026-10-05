#!/bin/sh
# LifeFlow container entrypoint.
#   web        → wait for MySQL, apply migrations, start Gunicorn
#   scheduler  → wait for MySQL, run the reminder loop
#   <other>    → run as a manage.py command (e.g. `createsuperuser`, `doctor`)
set -e

wait_for_db() {
  python - <<'PY'
import os, sys, time
import django
django.setup()
from django.db import connection
for attempt in range(60):
    try:
        connection.ensure_connection()
        sys.exit(0)
    except Exception as exc:
        print(f"waiting for database… ({exc.__class__.__name__})", flush=True)
        time.sleep(2)
sys.exit("database not reachable")
PY
}

case "$1" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" \
      --timeout 60 --access-logfile - --error-logfile -
    ;;
  scheduler)
    wait_for_db
    exec python manage.py run_scheduler --interval "${REMINDER_INTERVAL:-300}"
    ;;
  *)
    wait_for_db
    exec python manage.py "$@"
    ;;
esac
