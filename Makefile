.PHONY: setup dev test api-types build backup
setup:
	uv sync --locked
	cd frontend && npm ci
	docker compose up -d --wait
	uv run alembic upgrade head
	uv run less seed

dev:
	.venv/bin/python scripts/dev.py

test:
	LESS_TEST_DATABASE_URL=postgresql+psycopg://less:less_local@127.0.0.1:55432/less .venv/bin/pytest -q
	.venv/bin/ruff check backend migrations tests scripts
	cd frontend && npm run build

api-types:
	.venv/bin/less openapi > openapi.json
	cd frontend && npm run generate:api

build:
	cd frontend && npm run build

backup:
	.venv/bin/less backup
