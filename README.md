# SimpleBank API
Built with Django, [Django Ninja](https://django-ninja.dev/) and Pydantic.
Package/env management via [uv](https://docs.astral.sh/uv/) v=0.9.7 (Homebrew 2025-10-30)

## Quickstart

### Option A — everything in Docker (recommended)

One script spins up Postgres + the web container, applies migrations, and creates a local superuser:

```bash
scripts/docker-up.sh
```

Once it's up:
- API: http://localhost:8000/api/health
- Admin: http://localhost:8000/admin/

Tear down (removes containers + volumes):

```bash
scripts/docker-up.sh --down
```

### Option B — Postgres in Docker, server in your terminal

For day-to-day development: only Postgres runs in Docker, so you get hot-reload and a normal `uv run manage.py ...` workflow. The script starts the DB, applies migrations, and creates a local superuser:

```bash
scripts/docker-up-dev.sh
uv run manage.py runserver
```

Tear down (removes the DB container + volume):

```bash
scripts/docker-up-dev.sh --down
```

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [trivy](https://trivy.dev/) (for the local pre-commit vulnerability scan). use `brew install trivy` for macos, or see docs

## Setup

```bash
uv venv
source .venv/bin/activate
uv sync
cp envs/local.env .env   # or use envs/for_your_environment.env
uv run manage.py migrate
```

### Git hooks

```bash
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
uv run pre-commit run --all-files   # run check manually when you want it
```

## Running

```bash
uv run manage.py runserver
```

## Testing

```bash
uv run pytest
uv run pytest tests/test_smoke.py::test_health_endpoint
```

## Linting & type-checking

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

## Settings

Settings are splited under `simplebank/settings/`:

- `components/config.py` = the `Settings` model (`pydantic-settings`) that reads and validates config from the environment.
- `components/common.py` = shared settings, sourced from `Settings`.
- `components/database.py` = builds `DATABASES` from `DATABASE_URL`.
- `components/security.py` = secure-cookie/HSTS/SSL-redirect settings, used in production.
- `environments/local.py` = local development (used by `manage.py`, `DEBUG=True` by default).
- `environments/prod.py` = production (used by `wsgi.py`/`asgi.py`); requires `ALLOWED_HOSTS`.

Configuration is read from environment variables (or a local `.env` file, see
`envs/local.env` and `envs/production.env`): `SECRET_KEY`, `DEBUG`,
`ALLOWED_HOSTS`, `DATABASE_URL`. `.env` is git-ignored and must never be
committed.

## Database & Docker

Postgres is run via Docker Compose. Docker files live under `docker/`;
`docker-compose.yml` configs for production/stage/test/local-dev differ by
filename postfix.

To run the project (or part of it) locally:

```bash
cp envs/local.env .env
cp docker/docker-compose.local_full.yml docker-compose.yml

docker compose up --build
```

To tear it down:

```bash
docker compose rm -v
```

`scripts/docker-up.sh` wraps this (plus migrations and a seeded local
superuser) for day-to-day use; `scripts/docker-up-dev.sh` does the same but
only for the `db` service, for running `manage.py runserver` locally.

### Other environments

Stage/test deployments build on the base compose file (`docker/docker-compose.yml`)
with an override:

```bash
cp envs/production.env .env
docker compose --project-directory . -f docker/docker-compose.yml -f docker/docker-compose.override_stage_test.yml config > docker-compose.yml
```

See `docker/` and `.github/workflows/` for how other environments are wired up.

## Security scanning

Dependency/filesystem vulnerabilities are scanned with [Trivy](https://trivy.dev/):

- Locally via the `trivy-fs` pre-commit hook.
- In CI via `.github/workflows/trivy.yml` on every push/PR to `main`.
