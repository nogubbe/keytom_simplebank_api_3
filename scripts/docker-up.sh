#!/usr/bin/env bash
# Bootstrap the local Docker dev environment (web + Postgres).
#
# Usage:
#   scripts/docker-up.sh          # (re)start
#   scripts/docker-up.sh --down   # remove containers + volumes and stop

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

cp -f envs/local.env .env
cp -f docker/docker-compose.local_full.yml docker-compose.yml

if [[ "${1:-}" == "--down" ]]; then
    docker compose down -v --remove-orphans
    exit 0
fi

docker compose up -d --build
sleep 5

docker compose exec -T web uv run manage.py migrate
docker compose exec -T web uv run manage.py createsuperuser --noinput || true
