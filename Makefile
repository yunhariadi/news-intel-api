.PHONY: help up down test lint fmt gate

help:
	@echo "make up    - docker compose up (postgres+pgvector, redis, api, worker)"
	@echo "make down  - stop the stack"
	@echo "make test  - pytest across packages/apps/tests"
	@echo "make lint  - ruff + mypy --strict"
	@echo "make fmt   - ruff format + autofix"
	@echo "make gate  - the Layer A reference gate (trending invariants)"

up:
	docker compose up --build

down:
	docker compose down

test:
	python3 -m pytest

lint:
	python3 -m ruff check apps packages
	python3 -m mypy packages

fmt:
	python3 -m ruff format apps packages
	python3 -m ruff check --fix apps packages

# The canonical Layer A gate. If this is red, the trending engine is wrong.
gate:
	python3 -m pytest -q packages/ranking/test_trending.py
