#!/usr/bin/env python3
"""E5 runner: sends the preregistered arithmetic tasks to a chat endpoint.

OpenAI-compatible /chat/completions API. Configuration via environment:
  OPENAI_API_KEY   required; runner exits 2 without it (preregistered, not executed)
  OPENAI_MODEL     required model id (e.g. gpt-4o-mini, gpt-5-thinking)
  OPENAI_BASE_URL  optional, defaults to https://api.openai.com/v1

Writes one JSONL record per task (prompt inputs, raw reply, timing).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def call_api(base_url, api_key, model, prompt, timeout=180):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    return doc, time.time() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", default=str(HERE / "tasks.json"))
    ap.add_argument("--out", default="results/harness_responses.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N tasks (debug)")
    args = ap.parse_args(argv)

    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if not api_key or not model:
        print("OPENAI_API_KEY / OPENAI_MODEL not set; E5 is preregistered (harness/preregistration.md) but not executed.")
        print("Usage: OPENAI_API_KEY=... OPENAI_MODEL=<model> python3 harness/runner.py")
        return 2

    with open(args.tasks, encoding="utf-8") as fh:
        bundle = json.load(fh)
    tasks = bundle["tasks"]
    if args.limit:
        tasks = tasks[: args.limit]
    template = bundle["prompt_template"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for task in tasks:
            prompt = template.format(a=task["a"], b=task["b"])
            try:
                doc, secs = call_api(base_url, api_key, model, prompt)
                text = doc["choices"][0]["message"].get("content") or ""
                record = dict(task, model=model, prompt=prompt, response=text, seconds=round(secs, 2), ok=True)
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as err:
                record = dict(task, model=model, prompt=prompt, error=str(err), ok=False)
            fh.write(json.dumps(record) + "\n")
            print(task["task_id"], record.get("response", record.get("error")))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
