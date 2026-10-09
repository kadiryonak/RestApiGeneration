.PHONY: install lint format typecheck test test-integration check

install:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

typecheck:
	.venv/bin/mypy

# pytest exits with 5 when no tests are collected (true until the first module lands).
test:
	.venv/bin/pytest -m "not integration and not network" --cov --cov-report=term-missing; \
	status=$$?; [ $$status -eq 0 ] || [ $$status -eq 5 ]

test-integration:
	.venv/bin/pytest -m integration; \
	status=$$?; [ $$status -eq 0 ] || [ $$status -eq 5 ]

check: lint typecheck test
