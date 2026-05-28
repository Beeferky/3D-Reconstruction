#!/usr/bin/env python3
"""
03 — M3: Structure-from-Motion via pycolmap incremental mapper.

Reads M2 artifacts (features.h5, matches.h5, pairs-netvlad.txt) and runs
COLMAP's incremental mapping to estimate camera intrinsics + extrinsics
(R, t) and triangulate a sparse 3D point cloud.

Writes:
  <output>/sparse/                  COLMAP model (cameras.bin, images.bin, points3D.bin)
  <output>/sparse_pointcloud.ply    PLY export of the sparse cloud
  <output>/txt/                     human-readable text export
  <output>/stats.json               registration rate / reprojection error / etc.

Example:
  python scripts/03_m3_sfm.py \\
      --images data/myscene/images \\
      --m2 outputs/m2_myscene \\
      --output outputs/m3_myscene
"""
import argparse
import json
from pathlib import Path

from hloc import reconstruction
import pycolmap  # noqa: F401  (ensures pycolmap is installed)


def parse_args():
    p = argparse.ArgumentParser(description="M3: pycolmap incremental SfM")
    p.add_argument("--images", required=True, type=Path,
                   help="Folder of input images (must match what M2 used)")
    p.add_argument("--m2", required=True, type=Path,
                   help="M2 output folder containing features.h5, matches.h5, pairs-netvlad.txt")
    p.add_argument("--output", required=True, type=Path,
                   help="Output folder for M3 (sparse model + stats)")
    p.add_argument("--min-num-matches", type=int, default=15,
                   help="Minimum verified matches required to register an image (default: 15)")
    p.add_argument("--no-refine-focal", action="store_true",
                   help="Disable BA refinement of focal length (default: enabled)")
    p.add_argument("--refine-principal-point", action="store_true",
                   help="Enable BA refinement of principal point (default: disabled)")
    return p.parse_args()


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    sfm_pairs = args.m2 / "pairs-netvlad.txt"
    features_path = args.m2 / "features.h5"
    matches_path = args.m2 / "matches.h5"
    sfm_dir = args.output / "sparse"

    for required in (sfm_pairs, features_path, matches_path):
        if not required.exists():
            raise SystemExit(f"Missing M2 artifact: {required}")

    mapper_options = {
        "ba_refine_focal_length": not args.no_refine_focal,
        "ba_refine_principal_point": args.refine_principal_point,
        "ba_refine_extra_params": True,
        "min_num_matches": args.min_num_matches,
    }

    print("=" * 60)
    print("M3: incremental Structure-from-Motion")
    print("=" * 60)

    model = reconstruction.main(
        sfm_dir, args.images, sfm_pairs, features_path, matches_path,
        mapper_options=mapper_options, verbose=True,
    )

    if model is None:
        print("\nReconstruction failed: COLMAP could not build any sparse model.")
        print("Likely causes: insufficient parallax (pure rotation), low overlap, "
              "or too few correspondences. See README 'Capture guidelines'.")
        return

    ply_path = args.output / "sparse_pointcloud.ply"
    model.export_PLY(str(ply_path))
    txt_dir = args.output / "txt"
    txt_dir.mkdir(exist_ok=True)
    model.write_text(str(txt_dir))

    n_in = sum(1 for p in args.images.iterdir() if p.is_file())
    n_reg = model.num_reg_images()
    stats = {
        "num_input_images": n_in,
        "num_registered_images": n_reg,
        "registration_rate": round(n_reg / max(n_in, 1), 4),
        "num_points3D": model.num_points3D(),
        "num_observations": model.compute_num_observations(),
        "mean_track_length": model.compute_mean_track_length(),
        "mean_reprojection_error_px": model.compute_mean_reprojection_error(),
    }
    print("\nM3 done.")
    for k, v in stats.items():
        print(f"  {k:32s} : {v}")

    with open(args.output / "stats.json", "w") as f:
        json.dump(
            {k: float(v) if isinstance(v, (int, float)) else v for k, v in stats.items()},
            f, indent=2,
        )
    print(f"\nSparse model : {sfm_dir}")
    print(f"PLY          : {ply_path}")
    print(f"Stats        : {args.output / 'stats.json'}")


if __name__ == "__main__":
    main()
