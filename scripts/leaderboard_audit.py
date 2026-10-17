#!/usr/bin/env python3
"""E3: leaderboard-resolution audit on public 2026 benchmark datasets.

Dataset A (community, CC0): Kaggle 'LLM Benchmark Wars 2025-2026', 24 frontier
models x 6 benchmark columns + overall average.
Dataset B (community, CC BY 4.0): Kaggle 'Frontier AI Models Intelligence Hub',
130-column model registry including deprecation and knowledge-cutoff fields.

Analysis, mirroring the paired-resolution programme of the 2026 SWE-bench
audits (arXiv:2609.17394; Zenodo 10.5281/zenodo.22541065):

  1. top-k spreads and how many adjacent pairs sit within 2.5 points,
     the width of the top-model plateau observed independently by Scale Labs
     on MultiChallenge (2026-10-17);
  2. an item bootstrap: resample the six benchmark columns with replacement,
     recompute ranks, and report how often the original top-1 and top-3
     survive - a small-scale, reproducible estimate of rank fragility;
  3. registry health: deprecation counts and the divergence between the two
     arena-Elo columns stored side by side (LMArena and legacy Chatbot Arena).

Outputs: results/leaderboard_convergence.json, results/leaderboard_topk.csv
"""

import argparse
import csv
import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

SEED = 20261017
BOOTSTRAP_REPLICATES = 10000
PLATEAU_POINTS = 2.5

BENCH_COLUMNS = ["mmlu", "humaneval", "gpqa_diamond", "swe_bench", "hellaswag", "aime_2025"]


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def numeric(row, col):
    raw = (row.get(col) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def topk_table(models):
    scored = [
        {"model": m["model_name"], "score": numeric(m, "overall_benchmark_avg")}
        for m in models
        if numeric(m, "overall_benchmark_avg") is not None
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(scored, start=1):
        row["rank"] = i
    return scored


def bootstrap_ranking(models, top1_name, top3_names, seed=SEED, reps=BOOTSTRAP_REPLICATES):
    matrix = []
    for m in models:
        vals = [numeric(m, c) for c in BENCH_COLUMNS]
        if all(v is not None for v in vals):
            matrix.append((m["model_name"], vals))
    if not matrix:
        return {}

    rng = random.Random(seed)
    n_items = len(BENCH_COLUMNS)
    top1_hits = 0
    top3_hits = 0
    top1_counts = {}
    for _ in range(reps):
        cols = [rng.randrange(n_items) for _ in range(n_items)]
        scored = sorted(
            ((name, statistics.fmean(vals[c] for c in cols)) for name, vals in matrix),
            key=lambda pair: pair[1],
            reverse=True,
        )
        winner = scored[0][0]
        top1_counts[winner] = top1_counts.get(winner, 0) + 1
        if winner == top1_name:
            top1_hits += 1
        top3_set = {name for name, _ in scored[:3]}
        if top3_set == top3_names:
            top3_hits += 1

    return {
        "models_used": [name for name, _ in matrix],
        "replicates": reps,
        "seed": seed,
        "items_resampled": BENCH_COLUMNS,
        "top1_retention": round(top1_hits / reps, 4),
        "top3_set_retention": round(top3_hits / reps, 4),
        "top1_distribution": dict(
            sorted(top1_counts.items(), key=lambda kv: kv[1], reverse=True)
        ),
    }


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return round(num / (denx * deny), 4)


def registry_health(frontier_models):
    if not frontier_models:
        return {}
    deprecated = [
        m for m in frontier_models if (m.get("is_deprecated") or "").strip().lower() == "true"
    ]
    ld, cd = [], []
    for m in frontier_models:
        a = (m.get("bench_lmarena_elo") or "").strip()
        b = (m.get("bench_chatbot_arena_elo") or "").strip()
        if a and b:
            ld.append(float(a))
            cd.append(float(b))
    pairs = len(ld)
    return {
        "n_models": len(frontier_models),
        "n_deprecated": len(deprecated),
        "deprecated_examples": [m["model_name"] for m in deprecated[:8]],
        "n_arena_elo_pairs": pairs,
        "arena_elo_pearson": pearson(ld, cd) if pairs else None,
        "arena_elo_mean_gap": round(statistics.fmean(a - b for a, b in zip(ld, cd)), 2)
        if pairs
        else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-dir", default="data/external")
    ap.add_argument("--out-dir", default="results")
    args = ap.parse_args(argv)

    ext = Path(args.external_dir)
    models_a = load_csv(ext / "kaggle-llm-benchmark-wars" / "llm_benchmark_comparison_2025_2026.csv")
    models_b = load_csv(ext / "kaggle-frontier-ai-models" / "models.csv")

    table = topk_table(models_a)
    top5 = table[:5]
    top3_names = {row["model"] for row in table[:3]}
    adjacent_gaps = {
        f"{table[i]['model']} -> {table[i + 1]['model']}": round(
            table[i]["score"] - table[i + 1]["score"], 2
        )
        for i in range(min(10, len(table) - 1))
    }
    within_plateau = sum(1 for g in adjacent_gaps.values() if g <= PLATEAU_POINTS)

    boot = bootstrap_ranking(models_a, table[0]["model"], top3_names)
    registry = registry_health(models_b)

    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset_a": {
            "name": "Kaggle: LLM Benchmark Wars 2025-2026 (24 models)",
            "n_models": len(table),
            "top5": top5,
            "top1_minus_top2": round(table[0]["score"] - table[1]["score"], 2),
            "top1_minus_top5": round(table[0]["score"] - table[4]["score"], 2),
            "adjacent_gaps_top10": adjacent_gaps,
            "adjacent_gaps_within_2_5_pts": within_plateau,
            "plateau_threshold_points": PLATEAU_POINTS,
            "bootstrap": boot,
        },
        "dataset_b": {
            "name": "Kaggle: Frontier AI Models Intelligence Hub",
            "registry": registry,
        },
        "external_reference": {
            "scale_labs_multichallenge_2026_10_17": "Top-3 models within a 2.5-point band; open models lag 15-20 points (labs.scale.com/blog/multichallenge-update)",
            "swebench_resolution_audit": "29/29 adjacent Verified pairs not separable at alpha=0.05 (arXiv:2609.17394)",
            "zenodo_resolution_bound": "delta >= 2.80*sqrt(d/n) predicts decidable pairs; SWE-bench Verified 129/133 adjacent ranks inseparable (Zenodo 10.5281/zenodo.22541065)",
        },
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    topk_path = out_dir / "leaderboard_topk.csv"
    with open(topk_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["rank", "model", "score"])
        writer.writeheader()
        writer.writerows(table)

    summary_path = out_dir / "leaderboard_convergence.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    print(json.dumps(summary, indent=2))
    print(f"wrote {topk_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
