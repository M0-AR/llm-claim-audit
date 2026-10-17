#!/usr/bin/env python3
"""E2: cross-source and triangular validation of live market data.

Reads frozen snapshots from data/live/ and checks three independent consensuses:
  1. crypto triangularity: implied EUR/USD from BTC/EUR divided by BTC/USD
     versus the ECB reference rate on the same calendar dates;
  2. cross-vendor agreement: Yahoo Finance vs CoinGecko for BTC-USD and
     Yahoo Finance vs ECB for EUR/USD;
  3. publication-calendar structure: ECB publishes working days only, while
     crypto markets quote every day, so weekend dates must appear in the
     crypto series and be absent from the ECB series.

Outputs: results/fx_triangulation.csv, results/fx_triangulation.json
Exit code 1 if the median absolute triangular deviation exceeds --tolerance-bps.
"""

import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

LIVE_FILES = {
    "ecb": "ecb_eurusd.json",
    "btc_usd": "coingecko_btc_usd.json",
    "btc_eur": "coingecko_btc_eur.json",
    "yahoo_fx": "yahoo_eurusd.json",
    "yahoo_btc": "yahoo_btc.json",
}


def load_live(data_dir):
    out = {}
    for key, name in LIVE_FILES.items():
        path = Path(data_dir) / name
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                out[key] = json.load(fh)
    return out


def series_map(doc, key):
    if doc is None:
        return {}
    return {row["date"]: float(row[key]) for row in doc.get("rates", doc.get("prices", []))}


def weekday_name(iso_date):
    return dt.date.fromisoformat(iso_date).strftime("%A")


def triangulate(live):
    ecb = series_map(live.get("ecb"), "rate")
    btc_usd = series_map(live.get("btc_usd"), "close")
    btc_eur = series_map(live.get("btc_eur"), "close")

    rows = []
    for date in sorted(set(btc_usd) | set(btc_eur)):
        usd = btc_usd.get(date)
        eur = btc_eur.get(date)
        implied = (usd / eur) if (usd and eur) else None
        rate = ecb.get(date)
        diff_bps = ((implied - rate) / rate * 1e4) if (implied and rate) else None
        rows.append(
            {
                "date": date,
                "weekday": weekday_name(date),
                "btc_usd": usd,
                "btc_eur": eur,
                "implied_eurusd": round(implied, 6) if implied else None,
                "ecb_eurusd": rate,
                "diff_bps": round(diff_bps, 2) if diff_bps is not None else None,
                "ecb_published": rate is not None,
            }
        )
    return rows


def summarize(rows, live, tolerance_bps):
    aligned = [r for r in rows if r["ecb_published"] and r["diff_bps"] is not None]
    deviations = [abs(r["diff_bps"]) for r in aligned]
    crypto_dates = {r["date"] for r in rows}
    ecb_dates = {r["date"] for r in rows if r["ecb_published"]}
    unpublished = sorted(crypto_dates - ecb_dates)

    summary = {
        "n_crypto_days": len(rows),
        "n_aligned_with_ecb": len(aligned),
        "n_crypto_days_without_ecb_fixing": len(unpublished),
        "unpublished_dates": unpublished,
        "unpublished_weekdays": sorted({weekday_name(d) for d in unpublished}),
        "median_abs_diff_bps": round(statistics.median(deviations), 2) if deviations else None,
        "max_abs_diff_bps": round(max(deviations), 2) if deviations else None,
        "signed_diffs_bps": [
            {"date": r["date"], "weekday": r["weekday"], "diff_bps": r["diff_bps"]}
            for r in aligned
        ],
        "tolerance_bps": tolerance_bps,
        "tolerance_passed": bool(deviations) and statistics.median(deviations) <= tolerance_bps,
    }

    yahoo_fx = live.get("yahoo_fx")
    if yahoo_fx and ecb_dates:
        last_ecb_date = max(ecb_dates)
        last_ecb = series_map(live.get("ecb"), "rate")[last_ecb_date]
        current = float(yahoo_fx["current"])
        summary["cross_vendor"] = {
            "ecb_last_date": last_ecb_date,
            "ecb_last_rate": last_ecb,
            "yahoo_fx_current": current,
            "yahoo_fx_vs_ecb_last_bps": round((current - last_ecb) / last_ecb * 1e4, 2),
            "yahoo_fx_last_close": yahoo_fx.get("last_close"),
            "yahoo_fx_last_close_vs_ecb_last_bps": round(
                (float(yahoo_fx["last_close"]) - last_ecb) / last_ecb * 1e4, 2
            )
            if yahoo_fx.get("last_close")
            else None,
            "note": "Vendor 'current' is intraday; ECB fixing is a ~16:00 CET snapshot, so some spread is expected.",
        }

    yahoo_btc = live.get("yahoo_btc")
    btc_usd_doc = live.get("btc_usd")
    if yahoo_btc and btc_usd_doc:
        last_date = max(r["date"] for r in btc_usd_doc["prices"])
        cg_last = series_map(btc_usd_doc, "close")[last_date]
        yc = float(yahoo_btc["current"])
        summary["cross_vendor"]["btc_usd"] = {
            "coingecko_last_date": last_date,
            "coingecko_last_close": cg_last,
            "yahoo_current": yc,
            "yahoo_vs_coingecko_bps": round((yc - cg_last) / cg_last * 1e4, 2),
        }

    summary["method"] = (
        "Triangular implied EUR/USD = 1 / (BTC_EUR / BTC_USD) computed on CoinGecko "
        "daily closes; compared against the same-date ECB reference rate. Crypto daily "
        "closes are 00:00 UTC snapshots while the ECB fixing is ~16:00 CET, so residual "
        "deviations mix genuine basis with timestamp misalignment."
    )
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="data/live")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--tolerance-bps", type=float, default=100.0)
    args = ap.parse_args(argv)

    live = load_live(args.data_dir)
    missing = [k for k in LIVE_FILES if k not in live]
    if missing:
        print(f"missing live snapshot files: {missing}", file=sys.stderr)

    rows = triangulate(live)
    summary = summarize(rows, live, args.tolerance_bps)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "fx_triangulation.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    json_path = out_dir / "fx_triangulation.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    print(json.dumps(summary, indent=2))
    print(f"wrote {csv_path} and {json_path}")

    return 0 if summary["tolerance_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
