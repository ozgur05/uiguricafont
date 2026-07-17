"""Phase 4.5 validation metrics: Phase 4 partition vs refined partition.

Computes on the identical feature space:
  - mean silhouette (full, exact — 1057 points is fine)
  - per-cluster mean silhouette
  - Davies-Bouldin-style medoid separation ratio
Appends results to refinement_report.txt.
"""
import json
import os

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
feats = json.load(open(os.path.join(BASE, "segment_features.json"), encoding="utf-8"))["segments"]
by_name = {s["filename"]: i for i, s in enumerate(feats)}
N = len(feats)

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
hu = np.clip(np.array([s["hu_moments_log"] for s in feats], np.float32), -12, 12)
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


X = np.hstack([3.0 * img_vecs, 1.0 * z(zern) / np.sqrt(zern.shape[1]),
               0.5 * z(hu) / np.sqrt(7), 1.0 * z(cont) / np.sqrt(7),
               2.0 * z(geom) / np.sqrt(3)])
Xn = X / np.linalg.norm(X, axis=1, keepdims=True)
D = 1.0 - Xn @ Xn.T
np.fill_diagonal(D, 0.0)


def labels_from(cjson, key):
    data = json.load(open(os.path.join(BASE, cjson), encoding="utf-8"))
    lab = np.full(N, -1, int)
    for k, (name, c) in enumerate(sorted(data[key].items())):
        for f in c["members"]:
            lab[by_name[f]] = k
    return lab, data


def silhouette(lab):
    """Mean silhouette over points in clusters of size >= 2 (exact)."""
    vals = []
    ks = [k for k in np.unique(lab) if k >= 0]
    idx = {k: np.where(lab == k)[0] for k in ks}
    for k in ks:
        mem = idx[k]
        if len(mem) < 2:
            continue
        for i in mem:
            a = D[i, mem].sum() / (len(mem) - 1)
            b = min(D[i, idx[k2]].mean() for k2 in ks if k2 != k and len(idx[k2]) > 0)
            vals.append((b - a) / max(a, b))
    return float(np.mean(vals)), len(vals)


lab4, _ = labels_from("clusters.json", "clusters")
lab45, ref = labels_from("clusters_refined.json", "clusters")

s4, n4 = silhouette(lab4)
s45, n45 = silhouette(lab45)

# medoid separation: min inter-medoid distance / max intra mean, per partition
def sep(lab):
    ks = [k for k in np.unique(lab) if k >= 0]
    meds, intras = [], []
    for k in ks:
        mem = np.where(lab == k)[0]
        m = mem[int(D[np.ix_(mem, mem)].sum(axis=0).argmin())]
        meds.append(m)
        intras.append(D[mem, m].mean() if len(mem) > 1 else 0.0)
    inter = min(D[meds[a], meds[b]] for a in range(len(meds))
                for b in range(a + 1, len(meds)))
    return float(inter), float(max(intras))


i4, x4 = sep(lab4)
i45, x45 = sep(lab45)

lines = [
    "",
    "VALIDATION METRICS (identical feature space, exact full silhouette):",
    f"  Phase 4  : 36 clusters | silhouette={s4:.4f} over {n4} pts | "
    f"min inter-medoid={i4:.4f} | worst intra-mean={x4:.4f}",
    f"  Phase 4.5: {ref['meta']['n_clusters']} clusters | silhouette={s45:.4f} over {n45} pts | "
    f"min inter-medoid={i45:.4f} | worst intra-mean={x45:.4f}",
    f"  quarantined (excluded from refined partition): {ref['meta']['n_quarantined']}",
]
with open(os.path.join(BASE, "refinement_report.txt"), "a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
