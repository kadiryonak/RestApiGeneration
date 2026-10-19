# Literature review protocol

A lightweight systematic review (Kitchenham & Charters, 2007) combined with
snowballing (Wohlin, 2014). Paper PDFs and Turkish reading notes stay in the
Obsidian vault (`SoftwareTest/RESTapiLiteratür/`); this folder holds the
protocol, the bibliography and the extraction matrix.

## Files

| File | Purpose |
|------|---------|
| `references.bib` | Every paper cited or read. Keys: `firstauthorYEARkeyword` (e.g. `kim2025llamaresttest`). Only verified metadata. |
| `extraction-matrix.csv` | One row per paper: screening decision and extracted data (see columns below). |
| `note-template.md` | Copy into the vault for each paper read in full. |

## Review questions

- **LQ1** Which techniques generate tests for REST APIs (search-based, RL,
  LLM-based, hybrid), and how are they evaluated (benchmarks, metrics, baselines)?
- **LQ2** How are LLMs used to generate REST API *implementations* from specs
  or requirements, and how is correctness measured?
- **LQ3** How have ABC (and other swarm / evolutionary algorithms) been
  applied to software engineering problems — test generation, code
  generation, program repair? How is the neighbour operator defined for
  discrete solutions?
- **LQ4** How are LLMs combined with metaheuristics (LLM as mutation /
  crossover / construction operator, LLM-guided search, metaheuristic-tuned
  prompts)?
- **LQ5** What gap remains that an ABC + LLM hybrid can address? → Decision D1.

## Sources

IEEE Xplore, ACM Digital Library, Scopus, Web of Science, SpringerLink,
ScienceDirect, arXiv (cs.SE, cs.NE), Google Scholar (for snowballing).
Turkish theses: YÖK Ulusal Tez Merkezi; Turkish venues: DergiPark.

## Search strings (adapt to each engine's syntax; log every search below)

```
S1  ("REST API" OR RESTful OR OpenAPI OR "web API") AND (test* ) AND (generat* OR fuzz*)
S2  ("REST API" OR RESTful OR OpenAPI) AND ("large language model" OR LLM OR GPT) AND (generat* OR synthes*)
S3  ("artificial bee colony" OR "ABC algorithm") AND ("software test*" OR "test case" OR "test data" OR "code generation" OR "program repair")
S4  ("large language model" OR LLM) AND ("evolutionary" OR "genetic algorithm" OR "swarm" OR "metaheuristic" OR "search-based")
S5  ("search-based software engineering" OR SBSE) AND ("large language model" OR LLM)
```

## Inclusion / exclusion

- **Include:** peer-reviewed or arXiv preprint; English (or Turkish thesis);
  2015 onwards for S1, S2, S4, S5 (S3 has no year limit; ABC dates from 2005);
  proposes, evaluates or surveys a technique relevant to LQ1–LQ4.
- **Exclude:** no empirical evaluation and not a survey; only the abstract is
  available; duplicate or extended version (keep the most complete one);
  REST used only as an implementation detail.

## Quality assessment (0 / 0.5 / 1 each)

Q1 clear aims · Q2 replicable method description · Q3 real-world benchmark ·
Q4 comparison with baselines · Q5 statistical analysis / repeated runs ·
Q5b threats to validity discussed · Q6 artefact (tool, data) available.

## Extraction matrix columns

`reading_order, key, pdf_status (have/download/paywalled), title, year, venue, source(search id / snowball), lq, screening
(include/exclude/pending), exclusion_reason, approach_category, uses_llm,
llm_model, uses_metaheuristic, metaheuristic, solution_encoding, fitness,
benchmark, metrics, baselines, main_result, limitations, artefact_url,
quality_score, notes_in_vault`

## Search log

| Date | Engine | String | Filters | Hits | After title/abstract | After full text |
|------|--------|--------|---------|------|----------------------|-----------------|
