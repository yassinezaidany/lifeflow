#!/usr/bin/env bash
# One-time installation of LifeFlow on Linux / macOS.
#   ./setup.sh            standard install
#   ./setup.sh --demo     + demo accounts (demo / LifeFlow-demo1)
#   ./setup.sh --dev      + test / QA tools
set -euo pipefail
cd "$(dirname "$0")"
DEMO=0; DEV=0
for arg in "$@"; do case "$arg" in --demo) DEMO=1 ;; --dev) DEV=1 ;; esac; done

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }

step "Checking prerequisites"
PY=$(command -v python3.11 || command -v python3)
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
command -v docker >/dev/null || { echo "Docker is required"; exit 1; }

step "Virtual environment"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
[ "$DEV" = 1 ] && .venv/bin/pip install -r requirements-dev.txt -q

step "Configuration (.env)"
if [ ! -f .env ]; then
  SECRET=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(50))')
  sed "s/change-me-to-a-long-random-string/$SECRET/" .env.example > .env
  echo ".env created with a random SECRET_KEY"
fi

step "MySQL (Docker)"
docker compose up -d db
until [ "$(docker inspect -f '{{.State.Health.Status}}' lifeflow-mysql)" = "healthy" ]; do printf '.'; sleep 2; done; echo

step "Database"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed_templates
.venv/bin/python manage.py i18n compile
grep -q '^VAPID_PRIVATE_KEY=.\+' .env || .venv/bin/python manage.py generate_vapid_keys --write
[ "$DEMO" = 1 ] && .venv/bin/python manage.py seed_demo --reset

step "Installation check"
.venv/bin/python manage.py doctor || true
printf '\n\033[32mLifeFlow is installed.\033[0m Start it with ./start.sh (or ./start.sh --prod)\n'
