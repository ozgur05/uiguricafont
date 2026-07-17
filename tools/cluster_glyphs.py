"""Phase 4: cluster glyph segments by shape similarity.

NO classification, NO Unicode assignment - clusters are anonymous shape
groups (cluster_000, cluster_001, ...) for later human/expert review.

Features per segment (weighted, z-scored):
  A. image vector: 64x64 normalized ink, Gaussian-blurred (sigma=2),
     downsampled to 32x32, L2-normalized  -> captures letterform
  B. Zernike magnitudes (25)              -> rotation-robust shape
  C. Hu log moments (7)
  D. contour scalars: compactness, solidity, extent, eccentricity,
     n_holes (capped), skeleton endpoints/branchpoints (log)
  E. geometry: log aspect ratio, log trimmed height, log trimmed width
     (true physical size matters: diacritic dot vs letter vs word)

Clustering: agglomerative (average linkage, cosine distance) with a
distance threshold; scanned over thresholds, picked by silhouette.
Outputs:
  clusters.json          cluster -> members, medoid, stats
  clusters_report.txt    summary table
  qa/cluster_sheets/     one contact sheet PNG per cluster (largest 40)
"""
import json
import os

import numpy as np
from PIL import Image
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.ndimage import gaussian_filter
from scipy.spatial.distance import pdist, squareform

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
feats = json.load(open(os.path.join(BASE, "segment_features.json"), encoding="utf-8"))["segments"]
N = len(feats)

# ---------- feature matrix ----------
img_vecs = np.zeros((N, 32 * 32), np.float32)
for i, s in enumerate(feats):
    im = Image.open(os.path.join(BASE, "normalized", "64",
                                 s["filename"].replace("glyph", "norm")))
    a = 1.0 - np.asarray(im, np.float32) / 255.0
    a = gaussian_filter(a, 2.0)[::2, ::2]
    v = a.flatten()
    n = np.linalg.norm(v)
    img_vecs[i] = v / n if n > 0 else v

zern = np.array([[s["zernike"][k] for k in sorted(s["zernike"])] for s in feats], np.float32)
hu = np.array([s["hu_moments_log"] for s in feats], np.float32)
hu = np.clip(hu, -12, 12)
cont = np.array([[s["contour"]["compactness"], s["contour"]["solidity"],
                  s["contour"]["extent"], s["contour"]["eccentricity"],
                  min(s["contour"]["n_holes"], 12),
                  np.log1p(s["skeleton"]["endpoints"]),
                  np.log1p(s["skeleton"]["branchpoints"])] for s in feats], np.float32)
geom = np.array([[np.log(max(s["trimmed_size"][0], 1) / max(s["trimmed_size"][1], 1)),
                  np.log(max(s["trimmed_size"][1], 1)),
                  np.log(max(s["trimmed_size"][0], 1))] for s in feats], np.float32)


def z(m):
    sd = m.std(axis=0)
    sd[sd == 0] = 1
    return (m - m.mean(axis=0)) / sd


# weights: image dominates; geometry strongly separates dots/letters/words
X = np.hstack([
    3.0 * img_vecs,          # already L2-normalized rows
    1.0 * z(zern) / np.sqrt(zern.shape[1]),
    0.5 * z(hu) / np.sqrt(7),
    1.0 * z(cont) / np.sqrt(7),
    2.0 * z(geom) / np.sqrt(3),
])

D = pdist(X, metric="cosine")
Z = linkage(D, method="average")

# ---------- threshold scan, silhouette-selected ----------
from collections import Counter


def silhouette(labels, sqD):
    # sample-based silhouette on the precomputed distance matrix
    lab = np.asarray(labels)
    uniq = np.unique(lab)
    if len(uniq) < 2:
        return -1
    sil = []
    idx_by = {u: np.nonzero(lab == u)[0] for u in uniq}
    sample = np.random.RandomState(0).choice(len(lab), min(400, len(lab)), replace=False)
    for i in sample:
        own = idx_by[lab[i]]
        if len(own) < 2:
            continue
        a = sqD[i, own[own != i]].mean()
        b = min(sqD[i, idx_by[u]].mean() for u in uniq if u != lab[i])
        sil.append((b - a) / max(a, b))
    return float(np.mean(sil)) if sil else -1


sqD = squareform(D)
best = None
for t in np.arange(0.08, 0.62, 0.02):
    labels = fcluster(Z, t, criterion="distance")
    k = int(labels.max())
    sizes = Counter(labels)
    singletons = sum(1 for v in sizes.values() if v == 1)
    if not (25 <= k <= 300):
        continue
    s = silhouette(labels, sqD)
    print(f"t={t:.2f} clusters={k} singletons={singletons} silhouette={s:.3f}")
    if best is None or s > best[0]:
        best = (s, t, labels)

s, t, labels = best
k = int(labels.max())
print(f"\nselected t={t:.2f}: {k} clusters, silhouette={s:.3f}")

# ---------- second level: refine large/loose clusters ----------
# A single global threshold cannot serve 30px dots and 2500px words at
# once: long multi-letter segments agglomerate into one "is a word"
# cluster. Any cluster that is both large and internally loose is
# re-clustered at a tighter threshold (complete linkage for compactness).
REFINE_SIZE = 40
REFINE_INTRA = 0.10
REFINE_T = 0.28  # complete-linkage cosine threshold within subcluster

final_labels = np.zeros(N, dtype=int)
next_id = 0
for cid in range(1, k + 1):
    members = np.nonzero(labels == cid)[0]
    sub = sqD[np.ix_(members, members)]
    intra = float(sub.mean()) if len(members) > 1 else 0.0
    if len(members) >= REFINE_SIZE and intra > REFINE_INTRA:
        subZ = linkage(squareform(sub, checks=False), method="complete")
        sublab = fcluster(subZ, REFINE_T, criterion="distance")
        print(f"  refined cluster {cid} (size {len(members)}, intra {intra:.3f})"
              f" -> {sublab.max()} subclusters")
        for sc in range(1, int(sublab.max()) + 1):
            for m in members[sublab == sc]:
                final_labels[m] = next_id
            next_id += 1
    else:
        for m in members:
            final_labels[m] = next_id
        next_id += 1

k = next_id
labels = final_labels + 1
print(f"after refinement: {k} clusters")

# ---------- outputs ----------
clusters = {}
for cid in range(1, k + 1):
    members = np.nonzero(labels == cid)[0]
    sub = sqD[np.ix_(members, members)]
    medoid = int(members[sub.sum(axis=0).argmin()])
    heights = [feats[i]["trimmed_size"][1] for i in members]
    widths = [feats[i]["trimmed_size"][0] for i in members]
    clusters[f"cluster_{cid - 1:03d}"] = {
        "size": int(len(members)),
        "medoid": feats[medoid]["filename"],
        "mean_intra_distance": round(float(sub.mean()), 4),
        "median_width": int(np.median(widths)),
        "median_height": int(np.median(heights)),
        "pages": sorted({feats[i]["page"] for i in members}),
        "members": [feats[i]["filename"] for i in members],
    }

ordered = dict(sorted(clusters.items(), key=lambda kv: -kv[1]["size"]))
with open(os.path.join(BASE, "clusters.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {"n_segments": N, "n_clusters": k,
                        "distance_threshold": round(float(t), 2),
                        "silhouette": round(s, 3),
                        "linkage": "average", "metric": "cosine",
                        "note": "anonymous shape clusters; no classification"},
               "clusters": ordered}, f, indent=1)

# report
with open(os.path.join(BASE, "clusters_report.txt"), "w", encoding="utf-8") as f:
    f.write(f"Phase 4 clustering: {N} segments -> {k} clusters "
            f"(t={t:.2f}, silhouette={s:.3f})\n\n")
    f.write(f"{'cluster':14} {'size':>5} {'medW':>6} {'medH':>6} {'intraD':>7}  medoid\n")
    for name, c in ordered.items():
        f.write(f"{name:14} {c['size']:>5} {c['median_width']:>6} "
                f"{c['median_height']:>6} {c['mean_intra_distance']:>7}  {c['medoid']}\n")

# contact sheet per cluster
SHEETDIR = os.path.join(BASE, "qa", "cluster_sheets")
os.makedirs(SHEETDIR, exist_ok=True)
for name, c in ordered.items():
    files = c["members"][:40]
    cols = 8
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("L", (cols * 132, rows * 132 + 30), 255)
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for j, fn in enumerate(files):
        im = Image.open(os.path.join(BASE, "normalized", "128",
                                     fn.replace("glyph", "norm"))).resize((128, 128))
        sheet.paste(im, ((j % cols) * 132 + 2, (j // cols) * 132 + 32))
    d.text((6, 6), f"{name}  size={c['size']}  medoid={c['medoid']}", fill=0)
    sheet.save(os.path.join(SHEETDIR, f"{name}.png"))

print(f"clusters.json, clusters_report.txt, {len(ordered)} cluster sheets written")
