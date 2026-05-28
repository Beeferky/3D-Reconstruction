# 3D Reconstruction Pipeline · 三维重建流水线

> **Filtering + HLOC + COLMAP** — end-to-end from raw photos to a sparse / dense 3D reconstruction.
> **筛选 + HLOC + COLMAP** —— 从原始照片到稀疏 / 稠密三维重建的端到端流水线。

Drop your own photos in, run four commands, get a 3D reconstruction.
把你的照片放进去、跑四条命令、得到三维重建。

---

## 1 · What it does · 这套流水线在做什么

```
Photos (HEIC / JPG / PNG)
   │  [01] preprocess.py    — convert + EXIF-rotate + resize + quality score + filter
   ▼
data/<scene>/images/
   │  [02] m2_hloc.py       — NetVLAD retrieval → SuperPoint → LightGlue → pycolmap verify
   ▼
M2 features + matches + verified pairs
   │  [03] m3_sfm.py        — pycolmap incremental Structure-from-Motion
   ▼
Sparse model (camera poses R, t  + 3D points)
   │  [04] dense_mvs.sh     — COLMAP PatchMatch + StereoFusion       (optional)
   ▼
Dense point cloud (fused.ply)
```

| Stage 阶段 | Tooling 工具 | Output 产出 |
|---|---|---|
| **01 Filter** 筛选 | OpenCV (Laplacian / Canny / histogram) | Resized JPGs + quality scores CSV |
| **02 M2** 匹配 | hloc (NetVLAD + SuperPoint + LightGlue) + pycolmap | features.h5, matches.h5, database.db |
| **03 M3** SfM 稀疏重建 | pycolmap incremental mapper | Sparse model + PLY + stats.json |
| **04 Dense MVS** 稠密化 | COLMAP CLI (PatchMatch + StereoFusion) | fused.ply (dense cloud) |

---

## 2 · Installation · 安装

```bash
git clone https://github.com/Beeferky/3D-Reconstruction.git
cd 3D-Reconstruction

# Create the conda env. This installs hloc straight from GitHub via pip.
# 创建 conda 环境。hloc 通过 pip 从 GitHub 安装。
conda env create -f environment.yml
conda activate 3dreconstruction
```

**Stage 04 (dense MVS) additionally requires the COLMAP CLI** built with CUDA — install it separately following <https://colmap.github.io>. Stages 01–03 do **not** need the COLMAP CLI (pycolmap is enough).
**第 04 步（稠密 MVS）额外需要带 CUDA 的 COLMAP 命令行工具**，按 <https://colmap.github.io> 单独安装。前 01–03 步**不需要** COLMAP CLI（pycolmap 就够了）。

---

## 3 · Quick start · 快速上手（4 条命令）

```bash
# (0) Put your raw photos somewhere · 把原始照片放到任意目录
ls /path/to/raw_photos/
# IMG_0001.HEIC  IMG_0002.HEIC  ...

# (1) Preprocess + quality filter
#     EN: HEIC→JPG, resize to 2856 px long edge, drop blurriest images.
#     ZH: HEIC 转 JPG, 缩到 2856 长边, 剔除模糊度低于阈值的图。
python scripts/01_preprocess.py \
    --input  /path/to/raw_photos \
    --output data/myscene \
    --min-sharpness 50

# (2) M2: feature extraction + matching (~minutes, needs 1 GPU)
python scripts/02_m2_hloc.py \
    --images data/myscene/images \
    --output outputs/m2_myscene

# (3) M3: Structure-from-Motion (~minutes, CPU/GPU)
python scripts/03_m3_sfm.py \
    --images data/myscene/images \
    --m2     outputs/m2_myscene \
    --output outputs/m3_myscene

# (4) Dense MVS (optional, ~tens of minutes, needs COLMAP CLI + GPU)
bash scripts/04_dense_mvs.sh \
    data/myscene/images \
    outputs/m3_myscene/sparse \
    outputs/dense_myscene
```

That's it. The final products are:
就这样。最终产物：

* `outputs/m3_myscene/sparse_pointcloud.ply` — sparse cloud 稀疏点云
* `outputs/m3_myscene/stats.json` — registration rate, reprojection error, etc. 注册率、重投影误差等
* `outputs/dense_myscene/fused.ply` — dense cloud (if step 4 was run) 稠密点云

Open the `.ply` files in **MeshLab**, **CloudCompare**, or any 3D viewer.
用 **MeshLab** / **CloudCompare** 等三维查看器打开 `.ply`。

---

## 4 · Input requirements · 输入要求

The pipeline assumes a standard photogrammetry capture. The most important rules (consistent with COLMAP author's [tutorial](https://colmap.github.io/tutorial.html)):

| Requirement 要求 | Why · 为什么 |
|---|---|
| **Translate the camera, do not stand and rotate.** 相机要平移，不要原地转身。 | Pure rotation gives zero baseline → essential matrix `E = [t]×R` degenerates → SfM cannot triangulate depth. |
| **High visual overlap (~70%); each 3D point seen in ≥ 3 images.** 相邻图重叠 70%, 每个点至少被 3 张图看到。 | More observations → more stable triangulation, fewer floaters. |
| **Sharp images, consistent lighting, fixed focal length.** 图要清晰、光照恒定、固定焦距。 | Motion blur / exposure jumps break feature matching. |
| **Avoid mirrors, screens, large blank walls.** 避开镜子、屏幕、大片白墙。 | Reflective and textureless surfaces break the photometric-consistency assumption. |

Bad capture → registration drops, reprojection error rises, or reconstruction fails entirely. The pipeline cannot fix what the camera failed to capture.
拍得差 → 注册率下降、误差上升、甚至完全失败。流水线**修不了**采集阶段就丢掉的信息。

---

## 5 · Configuration reference · 参数参考

### 01 preprocess

| Flag | Default | Meaning |
|---|---|---|
| `--input` | (req) | Folder of raw photos. 原始照片目录 |
| `--output` | (req) | Output dataset folder. 输出目录 |
| `--max-dim` | 2856 | Resize longest edge (px). 缩放长边像素 |
| `--min-sharpness` | 0 | Drop images with Laplacian variance below this. 拉普拉斯方差阈值 |
| `--min-edge-ratio` | 0 | Drop images with Canny edge density below this. Canny 边缘比阈值 |
| `--max-overexposure` | 1.0 | Drop if fraction of pixels >250 exceeds this. 过曝阈值 |
| `--max-underexposure` | 1.0 | Drop if fraction of pixels <5 exceeds this. 欠曝阈值 |
| `--no-montage` | off | Skip thumbnail-grid generation. 跳过缩略图拼图 |

### 02 m2_hloc

| Flag | Default | Meaning |
|---|---|---|
| `--images` | (req) | Filtered images dir (output of step 01). 第1步筛选后的 images 目录 |
| `--output` | (req) | M2 output dir. M2 输出目录 |
| `--num-matched` | 30 | NetVLAD top-K candidate pairs per image (auto-capped to N-1). NetVLAD 每张图保留的候选邻居数 |

### 03 m3_sfm

| Flag | Default | Meaning |
|---|---|---|
| `--images` | (req) | Same images dir used in M2. 与 M2 一致的 images 目录 |
| `--m2` | (req) | M2 output dir. M2 输出目录 |
| `--output` | (req) | M3 output dir. M3 输出目录 |
| `--min-num-matches` | 15 | Minimum verified matches to register an image. 注册一张图所需最少匹配数 |
| `--no-refine-focal` | off | Disable BA refinement of focal length. 关闭 BA 焦距精化 |
| `--refine-principal-point` | off | Enable BA refinement of principal point. 开启主点精化 |

### 04 dense_mvs.sh

```bash
bash scripts/04_dense_mvs.sh <images_dir> <sparse_dir> <output_dir> [max_image_size=2560]
# Multi-GPU PatchMatch:
CUDA_VISIBLE_DEVICES=0,1,2,3 bash scripts/04_dense_mvs.sh ...
```

---

## 6 · Output structure · 输出结构

```
data/<scene>/
├── images_all/      All converted JPGs (sequential rename)   全部转换后的 JPG
├── images/          Filtered subset used downstream           筛选后用于重建的子集
├── scores.csv       Per-image quality scores                  逐图质量打分
└── sharpness_sorted.jpg   Thumbnail grid sorted by sharpness  按模糊度排序的缩略图

outputs/m2_<scene>/
├── global-feats-netvlad.h5     NetVLAD descriptors
├── pairs-netvlad.txt           Candidate image pairs
├── features.h5                 SuperPoint keypoints + descriptors
├── matches.h5                  LightGlue matches
└── database.db                 COLMAP database (verified)

outputs/m3_<scene>/
├── sparse/                     COLMAP binary model (cameras / images / points3D)
├── txt/                        Human-readable export
├── sparse_pointcloud.ply       Sparse cloud (PLY)
└── stats.json                  Registration rate, reproj error, num points, ...

outputs/dense_<scene>/
└── fused.ply                   Dense fused cloud
```

---

## 7 · Reading the metrics · 怎么看指标

`outputs/m3_<scene>/stats.json` gives you the standard SfM quality numbers:

| Metric | Good 良好范围 | What it tells you |
|---|---|---|
| `registration_rate` | ≥ 0.85 | Fraction of input images registered. 注册成功的比例 |
| `mean_reprojection_error_px` | < 2.0 | Geometric accuracy of triangulated points. 三角化几何精度 |
| `mean_track_length` | ≥ 3.0 | Average number of views per 3D point. 每点平均被几张图看到 |
| `num_points3D` | scene-dependent | Sparse cloud size. 稀疏点云规模 |

Low registration rate or huge reprojection error usually means a capture problem (insufficient parallax, blur, low overlap) — see §4.
注册率低/误差大通常是采集问题（视差不足、模糊、重叠少）—— 参见第 4 节。

---

## 8 · Common pitfalls · 常见坑

| Symptom 现象 | Likely cause 可能原因 | Fix 怎么改 |
|---|---|---|
| `Could not reconstruct any model!` | Pure rotation, no baseline. 纯旋转无基线 | Move the camera between shots (orbit, don't spin). |
| Very low registration (< 30%) | Low overlap / not enough images. 重叠不足/图太少 | Shoot more frames with 70%+ overlap. |
| Dense PLY has huge holes on walls | Textureless surfaces. 大面积无纹理 | Add posters / capture more variety; expected on plain walls. |
| iPhone HEIC not loading | `pillow-heif` missing. | `conda env update -f environment.yml`. |

---

## 9 · Acknowledgments · 致谢

This pipeline integrates established open-source components:

* **[hloc · Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization)** — Sarlin et al., *From Coarse to Fine: Robust Hierarchical Localization at Large Scale*, CVPR 2019.
* **[NetVLAD](https://www.di.ens.fr/willow/research/netvlad/)** — Arandjelović et al., CVPR 2016.
* **[SuperPoint](https://github.com/magicleap/SuperPointPretrainedNetwork)** — DeTone et al., CVPRW 2018.
* **[LightGlue](https://github.com/cvg/LightGlue)** — Lindenberger et al., ICCV 2023.
* **[COLMAP](https://colmap.github.io/) / [pycolmap](https://github.com/colmap/pycolmap)** — Schönberger & Frahm, *Structure-from-Motion Revisited*, CVPR 2016; Schönberger et al., *Pixelwise View Selection for Unstructured MVS*, ECCV 2016.

---

## 10 · License · 许可证

MIT — see [`LICENSE`](./LICENSE).
