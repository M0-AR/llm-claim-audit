#!/usr/bin/env python3
"""E1: audit the claim ledger and cross-check machine-checkable claims.

Reads claims/claims.csv (the ledger of material claims from the video window),
validates its structure, cross-checks selected claims against the committed
public datasets in data/external/, and reports era-dependent drift with a
Wilson 95% confidence interval.

Outputs: results/claim_audit.csv, results/claim_audit_summary.json
"""

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

ALLOWED_STATUSES = {
    "verified",
    "verified_with_caveat",
    "verified_evolved",
    "outdated",
    "superseded",
    "advice_still_supported",
}

DRIFT_STATUSES = {"outdated", "superseded"}
ERA_CATEGORIES = {"product_era", "platform_interface", "external_witness"}

CALCULATED_FIELDS = (
    "claim_id",
    "category",
    "claim_text",
    "evidence_from_video",
    "claim_date",
    "verification_method",
    "evidence_url",
    "evidence_date",
    "verified_at",
    "status",
    "notes",
)


def wilson_interval(successes, total, z=1.96):
    if total == 0:
        return [0.0, 0.0]
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def load_claims(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    problems = []
    for row in rows:
        for field in CALCULATED_FIELDS:
            if field not in row or row[field] is None:
                problems.append(f"{row.get('claim_id', '?')}: missing field {field}")
        if row.get("status") not in ALLOWED_STATUSES:
            problems.append(f"{row.get('claim_id', '?')}: bad status {row.get('status')!r}")
    return rows, problems


def load_frontier_models(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def machine_checks(external_dir):
    checks = {}
    models = load_frontier_models(Path(external_dir) / "kaggle-frontier-ai-models" / "models.csv")
    if models:
        fields = models[0].keys()
        checks["frontier_models_rows"] = len(models)
        gpt4o = [m for m in models if "gpt-4o" in (m.get("model_name") or "").lower()]
        checks["gpt4o_rows"] = [
            {
                "model_name": m.get("model_name"),
                "release_date": m.get("release_date"),
                "knowledge_cutoff_date": m.get("knowledge_cutoff_date"),
                "is_deprecated": m.get("is_deprecated"),
                "deprecation_date": m.get("deprecation_date"),
            }
            for m in gpt4o
        ]
        cutoffs = [m for m in models if (m.get("knowledge_cutoff_date") or "").strip()]
        checks["models_with_knowledge_cutoff"] = len(cutoffs)
        checks["lmarena_elo_present"] = "bench_lmarena_elo" in fields
        checks["chatbot_arena_elo_present"] = "bench_chatbot_arena_elo" in fields
        ld = [
            float(m["bench_lmarena_elo"])
            for m in models
            if (m.get("bench_lmarena_elo") or "").strip()
        ]
        cd = [
            float(m["bench_chatbot_arena_elo"])
            for m in models
            if (m.get("bench_chatbot_arena_elo") or "").strip()
        ]
        checks["lmarena_elo_nonnull"] = len(ld)
        checks["chatbot_arena_elo_nonnull"] = len(cd)
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claims", default="claims/claims.csv")
    ap.add_argument("--external-dir", default="data/external")
    ap.add_argument("--out-dir", default="results")
    args = ap.parse_args(argv)

    rows, problems = load_claims(args.claims)
    if problems:
        print("ledger problems:", *problems, sep="\n  ", file=sys.stderr)
        return 2

    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    era_rows = [r for r in rows if r["category"] in ERA_CATEGORIES]
    drifted = [r for r in era_rows if r["status"] in DRIFT_STATUSES]
    era_stats = {
        "n_era_dependent_claims": len(era_rows),
        "n_drifted": len(drifted),
        "drift_rate": round(len(drifted) / len(era_rows), 4) if era_rows else None,
        "wilson_95_ci": wilson_interval(len(drifted), len(era_rows)),
        "drifted_claim_ids": [r["claim_id"] for r in drifted],
    }

    stable_rows = [r for r in rows if r["category"] == "science_stable"]
    science_stats = {
        "n_science_claims": len(stable_rows),
        "n_verified": sum(1 for r in stable_rows if r["status"].startswith("verified")),
        "all_hold": all(r["status"].startswith("verified") for r in stable_rows),
    }

    checks = machine_checks(args.external_dir)

    for row in rows:
        row["drifted"] = row["status"] in DRIFT_STATUSES
        row["era_dependent"] = row["category"] in ERA_CATEGORIES

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / "claim_audit.csv"
    with open(audit_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_claims": len(rows),
        "counts_by_status": counts,
        "era_dependent_drift": era_stats,
        "science_stable_durability": science_stats,
        "machine_checks": checks,
        "ledger_path": args.claims,
    }
    summary_path = out_dir / "claim_audit_summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    print(json.dumps(summary, indent=2))
    print(f"wrote {audit_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
