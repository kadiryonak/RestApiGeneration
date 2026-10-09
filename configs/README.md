# Configuration

Configuration is the single source of truth for every run (AGENTS.md).

- `restgen.toml` — the base configuration (created with the first code).
- `experiments/<name>.toml` — one file per experimental condition; differs from
  the base only in what the condition changes.
- `benchmark.toml` — pinned benchmark manifest (see `benchmark/README.md`).

Expected sections once the method exists: `[llm]`, `[pricing]`, `[budget]`,
`[abc]` (colony size, limit, max cycles / evaluations, seed), `[fitness]`,
`[execution]`, `[paths]`.
