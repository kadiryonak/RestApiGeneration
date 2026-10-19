.PHONY: install tools lint format typecheck test test-integration check

install:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

# Comparison tools, each in its own venv, built from the study clones at pinned commits
# (git clone https://github.com/schemathesis/schemathesis and .../HypothesisWorks/hypothesis).
SCHEMATHESIS_COMMIT = 4eeb7ebf9234e6b087ebf0a0e643e4eb39cffddc
HYPOTHESIS_COMMIT = ca2a4c6e3c6b979d9fbb5ef9db614885a736d2aa

tools:
	test "$$(git -C schemathesis rev-parse HEAD)" = "$(SCHEMATHESIS_COMMIT)"
	test "$$(git -C hypothesis rev-parse HEAD)" = "$(HYPOTHESIS_COMMIT)"
	uv venv --python 3.12 --allow-existing schemathesis/.venv
	uv pip install --python schemathesis/.venv/bin/python -e schemathesis
	uv venv --python 3.12 --allow-existing .venvs/hypothesis
	uv pip install --python .venvs/hypothesis/bin/python -e hypothesis/hypothesis \
		hypothesis-jsonschema==0.23.1 httpx==0.28.1 pytest==9.1.1

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
