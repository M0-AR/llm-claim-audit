#!/usr/bin/env python3
"""Generate the preregistered E5 arithmetic task set.

Frozen before any model contact: seed 20261017, 40 tasks of the form
12-digit multiplicand x 8-digit multiplier (multiplier uses each digit
2-9 exactly once, mirroring the video's 253,491,780-style example).
Writes harness/tasks.json next to this script.
"""

import json
import random
from pathlib import Path

SEED = 20261017
N_TASKS = 40
HERE = Path(__file__).resolve().parent


def main():
    rng = random.Random(SEED)
    tasks = []
    for i in range(1, N_TASKS + 1):
        a = rng.randint(100000000000, 999999999999)
        digits = list("23456789")
        rng.shuffle(digits)
        b = int("".join(digits))
        tasks.append({"task_id": i, "a": str(a), "b": str(b), "answer": str(a * b)})
    out = HERE / "tasks.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"seed": SEED, "generated": "2026-10-17", "prompt_template": "What is {a} times {b}? Reply with only the number.", "tasks": tasks}, fh, indent=2)
        fh.write("\n")
    print(f"wrote {out} ({len(tasks)} tasks, seed {SEED})")


if __name__ == "__main__":
    main()
