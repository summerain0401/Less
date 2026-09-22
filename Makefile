.PHONY: setup dev test api-types build

setup:
	uv sync --locked
	cd frontend && npm ci

dev:
	.venv/bin/python scripts/dev.py

test:
	.venv/bin/pytest -q
	.venv/bin/ruff check backend tests scripts
	cd frontend && npm run build
	cd frontend && npm run test:e2e

api-types:
	.venv/bin/less openapi > openapi.json
	cd frontend && npm run generate:api

build:
	cd frontend && npm run build
