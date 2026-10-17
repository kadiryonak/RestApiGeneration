# CLAUDE.md

@AGENTS.md

## Additional notes for Claude

- Talk to the owner in Turkish; write code, identifiers, commit messages and
  repository docs in English.
- Commit messages: imperative, concise, no `Co-Authored-By` or any AI/tool
  attribution. The owner is the only author.
- **Phase gate:** while `docs/RESEARCH_PLAN.md` says the phase is
  "literature review", do not write method code. Help with the review itself
  (finding papers, filling the extraction matrix, comparing approaches),
  repository hygiene and documents only.
- Research memory lives in the Obsidian vault at
  `~/Masaüstü/Obsidian Vault/RestApi/RestApi/RESTapiLiteratür/` (paper PDFs and
  Turkish reading notes). The repository keeps the English review protocol,
  `docs/literature/references.bib` and `docs/literature/extraction-matrix.csv`;
  keep the two in sync when a paper is added or read.
- Never invent bibliographic data. A BibTeX entry or matrix row is written only
  from the paper itself or its DOI/arXiv page; mark anything unverified with
  `TODO verify`.
- Before claiming a result, point to the run directory under `results/` that
  produced it.
- Experiments follow `docs/EXPERIMENT_PROTOCOL.md` exactly once it is frozen.
  Do not change conditions after seeing results; record any change in the
  protocol's change log and rerun affected runs.
- The sister project ABACUS (`github.com/kadiryonak/ABACUS`, LLM unit-test
  generation) is the reference for conventions: config-driven runs, resumable
  run directories, verification of results, paired statistics.
