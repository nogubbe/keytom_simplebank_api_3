#!/usr/bin/env bash
# Bootstrap the local Docker dev environment (web + Postgres).
#
# Usage:
#   scripts/docker-up.sh          # start (build if needed), keep existing data
#   scripts/docker-up.sh --reset  # wipe containers + volumes first (drops the DB!)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "${1:-}" == "--reset" ]]; then
    echo "==> Removing containers and volumes (this drops the Postgres data)..."
    docker compose down -v --remove-orphans
fi

if [[ ! -f .env ]]; then
    echo "==> No .env found, copying envs/local.env..."
    cp envs/local.env .env
fi

if [[ ! -f docker-compose.yml ]]; then
    echo "==> No docker-compose.yml found, copying docker/docker-compose.local.yml..."
    cp docker/docker-compose.local.yml docker-compose.yml
fi

echo "==> Building and starting services..."
docker compose up -d --build

echo "==> Waiting for web to become healthy..."
timeout=60
until docker compose exec -T web python manage.py check >/dev/null 2>&1; do
    ((timeout -= 2)) || true
    if ((timeout <= 0)); then
        echo "web did not become ready in time" >&2
        docker compose logs web >&2
        exit 1
    fi
    sleep 2
done

echo "==> Ensuring local superuser exists..."
err_log="$(mktemp)"
trap 'rm -f "$err_log"' EXIT
if docker compose exec -T web python manage.py createsuperuser --noinput 2>"$err_log"; then
    echo "    created ${DJANGO_SUPERUSER_USERNAME:-admin}"
elif grep -q 'already taken' "$err_log"; then
    echo "    ${DJANGO_SUPERUSER_USERNAME:-admin} already exists, skipping"
else
    cat "$err_log" >&2
    exit 1
fi

echo "==> Ready. API: http://localhost:8000/api/health  Admin: http://localhost:8000/admin/"
