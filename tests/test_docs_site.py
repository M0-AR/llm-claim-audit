#!/usr/bin/env python3
"""Documentation and interactive-site tests: README contract, redirects, assets, offline guarantees."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8")
SITE_TEXT = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

BEGINNER_HEADING = "## 🌱 Beginner guide — Read this and you are a professional"
BEGINNER_ANCHOR = "(#-beginner-guide--read-this-and-you-are-a-professional)"


class ReadmeContractTests(unittest.TestCase):
    def test_beginner_guide_heading_and_anchor(self):
        self.assertIn(BEGINNER_HEADING, README_TEXT)
        self.assertIn(BEGINNER_ANCHOR, README_TEXT)

    def test_beginner_guide_promise_and_quote(self):
        self.assertIn("You will know more than most interview candidates.", README_TEXT)
        self.assertIn(
            "Let's work this out in a step-by-step way to be sure we have the right answer",
            README_TEXT,
        )

    def test_readme_embeds_demo_gif(self):
        self.assertIn('src="docs/assets/demo.gif"', README_TEXT)
        gif = ROOT / "docs" / "assets" / "demo.gif"
        self.assertTrue(gif.exists())
        blob = gif.read_bytes()
        self.assertTrue(blob.startswith(b"GIF8"))
        self.assertLess(len(blob), 5_000_000)

    def test_readme_documents_live_links(self):
        live = "https://m0-ar.github.io/llm-claim-audit"
        for suffix in ("/", "/preview.html", "/docs/preview.html"):
            self.assertIn(live + suffix, README_TEXT)


class SiteTests(unittest.TestCase):
    def test_site_exists_and_carries_headline_numbers(self):
        self.assertTrue((ROOT / "docs" / "index.html").exists())
        for marker in ("17 claims", "60%", "12.57", "0.08", "44.9", "200,019"):
            self.assertIn(marker, SITE_TEXT)

    def test_site_numbers_trace_to_committed_results(self):
        audit = json.loads((ROOT / "results" / "claim_audit_summary.json").read_text())
        fx = json.loads((ROOT / "results" / "fx_triangulation.json").read_text())
        lb = json.loads((ROOT / "results" / "leaderboard_convergence.json").read_text())
        tok = json.loads((ROOT / "results" / "token_reenactment.json").read_text())
        self.assertEqual(audit["n_claims"], 17)
        self.assertEqual(round(audit["era_dependent_drift"]["drift_rate"] * 100), 60)
        self.assertEqual(fx["median_abs_diff_bps"], 12.57)
        self.assertEqual(lb["dataset_a"]["top1_minus_top2"], 0.08)
        self.assertLess(abs(fx["cross_vendor"]["btc_usd"]["yahoo_vs_coingecko_bps"]), 50.0)
        self.assertAlmostEqual(lb["dataset_a"]["bootstrap"]["top1_retention"], 0.4492, places=4)
        self.assertIn(f"{tok['vocab_size_total']:,}", SITE_TEXT)

    def test_site_loads_no_external_resources(self):
        patterns = [
            r"<script[^>]+src=",
            r"<link[^>]+href=[\"']https?://",
            r"<img[^>]+src=[\"']https?://",
            r"url\([\"']?https?://",
            r"@import",
        ]
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, SITE_TEXT), pattern)

    def test_site_quiz_has_ten_questions_and_result_card(self):
        self.assertEqual(len(re.findall(r'\bq:"', SITE_TEXT)), 10)
        self.assertIn('id="quizResult"', SITE_TEXT)
        self.assertIn("See my result", SITE_TEXT)


class RedirectTests(unittest.TestCase):
    def test_preview_and_root_redirect_to_site(self):
        for name in ("preview.html", "index.html"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('http-equiv="refresh"', text)
            self.assertIn("docs/index.html", text)
        docs_preview = (ROOT / "docs" / "preview.html").read_text(encoding="utf-8")
        self.assertIn('http-equiv="refresh"', docs_preview)
        self.assertIn("index.html", docs_preview)

    def test_nojekyll_present(self):
        self.assertTrue((ROOT / "docs" / ".nojekyll").exists())
        self.assertTrue((ROOT / ".nojekyll").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
