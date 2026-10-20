.PHONY: install tools toolchain lint format typecheck test test-integration check

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

# JVM services (WFD/EMB): pinned JDK 8 and Maven inside .tools/, checksum-verified.
JDK8_TAR = OpenJDK8U-jdk_x64_linux_hotspot_8u504b01.tar.gz
JDK8_URL = https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u504-b01/$(JDK8_TAR)
JDK8_SHA256 = 9c70e102f527ac674ac2fe9c7d47b9a04e2d19842ba5ab8e9b33f368bbadfaea
MAVEN_TAR = apache-maven-3.9.16-bin.tar.gz
MAVEN_URL = https://archive.apache.org/dist/maven/maven-3/3.9.16/binaries/$(MAVEN_TAR)
MAVEN_SHA512 = 831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6

toolchain:
	mkdir -p .tools/downloads .tools/jdk .tools/maven
	test -f .tools/downloads/$(JDK8_TAR) || curl -sSL -o .tools/downloads/$(JDK8_TAR) $(JDK8_URL)
	echo "$(JDK8_SHA256)  .tools/downloads/$(JDK8_TAR)" | sha256sum --check --quiet
	test -d .tools/jdk/jdk8u504-b01 || tar -xzf .tools/downloads/$(JDK8_TAR) -C .tools/jdk
	test -f .tools/downloads/$(MAVEN_TAR) || curl -sSL -o .tools/downloads/$(MAVEN_TAR) $(MAVEN_URL)
	echo "$(MAVEN_SHA512)  .tools/downloads/$(MAVEN_TAR)" | sha512sum --check --quiet
	test -d .tools/maven/apache-maven-3.9.16 || tar -xzf .tools/downloads/$(MAVEN_TAR) -C .tools/maven

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
