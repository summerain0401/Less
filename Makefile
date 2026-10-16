.PHONY: setup start stop status dev test api-types build scheduler-install scheduler-status scheduler-uninstall

setup:
	uv sync --locked
	cd frontend && npm ci

start:
	.venv/bin/python -m less.services start

stop:
	.venv/bin/python -m less.services stop

status:
	.venv/bin/python -m less.services status

dev:
	.venv/bin/python -m less.services dev

scheduler-install: start

scheduler-status: status

scheduler-uninstall: stop

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
