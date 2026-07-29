#!/usr/bin/env bash
# Bootstrap the local dev DB (Postgres only, runserver is run manually).
#
# Usage:
#   scripts/docker-up-dev.sh          # (re)start
#   scripts/docker-up-dev.sh --down   # remove containers + volumes and stop

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

cp -f envs/local.env .env
cp -f docker/docker-compose.local_dev.yml docker-compose.yml

if [[ "${1:-}" == "--down" ]]; then
    docker compose down -v --remove-orphans
    exit 0
fi

docker compose up -d
sleep 3

set -a
source .env
set +a

uv run manage.py migrate
uv run manage.py createsuperuser --noinput || true
