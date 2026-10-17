#!/usr/bin/env python3
"""Unit and integration tests for the snapshot pipeline (stdlib unittest)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "harness"))

import cross_validate  # noqa: E402
import leaderboard_audit  # noqa: E402
import verify_claims  # noqa: E402


class LedgerTests(unittest.TestCase):
    def test_ledger_loads_without_problems(self):
        rows, problems = verify_claims.load_claims(ROOT / "claims" / "claims.csv")
        self.assertEqual(problems, [])
        self.assertGreaterEqual(len(rows), 17)

    def test_wilson_interval_bounds(self):
        lo, hi = verify_claims.wilson_interval(5, 10)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 1.0)
        self.assertEqual(verify_claims.wilson_interval(0, 0), [0.0, 0.0])


def synthetic_live():
    ecb_dates = ["2026-10-05", "2026-10-06", "2026-10-07"]
    crypto_dates = ecb_dates + ["2026-10-10", "2026-10-11"]
    return {
        "ecb": {
            "rates": [{"date": d, "rate": 1.10} for d in ecb_dates],
        },
        "btc_usd": {"prices": [{"date": d, "close": 110000.0} for d in crypto_dates]},
        "btc_eur": {"prices": [{"date": d, "close": 100000.0} for d in crypto_dates]},
    }


class TriangulationTests(unittest.TestCase):
    def test_identity_triangulation(self):
        live = synthetic_live()
        rows = cross_validate.triangulate(live)
        summary = cross_validate.summarize(rows, live, tolerance_bps=100.0)
        self.assertTrue(summary["tolerance_passed"])
        for row in rows:
            if row["ecb_published"]:
                self.assertAlmostEqual(row["diff_bps"], 0.0, places=6)

    def test_weekend_gap_detection(self):
        live = synthetic_live()
        rows = cross_validate.triangulate(live)
        summary = cross_validate.summarize(rows, live, tolerance_bps=100.0)
        self.assertEqual(summary["unpublished_dates"], ["2026-10-10", "2026-10-11"])
        self.assertEqual(summary["unpublished_weekdays"], ["Saturday", "Sunday"])

    def test_tolerance_failure_flagged(self):
        rows = [{"date": "2026-10-05", "weekday": "Monday", "btc_usd": 100000.0, "btc_eur": 120000.0,
                 "implied_eurusd": 1.2, "ecb_eurusd": 1.1, "diff_bps": 909.09, "ecb_published": True}]
        summary = cross_validate.summarize(rows, {}, tolerance_bps=100.0)
        self.assertFalse(summary["tolerance_passed"])


@unittest.skipUnless((ROOT / "data" / "live" / "ecb_eurusd.json").exists(), "frozen snapshots missing")
class FrozenSnapshotTests(unittest.TestCase):
    def test_real_snapshot_tolerances(self):
        live = cross_validate.load_live(ROOT / "data" / "live")
        rows = cross_validate.triangulate(live)
        summary = cross_validate.summarize(rows, live, tolerance_bps=100.0)
        self.assertTrue(summary["tolerance_passed"])
        self.assertGreaterEqual(summary["n_aligned_with_ecb"], 5)
        btc_cross = summary["cross_vendor"]["btc_usd"]["yahoo_vs_coingecko_bps"]
        self.assertLess(abs(btc_cross), 50.0)
        self.assertTrue({"Saturday", "Sunday"} <= set(summary["unpublished_weekdays"]))


class LeaderboardTests(unittest.TestCase):
    def test_bootstrap_and_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = leaderboard_audit.main(
                ["--external-dir", str(ROOT / "data" / "external"), "--out-dir", tmp]
            )
            self.assertEqual(rc, 0)
            doc = json.loads((Path(tmp) / "leaderboard_convergence.json").read_text())
            self.assertEqual(doc["dataset_a"]["bootstrap"]["replicates"], 10000)
            self.assertEqual(len(doc["dataset_a"]["top5"]), 5)
            self.assertGreater(doc["dataset_b"]["registry"]["n_models"], 50)


class HarnessTests(unittest.TestCase):
    def test_mcnemar_exact_known_value(self):
        from score import mcnemar_exact

        result = mcnemar_exact(2, 8)
        self.assertAlmostEqual(result["p_value_two_sided"], 0.109375, places=6)

    def test_score_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a_file = tmp / "a.jsonl"
            b_file = tmp / "b.jsonl"

            def rec(task_id, answer, response, ok=True):
                return {"task_id": task_id, "answer": answer, "response": response, "ok": ok}

            a_records = [
                rec(1, "100", "100"),
                rec(2, "200", "200"),
                rec(3, "300", "301"),
                rec(4, "400", "The answer is 400."),
            ]
            b_records = [
                rec(1, "100", "100"),
                rec(2, "200", "99"),
                rec(3, "300", "300"),
                rec(4, "400", "I cannot do that"),
            ]
            a_file.write_text("\n".join(json.dumps(r) for r in a_records))
            b_file.write_text("\n".join(json.dumps(r) for r in b_records))
            out = tmp / "score.json"
            from score import main as score_main

            rc = score_main(["--a", str(a_file), "--b", str(b_file), "--out", str(out)])
            self.assertEqual(rc, 0)
            doc = json.loads(out.read_text())
            self.assertEqual(doc["baseline"]["n_correct"], 2)
            self.assertEqual(doc["variant"]["n_correct"], 3)
            self.assertEqual(doc["paired_analysis"]["mcnemar_exact"]["discordant_b"], 2)
            self.assertEqual(doc["paired_analysis"]["mcnemar_exact"]["discordant_c"], 1)

    def test_runner_requires_key(self):
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "OPENAI_MODEL")}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "harness" / "runner.py")],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)


class TokenizerTests(unittest.TestCase):
    def test_token_reenactment(self):
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            self.skipTest("tiktoken not installed")
        with tempfile.TemporaryDirectory() as tmp:
            import token_reenactment

            rc = token_reenactment.main(["--out-dir", tmp])
            self.assertEqual(rc, 0)
            doc = json.loads((Path(tmp) / "token_reenactment.json").read_text())
            self.assertFalse(doc.get("skipped", False))
            self.assertTrue(doc["vocabulary_claim_holds"])
            total = doc["query"]["tokens"] + doc["response"]["tokens"]
            self.assertGreater(doc["chat_formatted"]["tokens"], total)


if __name__ == "__main__":
    unittest.main(verbosity=2)
