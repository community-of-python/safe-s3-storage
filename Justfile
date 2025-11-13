default: install lint test

down:
    docker compose down --remove-orphans

sh:
    docker compose run --service-ports application bash

test *args: down && down
    docker compose run application uv run --no-sync pytest {{ args }}

build:
    docker compose build application

install:
    uv lock --upgrade
    uv sync --frozen --all-groups

lint:
    uv run --group lint auto-typing-final .
    uv run --group lint ruff check
    uv run --group lint ruff format
    uv run --group lint mypy .

lint-ci:
    uv run --group lint auto-typing-final .
    uv run --group lint ruff format --check
    uv run --group lint ruff check --no-fix
    uv run --group lint mypy .

publish:
    rm -rf dist
    uv version $GITHUB_REF_NAME
    uv build
    uv publish --token $PYPI_TOKEN
