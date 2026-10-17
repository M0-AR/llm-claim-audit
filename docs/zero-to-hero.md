# Zero to Hero: verifying a 2025 AI video against 2026 reality

Andrej Karpathy's "How I use LLMs" (February 2025) was a practical tour of the
2025 chat-LLM ecosystem. This repository asks a simple, underrated question:

> If you re-checked every checkable statement in that video in October 2026,
> with primary sources and live market data, what would still hold?

The answer turned out to have structure worth teaching: **stable claims
(vocabulary sizes, caffeine content, hardware-era facts) survive almost
perfectly; era claims (tiers, model names, product defaults) decay fast; and
leaderboard "facts" are mostly noise at the top.**

This guide teaches the pipeline from zero.

## 1. What you need

- Python 3.12 (stdlib only, plus `tiktoken` for experiment E4)
- Optionally Docker + Compose for the offline proof
- No API keys, no paid services, no accounts

## 2. The one-command run

```bash
python3 scripts/run_all.py --mode snapshot
```

This runs four experiments over committed data:

| Experiment | Script | Reads | Writes |
|---|---|---|---|
| E1 claim audit | `scripts/verify_claims.py` | `claims/claims.csv`, `data/external/` | `results/claim_audit*.{csv,json}` |
| E2 market triangulation | `scripts/cross_validate.py` | `data/live/*.json` | `results/fx_triangulation.*` |
| E3 leaderboard resolution | `scripts/leaderboard_audit.py` | `data/external/` | `results/leaderboard_*` |
| E4 tokenizer re-enactment | `scripts/token_reenactment.py` | `tiktoken` | `results/token_reenactment.json` |

Everything is deterministic except the timestamps; the run ends with
`results/run_manifest.json`, a SHA-256 manifest of every artifact.

## 3. The claim ledger (E1)

`claims/claims.csv` is the heart of the project: 17 material claims from the
video, each with the quote, a date, a verification method, a source URL, and a
status - `verified`, `verified_with_caveat`, `verified_evolved`, `outdated`,
`superseded`, or `advice_still_supported`.

To add a claim: append a row, re-run `verify_claims.py`, and record how you
checked it. The script validates the schema and computes era-drift statistics:
what fraction of *era-dependent* claims (product tiers, interface defaults,
ecosystem witnesses) had to be re-statused within 20 months - with a Wilson
95% interval, computed in plain Python for transparency.

## 4. Market triangulation (E2)

The video-era question "how do you know a price is real?" gets a concrete
answer. `data/live/` holds frozen 2026-10-17 snapshots (ECB reference rates
via Frankfurter, CoinGecko BTC in USD and EUR, Yahoo Finance cross-quotes).
`cross_validate.py`:

1. re-derives EUR/USD from the bitcoin cross-rate (1 / (BTC_EUR / BTC_USD))
   and measures the deviation from the ECB fixing in basis points;
2. compares vendors (Yahoo vs CoinGecko, Yahoo vs ECB) for the same asset;
3. uses the publication calendar as structure: crypto quotes 7 days a week,
   the ECB 5, so weekend rows *must* exist in one series and not the other.

Lesson: independent sources agree to within ~10-25 bps, and the residual is
mostly *timestamp misalignment*, not disagreement. Run live mode to repeat it:

```bash
python3 scripts/run_all.py --mode live   # needs network; writes data/live-live/ and results/live/
```

## 5. Leaderboard resolution (E3)

Public leaderboards invite reading "rank 1" as "best". `leaderboard_audit.py`
shows why that's fragile:

- top-5 spreads and how many adjacent pairs sit within 2.5 points, the width
  of the current top-model plateau on independent boards;
- an item bootstrap (10,000 replicates, seed 20261017, stdlib `random`):
  resample the six benchmark columns with replacement, recompute the ranking,
  and count how often the original top-1 and top-3 survive;
- registry health: how many models in a 130-column 2026 registry are already
  deprecated, and how far apart the two arena-Elo columns sit.

This mirrors the 2026 "paired resolution" literature (see README references),
where most adjacent SWE-bench pairs are statistically inseparable.

## 6. Tokenizer re-enactment (E4)

The video counted 15 tokens for a request, 19 for a reply, 42 for the
chat-formatted exchange. The exact source strings are not recoverable from the
fetched transcript window, so `token_reenactment.py` re-enacts the *method*:
it counts tokens with `tiktoken`'s `o200k_base` (the GPT-4o encoding), shows
the chat-format overhead of special tokens, and verifies the "roughly 200,000
token vocabulary" claim against the shipped tokenizer (200,019 mergeable
ranks).

## 7. The model-contact harness (E5, preregistered)

`harness/` is a frozen experiment: 40 arithmetic tasks (12-digit x 8-digit,
seed 20261017), a runner that sends them to any OpenAI-compatible endpoint,
and an offline scorer with exact McNemar tests and bootstrap CIs. Without
`OPENAI_API_KEY` the runner exits with code 2 and nothing is claimed - the
README says so explicitly. Freeze the analysis before seeing results; that's
the whole point.

```bash
OPENAI_API_KEY=... OPENAI_MODEL=<model> python3 harness/runner.py
python3 harness/score.py --b results/harness_responses.jsonl
```

## 8. The offline proof (Docker)

```bash
docker compose run --rm snapshot    # networking disabled; same results
docker compose run --rm --build live  # optional: fresh market data
```

`network_mode: "none"` plus committed data means the snapshot analysis is
bit-for-bit reproducible from the repo alone. `make test` runs the unit and
integration tests, including live-data tolerance checks against the frozen
snapshots.

## 9. Reading and extending the results

- `results/claim_audit_summary.json` - drift statistics and machine checks
- `results/fx_triangulation.json` - bps deviations, cross-vendor gaps
- `results/leaderboard_convergence.json` - plateau width, bootstrap retention
- `results/run_manifest.json` - hashes for everything above

To extend: add rows to `claims/claims.csv`, add a snapshot file to
`data/live/` (follow the schemas), or add benchmark columns in
`leaderboard_audit.py::BENCH_COLUMNS`. Re-run the pipeline and the README's
numbers can be regenerated - nothing in the analysis is hand-computed.

## 10. What you should take away

1. Re-check claims with a ledger, not a vibe: quote, date, source, status.
2. Prefer triangulation: two independent vendors plus structure (calendars,
   cross-rates) beats one authoritative-looking number.
3. Treat top-of-leaderboard gaps under ~2-3 points as unresolved, not as
   rankings; resampling shows how little separates the leaders.
4. Separate *what was true* from *what was said*: most 2025-era claims were
   accurate when recorded and simply aged - that's a property of fast-moving
   products, not of the videographer.
