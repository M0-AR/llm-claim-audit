#!/usr/bin/env python3
"""E4: re-enact the video's token-count demonstration with the real tokenizer.

The video counts 15 tokens for a haiku request, 19 tokens for the reply and
42 tokens for the chat-formatted exchange, with a ~200k-token vocabulary.
The fetched transcript window does not preserve the exact punctuation of the
original strings, so an exact reproduction of (15, 19, 42) is impossible from
public data; this script instead reproduces the *method* with best-effort
reconstructions and verifies the vocabulary-size claim against the shipped
tokenizer (tiktoken o200k_base, the GPT-4o encoding).

Requires: tiktoken (see requirements.txt). Skips gracefully without it.
Outputs: results/token_reenactment.json
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

QUERY_RECONSTRUCTION = "give me a haiku about what it's like to be a large language model"
RESPONSE_RECONSTRUCTION = (
    "words flow like a stream, endless echo, never mind - ghost of thought unseen"
)
VIDEO_CLAIM = {"query_tokens": 15, "response_tokens": 19, "chat_total_tokens": 42}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="results")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "token_reenactment.json"

    try:
        import tiktoken
    except ImportError:
        doc = {
            "skipped": True,
            "reason": "tiktoken not installed; run: pip install -r requirements.txt",
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        print("tiktoken not available; wrote skipped marker")
        return 0

    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception as err:  # noqa: BLE001 - encoder file unavailable (e.g. offline, no cache)
        doc = {
            "skipped": True,
            "reason": f"encoder file unavailable: {err}",
            "hint": "Docker image bakes the cache at build time (TIKTOKEN_CACHE_DIR); on a host, run once with network access.",
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        print(f"encoder unavailable ({err}); wrote skipped marker")
        return 0
    vocab_size = None
    try:
        vocab_size = len(enc._mergeable_ranks)
    except AttributeError:
        pass
    try:
        vocab_size_total = enc.n_vocab
    except AttributeError:
        vocab_size_total = None

    query_tokens = enc.encode(QUERY_RECONSTRUCTION, disallowed_special=())
    response_tokens = enc.encode(RESPONSE_RECONSTRUCTION, disallowed_special=())
    chat_text = (
        "<|im_start|>user\n"
        + QUERY_RECONSTRUCTION
        + "<|im_end|>\n<|im_start|>assistant\n"
        + RESPONSE_RECONSTRUCTION
        + "<|im_end|>\n"
    )
    chat_tokens = enc.encode(chat_text, disallowed_special=())

    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tiktoken_version": tiktoken.__version__,
        "encoding": "o200k_base",
        "vocab_size_mergeable_ranks": vocab_size,
        "vocab_size_total": vocab_size_total,
        "vocabulary_claim": "~200,000",
        "vocabulary_claim_holds": bool(
            (vocab_size_total or vocab_size)
            and abs((vocab_size_total or vocab_size) - 200000) / 200000 < 0.01
        ),
        "query": {"reconstruction": QUERY_RECONSTRUCTION, "tokens": len(query_tokens)},
        "response": {"reconstruction": RESPONSE_RECONSTRUCTION, "tokens": len(response_tokens)},
        "chat_formatted": {
            "template": "<|im_start|>role\\n content...<|im_end|>",
            "tokens": len(chat_tokens),
        },
        "video_claim": VIDEO_CLAIM,
        "chat_special_token_overhead": len(chat_tokens) - len(query_tokens) - len(response_tokens),
        "verdict": (
            "Method reproduced end to end with the shipped GPT-4o tokenizer. Exact claim "
            "triple (15, 19, 42) is not reproducible without the verbatim original strings; "
            "the reconstruction demonstrates the same turn-structure arithmetic plus the "
            "chat-format overhead of special tokens."
        ),
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

    print(json.dumps(doc, indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
