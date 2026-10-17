#!/usr/bin/env python3
"""Fetch live market data (no API keys) for the E2 triangulation.

Sources:
  - ECB reference rates via Frankfurter (api.frankfurter.dev, fallback api.frankfurter.app)
  - CoinGecko simple market chart (BTC in USD and EUR)
  - Yahoo Finance v8 chart (EURUSD=X, BTC-USD) as an independent cross-vendor quote

Writes the same JSON schema as the frozen snapshots in data/live/, plus a
manifest.json with SHA-256 hashes. Retries with backoff on transient errors;
exits non-zero if any source failed.
"""

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "llm-claims-lab/1.0 (+research; contact in repo)"}


def get_json(url, tries=3, backoff=2.0, timeout=25):
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as err:
            last_err = err
            if attempt < tries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"failed after {tries} tries: {url}: {last_err}")


def iso_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_ecb(days=14):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    endpoints = [
        f"https://api.frankfurter.dev/v1/{start}..{end}?base=EUR&symbols=USD",
        f"https://api.frankfurter.app/{start}..{end}?from=EUR&to=USD",
    ]
    errors = []
    for url in endpoints:
        try:
            doc = get_json(url)
            if "app" in url:
                rates = doc["rates"]
            else:
                rates = doc["rates"]
            rows = [
                {"date": d, "rate": float(v["USD"])}
                for d, v in sorted(rates.items())
                if v.get("USD") is not None
            ]
            return {
                "source": "European Central Bank reference rates via Frankfurter API",
                "endpoint": url,
                "retrieved_via": "scripts/fetch_live.py (urllib)",
                "fetched_at": iso_now(),
                "base": "EUR",
                "quote": "USD",
                "publication_rule": "ECB reference rates are published around 16:00 CET on working days only; no weekend or TARGET holiday values exist.",
                "rates": rows,
            }
        except RuntimeError as err:
            errors.append(str(err))
    raise RuntimeError("ECB fetch failed: " + " | ".join(errors))


def fetch_coingecko(vs, days=7):
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        f"?vs_currency={vs}&days={days}&interval=daily"
    )
    doc = get_json(url)
    per_day = {}
    for ts_ms, price in doc["prices"]:
        date = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).date().isoformat()
        per_day[date] = float(price)
    rows = [{"date": d, "close": per_day[d]} for d in sorted(per_day)]
    return {
        "source": "CoinGecko",
        "endpoint": url,
        "retrieved_via": "scripts/fetch_live.py (urllib)",
        "fetched_at": iso_now(),
        "coin": "bitcoin",
        "quote": vs,
        "prices": rows,
    }


def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    doc = get_json(url)
    meta = doc["chart"]["result"][0]["meta"]
    return {
        "source": "Yahoo Finance v8 API",
        "endpoint": url,
        "retrieved_via": "scripts/fetch_live.py (urllib)",
        "fetched_at": iso_now(),
        "symbol": symbol,
        "current": float(meta["regularMarketPrice"]),
        "last_close": float(meta.get("chartPreviousClose", meta.get("previousClose", 0.0))) or None,
        "market_time_unix": int(meta["regularMarketTime"]),
        "quote_currency": meta.get("currency"),
    }


def sha256_of(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="data/live")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    jobs = {
        "ecb_eurusd.json": lambda: fetch_ecb(days=max(args.days, 14)),
        "coingecko_btc_usd.json": lambda: fetch_coingecko("usd", args.days),
        "coingecko_btc_eur.json": lambda: fetch_coingecko("eur", args.days),
        "yahoo_eurusd.json": lambda: fetch_yahoo("EURUSD=X"),
        "yahoo_btc.json": lambda: fetch_yahoo("BTC-USD"),
    }

    failures = []
    written = []
    for name, job in jobs.items():
        try:
            doc = job()
            path = out / name
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2)
                fh.write("\n")
            written.append(name)
            print(f"ok   {name}")
        except Exception as err:  # noqa: BLE001 - report every source failure, keep going
            failures.append(f"{name}: {err}")
            print(f"FAIL {name}: {err}", file=sys.stderr)

    manifest = {
        "fetched_at": iso_now(),
        "files": {name: sha256_of(out / name) for name in written},
        "failures": failures,
    }
    if written:
        with open(out / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")

    if failures:
        print(f"{len(failures)} source(s) failed; {len(written)} written", file=sys.stderr)
        return 1
    print(f"all {len(written)} snapshots written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
