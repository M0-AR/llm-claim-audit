#!/usr/bin/env python3
"""Run the full snapshot pipeline (or live mode) and write a manifest.

Snapshot mode (default): pure offline audit of the committed ledgers, frozen
market snapshots and external datasets. The Docker 'snapshot' service runs
this with networking disabled, proving the offline claim.

Live mode: first re-fetches market data into data/live-live/ (leaving the
frozen data/live/ snapshots untouched), then runs the same audits with the
fresh data, writing results into results/live/.

Outputs: <out-dir>/run_manifest.json plus everything the sub-steps write.
"""

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

REQUIRED = {"verify_claims", "cross_validate", "leaderboard_audit"}


def sha256(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def build_steps(mode):
    py = sys.executable
    if mode == "live":
        return [
            ("fetch_live", [py, str(HERE / "fetch_live.py"), "--out-dir", "data/live-live"], True),
            ("verify_claims", [py, str(HERE / "verify_claims.py"), "--out-dir", "results/live"], False),
            (
                "cross_validate",
                [py, str(HERE / "cross_validate.py"), "--data-dir", "data/live-live", "--out-dir", "results/live"],
                False,
            ),
            ("leaderboard_audit", [py, str(HERE / "leaderboard_audit.py"), "--out-dir", "results/live"], False),
            ("token_reenactment", [py, str(HERE / "token_reenactment.py"), "--out-dir", "results/live"], False),
        ]
    return [
        ("fetch_live", [py, str(HERE / "fetch_live.py")], True),
        ("verify_claims", [py, str(HERE / "verify_claims.py")], False),
        ("cross_validate", [py, str(HERE / "cross_validate.py")], False),
        ("leaderboard_audit", [py, str(HERE / "leaderboard_audit.py")], False),
        ("token_reenactment", [py, str(HERE / "token_reenactment.py")], False),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["snapshot", "live"], default="snapshot")
    ap.add_argument("--out-dir", default=None, help="defaults to results/ (snapshot) or results/live/ (live)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir or ("results/live" if args.mode == "live" else "results"))

    results = []
    for name, cmd, is_fetch in build_steps(args.mode):
        if name == "fetch_live" and args.mode != "live":
            results.append({"step": name, "status": "skipped", "reason": "snapshot mode"})
            continue
        proc = subprocess.run(cmd, cwd=ROOT)
        status = "ok" if proc.returncode == 0 else f"exit={proc.returncode}"
        results.append({"step": name, "status": status})
        print(f"[run_all] {name}: {status}")

    manifest = {
        "mode": args.mode,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "steps": results,
        "artifacts": {},
    }

    fixed = ["claims/claims.csv", "data/live/manifest.json"]
    for pattern in fixed:
        path = ROOT / pattern
        if path.exists():
            manifest["artifacts"][pattern] = sha256(path)
    for path in sorted(out_dir.glob("*")):
        if path.is_file():
            rel = str(path)
            manifest["artifacts"][rel] = sha256(path)
    for path in sorted((ROOT / "data" / "live").glob("*.json")):
        rel = str(path.relative_to(ROOT))
        manifest["artifacts"][rel] = sha256(path)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "run_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    failed_required = [
        r for r in results if r["step"] in REQUIRED and r["status"] not in ("ok", "skipped")
    ]
    print(json.dumps(manifest, indent=2))
    print(f"wrote {manifest_path}")
    return 1 if failed_required else 0


if __name__ == "__main__":
    sys.exit(main())
