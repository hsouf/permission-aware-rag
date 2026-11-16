PY ?= .venv/bin/python
export PA_RAG_DATABASE_URL ?= postgresql://rag_gateway:rag_gateway_dev@localhost:5433/hr

.PHONY: install lint typecheck test test-adversarial test-integration db-up db-down demo serve check

install:
	python3 -m venv .venv && $(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest --cov --cov-report=term

test-adversarial:
	$(PY) -m pytest tests/adversarial -v

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose down -v

test-integration: db-up
	$(PY) -m pytest tests/integration -v

demo:
	$(PY) -m pa_rag.demo

serve:
	$(PY) -m uvicorn pa_rag.api.app:create_app --factory --reload

check: lint typecheck test
