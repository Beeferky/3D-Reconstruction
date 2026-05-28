#!/usr/bin/env bash
# 04 — Dense MVS via COLMAP CLI (PatchMatch + StereoFusion).
#
# Requires:
#   * COLMAP binary on PATH (built with CUDA). See https://colmap.github.io
#
# Usage:
#   bash scripts/04_dense_mvs.sh <images_dir> <sparse_dir> <output_dir> [max_image_size]
#
# Example:
#   bash scripts/04_dense_mvs.sh \\
#       data/myscene/images \\
#       outputs/m3_myscene/sparse \\
#       outputs/dense_myscene
#
# Optionally set CUDA_VISIBLE_DEVICES for multi-GPU PatchMatch:
#   CUDA_VISIBLE_DEVICES=0,1,2,3 bash scripts/04_dense_mvs.sh ...
#
# Output:
#   <output_dir>/fused.ply — dense fused point cloud
#
set -e

IMAGES_DIR="${1:?images_dir required}"
SPARSE_DIR="${2:?sparse_dir required}"
DENSE_DIR="${3:?output_dir required}"
MAX_IMAGE_SIZE="${4:-2560}"
GPU_LIST="${CUDA_VISIBLE_DEVICES:-0}"

# If sparse_dir has numbered submodels (sparse/0/), prefer the first one
[ -d "$SPARSE_DIR/0" ] && SPARSE_DIR="$SPARSE_DIR/0"

if ! command -v colmap >/dev/null 2>&1; then
    echo "ERROR: 'colmap' binary not found on PATH."
    echo "       Install COLMAP with CUDA support: https://colmap.github.io"
    exit 1
fi

rm -rf "$DENSE_DIR"
mkdir -p "$DENSE_DIR"

echo "============================================================"
echo "Dense MVS"
echo "  images       : $IMAGES_DIR"
echo "  sparse       : $SPARSE_DIR"
echo "  output       : $DENSE_DIR"
echo "  max_image_sz : $MAX_IMAGE_SIZE"
echo "  GPUs         : $GPU_LIST"
echo "============================================================"

echo ""
echo "===== Step 1/3: image_undistorter ====="
colmap image_undistorter \
    --image_path "$IMAGES_DIR" \
    --input_path "$SPARSE_DIR" \
    --output_path "$DENSE_DIR" \
    --output_type COLMAP \
    --max_image_size "$MAX_IMAGE_SIZE"

echo ""
echo "===== Step 2/3: patch_match_stereo (GPUs: $GPU_LIST) ====="
colmap patch_match_stereo \
    --workspace_path "$DENSE_DIR" \
    --workspace_format COLMAP \
    --PatchMatchStereo.geom_consistency true \
    --PatchMatchStereo.gpu_index "$GPU_LIST" \
    --PatchMatchStereo.num_iterations 5

echo ""
echo "===== Step 3/3: stereo_fusion ====="
colmap stereo_fusion \
    --workspace_path "$DENSE_DIR" \
    --workspace_format COLMAP \
    --input_type geometric \
    --output_path "$DENSE_DIR/fused.ply"

echo ""
echo "Dense MVS done."
echo "PLY: $DENSE_DIR/fused.ply"
