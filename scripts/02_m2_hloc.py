#!/usr/bin/env python3
"""
02 — M2: HLOC feature extraction + matching.

  NetVLAD image retrieval (top-K candidate pairs)
  -> SuperPoint local features
  -> LightGlue matching
  -> pycolmap geometric verification (Essential/Fundamental + RANSAC)

Writes:
  <output>/global-feats-netvlad.h5
  <output>/pairs-netvlad.txt
  <output>/features.h5
  <output>/matches.h5
  <output>/database.db

Example:
  python scripts/02_m2_hloc.py \\
      --images data/myscene/images \\
      --output outputs/m2_myscene
"""
import argparse
import sqlite3
from pathlib import Path

from hloc import extract_features, match_features, pairs_from_retrieval
from hloc.triangulation import (
    estimation_and_geometric_verification,
    import_features,
    import_matches,
)
from hloc.reconstruction import create_empty_db, import_images
import pycolmap


def parse_args():
    p = argparse.ArgumentParser(description="M2: HLOC features + matching")
    p.add_argument("--images", required=True, type=Path,
                   help="Folder of input images (filtered set, e.g. data/myscene/images)")
    p.add_argument("--output", required=True, type=Path,
                   help="Output folder for M2 artifacts")
    p.add_argument("--num-matched", type=int, default=30,
                   help="NetVLAD top-K candidate pairs per image (default: 30, "
                        "auto-capped to N-1 for tiny sets)")
    return p.parse_args()


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    images = args.images
    outputs = args.output
    sfm_pairs = outputs / "pairs-netvlad.txt"
    features_path = outputs / "features.h5"
    matches_path = outputs / "matches.h5"
    database_path = outputs / "database.db"

    retrieval_conf = extract_features.confs["netvlad"]
    feature_conf = extract_features.confs["superpoint_aachen"]
    matcher_conf = match_features.confs["superpoint+lightglue"]

    img_files = [p for p in images.iterdir() if p.is_file()]
    img_count = len(img_files)
    if img_count < 2:
        raise SystemExit(f"Need >= 2 images in {images}, found {img_count}.")
    num_matched = min(args.num_matched, img_count - 1)

    print("=" * 60)
    print(f"M2 (HLOC): SuperPoint + LightGlue, {img_count} images, top-{num_matched}")
    print("=" * 60)

    print("\n[1/5] NetVLAD retrieval features...")
    retrieval_path = extract_features.main(retrieval_conf, images, outputs)

    print(f"\n[2/5] Candidate pairs (top-{num_matched})...")
    pairs_from_retrieval.main(retrieval_path, sfm_pairs, num_matched=num_matched)

    print("\n[3/5] SuperPoint local features...")
    extract_features.main(feature_conf, images, outputs, feature_path=features_path)

    print("\n[4/5] LightGlue matching...")
    match_features.main(matcher_conf, sfm_pairs,
                        features=features_path, matches=matches_path)

    print("\n[5/5] Geometric verification (pycolmap)...")
    if database_path.exists():
        database_path.unlink()
    create_empty_db(database_path)
    import_images(images, database_path, camera_mode=pycolmap.CameraMode.AUTO)

    image_ids = {}
    conn = sqlite3.connect(str(database_path))
    cur = conn.cursor()
    cur.execute("SELECT image_id, name FROM images;")
    for r in cur.fetchall():
        image_ids[r[1]] = r[0]
    conn.close()

    with pycolmap.Database.open(database_path) as db:
        import_features(image_ids, db, features_path)
        import_matches(image_ids, db, sfm_pairs, matches_path,
                       min_match_score=None, skip_geometric_verification=False)
    estimation_and_geometric_verification(database_path, sfm_pairs, verbose=True)

    print(f"\nM2 done. Artifacts: {outputs}")


if __name__ == "__main__":
    main()
