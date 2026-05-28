#!/usr/bin/env python3
"""
01 — Image preprocessing + quality filtering.

Reads HEIC / JPG / PNG photos from --input, converts to JPG, applies EXIF
rotation, resizes the longest edge to --max-dim, and scores each image with:
  * Variance of Laplacian  (out-of-focus / motion blur)
  * Canny edge density     (low-texture / blank-wall detection)
  * Saturated/dark pixel ratios (over-/under-exposure)

Writes:
  <output>/images_all/IMG_00001.jpg ...      all converted, renamed sequentially
  <output>/images/IMG_*.jpg                  filtered subset (passed thresholds)
  <output>/scores.csv                        per-image quality scores
  <output>/sharpness_sorted.jpg              thumbnail grid sorted by sharpness

Example:
  python scripts/01_preprocess.py \\
      --input /path/to/raw_photos \\
      --output data/myscene \\
      --min-sharpness 50
"""
import argparse
import csv
import shutil
from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageDraw, ImageFont, ImageOps

pillow_heif.register_heif_opener()


def parse_args():
    p = argparse.ArgumentParser(
        description="Image preprocessing + quality filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", required=True, type=Path,
                   help="Folder containing raw photos (HEIC/JPG/PNG)")
    p.add_argument("--output", required=True, type=Path,
                   help="Output dataset folder (will create images_all/, images/)")
    p.add_argument("--max-dim", type=int, default=2856,
                   help="Resize longest edge to this many pixels (default: 2856)")
    p.add_argument("--min-sharpness", type=float, default=0.0,
                   help="Drop images with Laplacian variance < this (default 0 = keep all)")
    p.add_argument("--min-edge-ratio", type=float, default=0.0,
                   help="Drop images with Canny edge fraction < this (default 0)")
    p.add_argument("--max-overexposure", type=float, default=1.0,
                   help="Drop images with > this fraction of pixels > 250 (default 1.0)")
    p.add_argument("--max-underexposure", type=float, default=1.0,
                   help="Drop images with > this fraction of pixels < 5 (default 1.0)")
    p.add_argument("--no-montage", action="store_true",
                   help="Skip thumbnail grid generation (faster)")
    return p.parse_args()


def score_image(im_pil):
    arr = cv2.cvtColor(np.array(im_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 50, 150)
    return {
        "sharpness": round(sharpness, 1),
        "edge_ratio": round(float((edges > 0).mean()), 4),
        "over_exp": round(float((gray > 250).mean()), 4),
        "under_exp": round(float((gray < 5).mean()), 4),
    }


def make_montage(rows, images_all_dir, out_path):
    THUMB_W, COLS, PAD, LABEL_H = 220, 10, 4, 28
    n_rows = (len(rows) + COLS - 1) // COLS
    sample = Image.open(images_all_dir / rows[0]["file"])
    th_guess = int(THUMB_W * sample.height / sample.width)
    cell_h = th_guess + LABEL_H
    canvas = Image.new(
        "RGB",
        (COLS * (THUMB_W + PAD) + PAD, n_rows * (cell_h + PAD) + PAD),
        (30, 30, 30),
    )
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12
        )
    except Exception:
        font = ImageFont.load_default()
    for idx, r in enumerate(rows):
        t = Image.open(images_all_dir / r["file"])
        th = int(THUMB_W * t.height / t.width)
        t = t.resize((THUMB_W, th), Image.LANCZOS)
        cx = PAD + (idx % COLS) * (THUMB_W + PAD)
        cy = PAD + (idx // COLS) * (cell_h + PAD)
        canvas.paste(t, (cx, cy))
        label = f"{r['file'].replace('.jpg', '')} S{r['sharpness']:.0f}"
        draw.text((cx + 2, cy + th + 1), label, fill=(255, 255, 0), font=font)
    canvas.save(out_path, "JPEG", quality=85)


def main():
    args = parse_args()
    images_all = args.output / "images_all"
    images_kept = args.output / "images"
    images_all.mkdir(parents=True, exist_ok=True)
    images_kept.mkdir(parents=True, exist_ok=True)
    for f in images_kept.glob("*.jpg"):
        f.unlink()

    exts = ("HEIC", "heic", "JPG", "jpg", "JPEG", "jpeg", "PNG", "png")
    srcs = sorted({p for ext in exts for p in args.input.glob(f"*.{ext}")})
    if not srcs:
        print(f"No images found in {args.input}")
        return

    print(f"Found {len(srcs)} images in {args.input}\n")
    rows = []
    for i, src in enumerate(srcs, 1):
        out_jpg = images_all / f"IMG_{i:05d}.jpg"
        try:
            im = Image.open(src)
            im = ImageOps.exif_transpose(im)
            if im.mode != "RGB":
                im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, args.max_dim / max(w, h))
            if scale < 1.0:
                im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            im.save(out_jpg, "JPEG", quality=92)
            scores = score_image(im)
            rows.append({
                "src": src.name, "file": out_jpg.name,
                "w": im.size[0], "h": im.size[1],
                **scores,
            })
            if i % 20 == 0 or i == len(srcs):
                print(f"  [{i}/{len(srcs)}] {src.name} sharp={scores['sharpness']:.0f}")
        except Exception as e:
            print(f"  WARN  {src.name}: {e}")

    if not rows:
        print("No images successfully converted.")
        return

    kept = [
        r for r in rows
        if r["sharpness"] >= args.min_sharpness
        and r["edge_ratio"] >= args.min_edge_ratio
        and r["over_exp"] <= args.max_overexposure
        and r["under_exp"] <= args.max_underexposure
    ]
    for r in kept:
        shutil.copy2(images_all / r["file"], images_kept / r["file"])

    rows_sorted = sorted(rows, key=lambda r: r["sharpness"])
    csv_path = args.output / "scores.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_sorted[0].keys()))
        w.writeheader()
        w.writerows(rows_sorted)

    if not args.no_montage:
        make_montage(rows_sorted, images_all, args.output / "sharpness_sorted.jpg")

    sharps = np.array([r["sharpness"] for r in rows])
    print("\n=== Summary ===")
    print(f"  converted : {len(rows)}")
    print(f"  kept      : {len(kept)} (dropped {len(rows) - len(kept)})")
    print(
        f"  sharpness : P0={np.percentile(sharps, 0):.0f}  "
        f"P25={np.percentile(sharps, 25):.0f}  P50={np.percentile(sharps, 50):.0f}  "
        f"P75={np.percentile(sharps, 75):.0f}  P100={np.percentile(sharps, 100):.0f}"
    )
    print(f"  all       : {images_all}")
    print(f"  filtered  : {images_kept}")
    print(f"  scores    : {csv_path}")
    if not args.no_montage:
        print(f"  montage   : {args.output / 'sharpness_sorted.jpg'}")


if __name__ == "__main__":
    main()
