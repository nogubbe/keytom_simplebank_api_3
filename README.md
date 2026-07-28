# keytom_simplebank_api_3

brew install trivy
uv venv
uv run pre-commit install
source .venv/bin/activate

uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
uv run pre-commit run --all-files
