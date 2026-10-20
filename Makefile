.PHONY: install tools lint format typecheck test test-integration check

install:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

# Comparison tools, each in its own environment: Schemathesis and Hypothesis from the study
# clones at pinned commits, EvoMaster from its release jar (checksum-verified).
SCHEMATHESIS_COMMIT = 4eeb7ebf9234e6b087ebf0a0e643e4eb39cffddc
HYPOTHESIS_COMMIT = ca2a4c6e3c6b979d9fbb5ef9db614885a736d2aa
EVOMASTER_VERSION = 6.2.0
EVOMASTER_SHA256 = 93f9c4a0de88b01395d2a1009776aa739973e9f64343778d2fd49c212fd17915
EVOMASTER_JAR = .tools/evomaster/$(EVOMASTER_VERSION)/evomaster.jar

tools:
	test "$$(git -C schemathesis rev-parse HEAD)" = "$(SCHEMATHESIS_COMMIT)"
	test "$$(git -C hypothesis rev-parse HEAD)" = "$(HYPOTHESIS_COMMIT)"
	uv venv --python 3.12 --allow-existing schemathesis/.venv
	uv pip install --python schemathesis/.venv/bin/python -e schemathesis
	uv venv --python 3.12 --allow-existing .venvs/hypothesis
	uv pip install --python .venvs/hypothesis/bin/python -e hypothesis/hypothesis \
		hypothesis-jsonschema==0.23.1 httpx==0.28.1 pytest==9.1.1
	mkdir -p $(dir $(EVOMASTER_JAR))
	test -f $(EVOMASTER_JAR) || curl -sSL -o $(EVOMASTER_JAR) \
		https://github.com/WebFuzzing/EvoMaster/releases/download/v$(EVOMASTER_VERSION)/evomaster.jar
	echo "$(EVOMASTER_SHA256)  $(EVOMASTER_JAR)" | sha256sum --check --quiet
	uv venv --python 3.12 --allow-existing .venvs/evomaster
	# what EvoMaster's generated Python tests import
	uv pip install --python .venvs/evomaster/bin/python requests==2.34.2 pytest==9.1.1 \
		timeout-decorator==0.5.0 rfc3986==2.0.0

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
