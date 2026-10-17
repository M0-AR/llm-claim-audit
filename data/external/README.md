# External datasets (committed for offline reproducibility)

Two community databases, both downloaded 2026-10-17, are vendored so the
snapshot pipeline runs with networking disabled. Provenance and licensing:

## kaggle-llm-benchmark-wars/

- Dataset: "LLM Benchmark Wars 2025-2026 | 24 Models Compared" (Kaggle user `alitaqishah`)
- URL: https://www.kaggle.com/datasets/alitaqishah/llm-benchmark-wars-2025-2026-24-models-compared
- License: CC0-1.0 (public domain)
- Files: `llm_benchmark_comparison_2025_2026.csv`
- SHA-256: `e0be5197f4384b9a1787a4b810f270305e9536017a4a6a3c839b88b8b303476a`
- Role in this project: dataset A for the E3 leaderboard-resolution audit
  (per-model MMLU / HumanEval / GPQA-Diamond / SWE-bench / HellaSwag / AIME
  2025 scores plus pricing; column `overall_benchmark_avg` is the composite).

## kaggle-frontier-ai-models/

- Dataset: "Frontier AI Models Intelligence Hub" (Kaggle user `saitejabandaruin`)
- URL: https://www.kaggle.com/datasets/saitejabandaruin/frontier-ai-models
- License: CC BY 4.0
- Key files: `models.csv` (130-column model registry), `benchmarks.csv`
  (long format: model x benchmark x score), `frontier_ai_hub.sqlite`,
  `quality_report.json`, `providers.csv`, `schema.json`
- SHA-256 (`models.csv`): `7140b1832dbc2aebef07e309ff9bfe8e5bb0cf0296449e73799edbc99ed040e1`
- SHA-256 (`benchmarks.csv`): `3959a443ac1bc7bfd1db2a9162e622c2630a8870072775ffcfcb37b696522298`
- Role in this project: dataset B - registry health (deprecation fields,
  knowledge-cutoff dates) and the dual arena-Elo columns
  (`bench_lmarena_elo` vs `bench_chatbot_arena_elo`), used as machine evidence
  for claims C03, C07 and C11.

## Usage notes

- These are third-party community databases of uncertain primary provenance.
  They are used here only to demonstrate *machine-checkable audit methods*;
  claims about any specific vendor number must be traced to the vendor page
  before publication.
- The snapshot pipeline (`scripts/run_all.py --mode snapshot`) reads these
  files as-is and hashes them into `results/run_manifest.json`.
