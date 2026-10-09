# restgen

**Hybrid Artificial Bee Colony + LLM approach for REST APIs.**

Graduation thesis project. The Artificial Bee Colony (ABC) algorithm drives a
population-based search; a large language model acts as a knowledge-rich
operator inside it (constructing, mutating or repairing candidate solutions).

> Status: **literature review**. No method code yet. Private repository.

Whether the method generates *test suites for existing REST APIs* or *REST API
implementations* is decided at the end of the review — see
[docs/RESEARCH_PLAN.md](docs/RESEARCH_PLAN.md).

## Where things are

| What | Where |
|------|-------|
| Thesis plan, open decisions, research questions | [docs/RESEARCH_PLAN.md](docs/RESEARCH_PLAN.md) |
| Literature review protocol | [docs/literature/README.md](docs/literature/README.md) |
| Bibliography / extraction matrix | [docs/literature/references.bib](docs/literature/references.bib), [docs/literature/extraction-matrix.csv](docs/literature/extraction-matrix.csv) |
| Experiment protocol (frozen before the first run) | [docs/EXPERIMENT_PROTOCOL.md](docs/EXPERIMENT_PROTOCOL.md) |
| Engineering rules, layout, commands | [AGENTS.md](AGENTS.md) |

## Development

```bash
make install          # .venv (Python 3.12) with dev tools
cp .env.example .env  # API keys, once an LLM is used
make check            # lint + type check + unit tests
```

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE).
