#!/usr/bin/env bash
# Start LifeFlow (web + reminder scheduler) on Linux / macOS.
#   ./start.sh           development server on http://127.0.0.1:8000
#   ./start.sh --prod    Gunicorn, DEBUG off (put a TLS proxy in front, or USE_HTTPS=False for local use)
set -euo pipefail
cd "$(dirname "$0")"
PORT=${PORT:-8000}
mkdir -p logs
docker compose up -d db >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' lifeflow-mysql)" = "healthy" ]; do sleep 2; done

.venv/bin/python manage.py run_scheduler > logs/scheduler.out.log 2>&1 &
SCHEDULER=$!
trap 'kill $SCHEDULER 2>/dev/null || true' EXIT

if [ "${1:-}" = "--prod" ]; then
  export DJANGO_SETTINGS_MODULE=config.settings.prod DEBUG=False
  .venv/bin/python manage.py migrate --noinput
  .venv/bin/python manage.py collectstatic --noinput >/dev/null
  exec_cmd=(.venv/bin/gunicorn config.wsgi:application --bind "0.0.0.0:$PORT" --workers 3)
else
  exec_cmd=(.venv/bin/python manage.py runserver "127.0.0.1:$PORT")
fi
echo "LifeFlow → http://127.0.0.1:$PORT"
"${exec_cmd[@]}"
