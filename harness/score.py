#!/usr/bin/env python3
"""E5 scorer: offline analysis of harness response files (no network).

Usage:
  python3 harness/score.py --b results/harness_nonthinking.jsonl
  python3 harness/score.py --a results/harness_thinking.jsonl --b results/harness_nonthinking.jsonl

With one file: accuracy + Wilson 95% interval (H1 check).
With two files: adds b/c discordant counts, exact McNemar p-value (H2) and a
bootstrap CI of the paired accuracy difference (H3); --a is the variant
expected to win. Outputs results/harness_score.json (or --out).
"""

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

SEED = 20261017
REPS = 10000


def extract_int(text):
    if not text:
        return None
    m = re.search(r"-?\d+", text.replace(",", ""))
    return int(m.group()) if m else None


def load(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def is_correct(record):
    return record.get("ok") and extract_int(record.get("response")) == int(record["answer"])


def wilson(successes, total, z=1.96):
    if total == 0:
        return [0.0, 0.0]
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return {"discordant_b": b, "discordant_c": c, "n_discordant": 0, "p_value_two_sided": 1.0}
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return {
        "discordant_b": b,
        "discordant_c": c,
        "n_discordant": n,
        "p_value_two_sided": round(min(1.0, 2 * tail), 6),
    }


def bootstrap_diff(correct_a, correct_b, reps=REPS, seed=SEED):
    rng = random.Random(seed)
    n = len(correct_a)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(correct_a[i] for i in idx) / n - sum(correct_b[i] for i in idx) / n)
    diffs.sort()
    lo = diffs[int(0.025 * reps)]
    hi = diffs[min(reps - 1, int(0.975 * reps))]
    return [round(lo, 4), round(hi, 4)]


def summarize(records, label):
    correct = [is_correct(r) for r in records]
    hits = sum(correct)
    return {
        "label": label,
        "n_tasks": len(records),
        "n_correct": hits,
        "accuracy": round(hits / len(records), 4) if records else None,
        "wilson_95_ci": wilson(hits, len(records)),
        "correct_flags": correct,
        "task_ids": [r["task_id"] for r in records],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", default=None, help="variant expected to win (e.g. thinking)")
    ap.add_argument("--b", required=True, help="baseline response file")
    ap.add_argument("--out", default="results/harness_score.json")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    base = load(args.b)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "seed": args.seed,
        "bootstrap_replicates": REPS,
        "baseline": {k: v for k, v in summarize(base, Path(args.b).name).items() if k != "correct_flags"},
    }

    if args.a:
        var = load(args.a)
        by_id_base = {r["task_id"]: r for r in base}
        by_id_var = {r["task_id"]: r for r in var}
        ids = sorted(set(by_id_base) & set(by_id_var))
        ca = [is_correct(by_id_var[i]) for i in ids]
        cb = [is_correct(by_id_base[i]) for i in ids]
        b_count = sum(1 for x, y in zip(ca, cb) if x and not y)
        c_count = sum(1 for x, y in zip(ca, cb) if y and not x)
        doc["variant"] = {k: v for k, v in summarize(var, Path(args.a).name).items() if k != "correct_flags"}
        doc["paired_analysis"] = {
            "n_paired_tasks": len(ids),
            "mcnemar_exact": mcnemar_exact(b_count, c_count),
            "accuracy_difference_95_ci": bootstrap_diff(ca, cb, seed=args.seed),
            "accuracy_difference": round(sum(ca) / len(ca) - sum(cb) / len(cb), 4) if ids else None,
        }

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(json.dumps(doc, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
