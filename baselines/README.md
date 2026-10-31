# Baseline installations

This directory separates third-party comparison tools from restgen's own source code.
Run `make tools` to validate/install the pinned versions.

| Path | Purpose | Provenance |
|---|---|---|
| `schemathesis/` | pinned upstream clone and its private `.venv` | commit in `Makefile` |
| `hypothesis/` | pinned, partial upstream clone used as the library baseline | commit in `Makefile` |
| `.venvs/hypothesis/` | environment that runs generated Hypothesis suites | reproducible by `make tools` |
| `evomaster/releases/` | checksum-verified EvoMaster release JAR | version/hash in `Makefile` |
| `evomaster/.venv/` | environment that runs EvoMaster's generated Python tests | reproducible by `make tools` |

All installation directories are git-ignored. This README and the installer/configuration
files are the reproducible description; third-party source and binaries are never committed.

Do not confuse this directory with `src/restgen/baselines/`: that Python package contains
restgen's adapters for running comparison tools through the common measurement pipeline.
