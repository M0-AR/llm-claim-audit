#!/usr/bin/env python3
"""Assemble docs/assets/demo.gif from the PNG screenshots in docs/assets/frames/.

Frames are resized, quantized against one shared 256-color palette so colors
stay stable across the animation, and written with a fixed per-frame duration.
If the result exceeds the README budget the script retries at smaller widths.

Requires Pillow (pip install pillow).
"""

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install pillow")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FRAMES_DIR = ROOT / "docs" / "assets" / "frames"
OUT_PATH = ROOT / "docs" / "assets" / "demo.gif"
WIDTHS = (800, 720, 640)
DURATION_MS = 1200
TARGET_BYTES = 3_000_000


def load_frames():
    paths = sorted(FRAMES_DIR.glob("*.png"))
    if not paths:
        raise SystemExit(f"no PNG frames found in {FRAMES_DIR}")
    return [Image.open(path).convert("RGB") for path in paths]


def resize_all(frames, width):
    resized = []
    for im in frames:
        height = round(im.height * width / im.width)
        resized.append(im.resize((width, height), Image.Resampling.LANCZOS))
    return resized


def quantize_all(frames):
    total_height = sum(im.height for im in frames)
    strip = Image.new("RGB", (frames[0].width, total_height))
    y = 0
    for im in frames:
        strip.paste(im, (0, y))
        y += im.height
    palette = strip.quantize(colors=256)
    return [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in frames]


def main():
    frames = load_frames()
    for width in WIDTHS:
        quantized = quantize_all(resize_all(frames, width))
        quantized[0].save(
            OUT_PATH,
            save_all=True,
            append_images=quantized[1:],
            duration=DURATION_MS,
            loop=0,
            optimize=True,
        )
        size = OUT_PATH.stat().st_size
        print(
            f"{len(quantized)} frames at {width}px -> "
            f"{OUT_PATH.relative_to(ROOT)} ({size / 1e6:.2f} MB)"
        )
        if size <= TARGET_BYTES:
            return
    raise SystemExit(f"demo.gif still exceeds {TARGET_BYTES} bytes at the smallest width")


if __name__ == "__main__":
    main()
