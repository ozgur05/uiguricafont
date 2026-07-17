"""Phase 4.6b: cluster decomposed pieces and rebuild the cluster set.

Input : decomposition.json, decomposed_segments/, clusters_refined.json,
        normalized/128 (for kept clusters' sheet images)
Output: decomposed_features.json, decomposed_normalized/{64,128}/
        updated_clusters.json      full cluster set:
                                     - non-word Phase 4.5 clusters kept as-is
                                     - word clusters replaced by clusters of
                                       their decomposed pieces
                                   each cluster: id, representative (medoid),
                                   size, visual type, internal similarity,
                                   homogeneity confidence, mixed flag+reason
        updated_clusters_report.txt
        updated_contact_sheets.pdf

Visual type is STRUCTURAL only (size/shape class), never an identity:
  diacritic / punctuation-like mark / letter candidate / letter fragment /
  word segment / unknown.
No classification, no Unicode, font untouched.
"""
import json
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.ndimage import gaussian_filter
from scipy.spatial.distance import pdist, squareform
from skimage.morphology import skeletonize

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SUB = os.path.join(BASE, "decomposed_segments")
DNRM = os.path.join(BASE, "decomposed_normalized")
for s in (64, 128):
    os.makedirs(os.path.join(DNRM, str(s)), exist_ok=True)

decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
refined = json.load(open(os.path.join(BASE, "clusters_refined.json"), encoding="utf-8"))
WORD_CLUSTERS = set(decomp["meta"]["word_clusters"])
pieces = decomp["pieces"]
N = len(pieces)


def zernike_magnitudes(img, order=8):
    h, w = img.shape
    ys, xs = np.mgrid[0:h, 0:w]
    x = (xs - (w - 1) / 2) / ((w - 1) / 2)
    y = (ys - (h - 1) / 2) / ((h - 1) / 2)
    rho = np.hypot(x, y)
    theta = np.arctan2(y, x)
    disk = rho <= 1.0
    wgt = img * disk
    mass = wgt.sum()
    if mass <= 0:
        return {}
    out = {}
    for n in range(order + 1):
        for m in range(n % 2, n + 1, 2):
            R = np.zeros_like(rho)
            for k in range((n - m) // 2 + 1):
                c = ((-1) ** k * math.factorial(n - k) /
                     (math.factorial(k) * math.factorial((n + m) // 2 - k) *
                      math.factorial((n - m) // 2 - k)))
                R += c * rho ** (n - 2 * k)
            V = R * np.exp(-1j * m * theta)
            A = (n + 1) / np.pi * (wgt * V)[disk].sum() / mass
            out[f"z{n}_{m}"] = round(float(abs(A)), 6)
    return out


# ---------- per-piece normalization + descriptors (Phase 3.5 recipe) ------
FEATS_PATH = os.path.join(BASE, "decomposed_features.json")
CACHED = os.path.exists(FEATS_PATH)
if CACHED:
    feats = json.load(open(FEATS_PATH, encoding="utf-8"))["segments"]
feats = feats if CACHED else []
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
for r in (pieces if not CACHED else []):
    im = Image.open(os.path.join(SUB, r["filename"])).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    alpha = a[:, :, 3]
    ys, xs = np.nonzero(alpha > 0)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    a = a[y0:y1, x0:x1]
    alpha = alpha[y0:y1, x0:x1]
    gray = a[:, :, :3].mean(axis=2)
    ink = (alpha / 255.0) * (1.0 - gray / 255.0)
    h, w = ink.shape
    mask = (alpha > 127).astype(np.uint8)

    norm128 = None
    for S in (64, 128):
        scale = S / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        ink_s = np.asarray(Image.fromarray((ink * 255).astype(np.uint8), "L")
                           .resize((nw, nh), Image.LANCZOS), np.float32) / 255.0
        canvas = np.zeros((S, S), np.float32)
        dx, dy = (S - nw) // 2, (S - nh) // 2
        canvas[dy:dy + nh, dx:dx + nw] = ink_s
        if S == 128:
            norm128 = canvas
        Image.fromarray((255 - canvas * 255).astype(np.uint8), "L").save(
            os.path.join(DNRM, str(S), r["filename"].replace("sub", "dnorm")))

    hu = cv2.HuMoments(cv2.moments(mask, binaryImage=True)).flatten()
    hu_log = [round(float(-np.sign(v) * np.log10(abs(v))), 6) if v != 0 else 0.0
              for v in hu]
    zern = zernike_magnitudes(norm128)

    cmask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cnts, hier = cv2.findContours(cmask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    n_holes = 0
    perim = 0.0
    if hier is not None:
        for i, c in enumerate(cnts):
            perim += cv2.arcLength(c, True)
            if hier[0][i][3] != -1:
                n_holes += 1
    area = float(cmask.sum())
    compact = float(4 * np.pi * area / perim ** 2) if perim > 0 else 0.0
    hull = cv2.convexHull(np.column_stack(np.nonzero(cmask)[::-1]))
    hull_area = float(cv2.contourArea(hull)) if len(hull) >= 3 else area
    solidity = area / hull_area if hull_area > 0 else 1.0
    ecc = 0.0
    big = max(cnts, key=cv2.contourArea) if cnts else None
    if big is not None and len(big) >= 5:
        _, (MA, ma), _ = cv2.fitEllipse(big)
        if max(MA, ma) > 0:
            b_, a_ = sorted((MA, ma))
            ecc = math.sqrt(max(0.0, 1 - (b_ / a_) ** 2))
    sk = skeletonize(cmask > 0)
    nb = cv2.filter2D(sk.astype(np.uint8), -1,
                      np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], np.uint8),
                      borderType=cv2.BORDER_CONSTANT)
    ends = int(((nb == 1) & sk).sum())
    branches = int(((nb >= 3) & sk).sum())

    feats.append({
        "filename": r["filename"], "parent": r["parent"],
        "parent_cluster": r["parent_cluster"], "page": r["page"],
        "bbox": r["bbox"], "trimmed_size": [int(w), int(h)],
        "hu_moments_log": hu_log, "zernike": zern,
        "contour": {"n_holes": n_holes, "compactness": round(compact, 5),
                    "solidity": round(solidity, 5),
                    "extent": round(area / (w * h), 5),
                    "eccentricity": round(ecc, 5)},
        "skeleton": {"endpoints": ends, "branchpoints": branches},
    })

if not CACHED:
    with open(FEATS_PATH, "w", encoding="utf-8") as f:
        json.dump({"meta": {"count": N, "recipe": "Phase 3.5 descriptors"},
                   "segments": feats}, f, indent=1)
print(f"features {'loaded from cache' if CACHED else 'computed'} for {N} pieces")

# ---------- feature matrix (Phase 4 weighting) ----------
img_vecs = np.zeros((N, 32 * 32), np.float32)
for i, s in enumerate(feats):
    im = Image.open(os.path.join(DNRM, "64", s["filename"].replace("sub", "dnorm")))
    a = 1.0 - np.asarray(im, np.float32) / 255.0
    a = gaussian_filter(a, 2.0)[::2, ::2]
    v = a.flatten()
    n = np.linalg.norm(v)
    img_vecs[i] = v / n if n > 0 else v

zernM = np.array([[s["zernike"][k] for k in sorted(s["zernike"])] for s in feats], np.float32)
huM = np.clip(np.array([s["hu_moments_log"] for s in feats], np.float32), -12, 12)
contM = np.array([[s["contour"]["compactness"], s["contour"]["solidity"],
                   s["contour"]["extent"], s["contour"]["eccentricity"],
                   min(s["contour"]["n_holes"], 12),
                   np.log1p(s["skeleton"]["endpoints"]),
                   np.log1p(s["skeleton"]["branchpoints"])] for s in feats], np.float32)
geomM = np.array([[np.log(max(s["trimmed_size"][0], 1) / max(s["trimmed_size"][1], 1)),
                   np.log(max(s["trimmed_size"][1], 1)),
                   np.log(max(s["trimmed_size"][0], 1))] for s in feats], np.float32)


def z(m):
    sd = m.std(axis=0)
    sd[sd == 0] = 1
    return (m - m.mean(axis=0)) / sd


X = np.hstack([3.0 * img_vecs, 1.0 * z(zernM) / np.sqrt(zernM.shape[1]),
               0.5 * z(huM) / np.sqrt(7), 1.0 * z(contM) / np.sqrt(7),
               2.0 * z(geomM) / np.sqrt(3)])
D = pdist(X, metric="cosine")
Z = linkage(D, method="average")
sqD = squareform(D)


def silhouette(labels):
    lab = np.asarray(labels)
    uniq = np.unique(lab)
    if len(uniq) < 2:
        return -1
    idx_by = {u: np.nonzero(lab == u)[0] for u in uniq}
    sample = np.random.RandomState(0).choice(len(lab), min(400, len(lab)), replace=False)
    vals = []
    for i in sample:
        own = idx_by[lab[i]]
        if len(own) < 2:
            continue
        a = sqD[i, own[own != i]].mean()
        b = min(sqD[i, idx_by[u]].mean() for u in uniq if u != lab[i])
        vals.append((b - a) / max(a, b))
    return float(np.mean(vals)) if vals else -1


# selection: among thresholds within 0.03 silhouette of the best, take the
# FEWEST clusters — raw argmax always picks the tightest threshold and
# shatters the pieces into ~200 near-singleton groups, which defeats
# "repeated visual prototype" evidence. Parsimony within a statistical tie.
scan = []
for t in np.arange(0.08, 0.62, 0.02):
    labels = fcluster(Z, t, criterion="distance")
    k = int(labels.max())
    if not (15 <= k <= 250):
        continue
    s = silhouette(labels)
    print(f"t={t:.2f} k={k} sil={s:.3f}")
    scan.append((s, k, t, labels))
smax = max(e[0] for e in scan)
s, k, t, labels = min((e for e in scan if e[0] >= smax - 0.03),
                      key=lambda e: e[1])
print(f"selected t={t:.2f}: {k} piece clusters, silhouette={s:.3f} "
      f"(best sil {smax:.3f}; parsimony rule)")

# ---------- visual type heuristics (structural, not identity) ----------
def cluster_type(medw, medh, med_branch, med_ends):
    if medw < 60 and medh < 60:
        return "diacritic"
    if medw < 90 and medh < 90 and med_branch == 0:
        return "punctuation-like mark"
    if medw >= 300 and medw / max(medh, 1) >= 2.2:
        return "word segment"
    if med_branch == 0 and med_ends <= 2 and (medw / max(medh, 1) > 3
                                              or medh / max(medw, 1) > 3):
        return "letter fragment"
    if 60 <= medw < 300:
        return "letter candidate"
    return "unknown"


def confidence(intra):
    return round(max(0.0, min(1.0, 1.0 - intra / 0.15)), 2)


updated = {}
uid = 0

# piece clusters
for cid in range(1, k + 1):
    mem = np.nonzero(labels == cid)[0]
    sub = sqD[np.ix_(mem, mem)]
    medoid = int(mem[sub.sum(axis=0).argmin()])
    intra = float(sub.mean()) if len(mem) > 1 else 0.0
    mx = float(sub.max()) if len(mem) > 1 else 0.0
    medw = float(np.median([feats[i]["trimmed_size"][0] for i in mem]))
    medh = float(np.median([feats[i]["trimmed_size"][1] for i in mem]))
    mbr = float(np.median([feats[i]["skeleton"]["branchpoints"] for i in mem]))
    men = float(np.median([feats[i]["skeleton"]["endpoints"] for i in mem]))
    conf = confidence(intra)
    mixed = intra > 0.11 or mx > 0.25
    updated[f"updated_{uid:03d}"] = {
        "source": "decomposed pieces",
        "size": int(len(mem)),
        "representative": feats[medoid]["filename"],
        "representative_dir": "decomposed_segments",
        "type": cluster_type(medw, medh, mbr, men),
        "internal_similarity": round(1.0 - intra, 4),
        "homogeneity_confidence": conf,
        "mixed_flag": bool(mixed),
        "mixed_reason": (f"mean intra distance {intra:.3f} / max {mx:.3f} "
                         "exceeds homogeneity gate (0.11 / 0.25)"
                         if mixed else None),
        "median_width": int(medw), "median_height": int(medh),
        "variance": round(float(sub.var()), 5) if len(mem) > 1 else 0.0,
        "members": [feats[i]["filename"] for i in mem],
    }
    uid += 1

# kept (non-word) Phase 4.5 clusters, passed through unchanged
for name, c in refined["clusters"].items():
    if name in WORD_CLUSTERS:
        continue
    intra = c["mean_intra_distance"]
    medw, medh = c["median_width"], c["median_height"]
    typ = ("diacritic" if medw < 60 and medh < 60 else
           "punctuation-like mark" if medw < 90 and medh < 90 else
           "letter fragment" if (medw / max(medh, 1) > 3 or
                                 medh / max(medw, 1) > 3) else
           "letter candidate" if medw < 300 else "unknown")
    mixed = intra > 0.11 or c["max_intra_distance"] > 0.25
    updated[f"updated_{uid:03d}"] = {
        "source": f"unchanged from {name} (Phase 4.5)",
        "size": c["size"],
        "representative": c["medoid"],
        "representative_dir": "segments",
        "type": typ,
        "internal_similarity": round(1.0 - intra, 4),
        "homogeneity_confidence": confidence(intra),
        "mixed_flag": bool(mixed),
        "mixed_reason": (f"mean intra distance {intra:.3f} / max "
                         f"{c['max_intra_distance']:.3f} exceeds gate"
                         if mixed else None),
        "median_width": medw, "median_height": medh,
        "variance": None,
        "members": c["members"],
    }
    uid += 1

with open(os.path.join(BASE, "updated_clusters.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "n_clusters": uid,
        "piece_clusters": k, "kept_clusters": uid - k,
        "piece_cluster_threshold": round(float(t), 2),
        "piece_silhouette": round(s, 3),
        "n_pieces": N,
        "note": ("types are structural shape classes, NOT identities; "
                 "no Unicode, no contextual forms")},
        "clusters": updated}, f, indent=1)

# ---------- report ----------
words = decomp["words"]
n_split = sum(1 for w in words if w["n_pieces"] > 1)
with open(os.path.join(BASE, "updated_clusters_report.txt"), "w", encoding="utf-8") as f:
    f.write("Phase 4.6: word decomposition + updated cluster set\n\n")
    f.write(f"words processed:        {len(words)}\n")
    f.write(f"words split:            {n_split}\n")
    f.write(f"words left unsplit:     {len(words) - n_split}\n")
    f.write(f"new glyph candidates:   {N} pieces -> {k} piece clusters "
            f"(t={t:.2f}, silhouette={s:.3f})\n")
    f.write(f"kept Phase 4.5 clusters: {uid - k}\n")
    f.write(f"total updated clusters: {uid}\n\n")
    f.write("UNSPLIT WORDS AND WHY:\n")
    for w in words:
        if w["n_pieces"] == 1:
            f.write(f"  {w['parent']}: {w['unsplit_reason']}\n")
    f.write("\nSPLIT CONFIDENCES:\n")
    for w in words:
        for c in w["cuts"]:
            f.write(f"  {w['parent']} x={c['x_trimmed']} "
                    f"conf={c['confidence']} run={c['run_px']}px "
                    f"extent={c['extent_px']}px\n")
    f.write(f"\n{'cluster':13} {'size':>4} {'sim':>6} {'conf':>5} "
            f"{'mixed':>5}  type / representative\n")
    for n, c in updated.items():
        f.write(f"{n:13} {c['size']:>4} {c['internal_similarity']:>6} "
                f"{c['homogeneity_confidence']:>5} "
                f"{'YES' if c['mixed_flag'] else '-':>5}  "
                f"{c['type']} / {c['representative']}\n")

# ---------- contact sheets PDF ----------
pages = []
for n, c in updated.items():
    files = c["members"][:40]
    cols = 8
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 132, rows * 132 + 40), "white")
    dr = ImageDraw.Draw(sheet)
    for j, fn in enumerate(files):
        if c["representative_dir"] == "decomposed_segments":
            p = os.path.join(DNRM, "128", fn.replace("sub", "dnorm"))
        else:
            p = os.path.join(BASE, "normalized", "128", fn.replace("glyph", "norm"))
        im = Image.open(p).convert("RGB").resize((128, 128))
        sheet.paste(im, ((j % cols) * 132 + 2, (j // cols) * 132 + 38))
    dr.text((6, 4), f"{n} size={c['size']} type={c['type']} "
            f"sim={c['internal_similarity']} conf={c['homogeneity_confidence']}"
            f"{' MIXED' if c['mixed_flag'] else ''}", fill=(0, 0, 0))
    dr.text((6, 18), f"source: {c['source']}", fill=(80, 80, 80))
    pages.append(sheet)
W = max(p.width for p in pages)
H = max(p.height for p in pages)
pages = [p if p.size == (W, H) else
         (lambda q: (q.paste(p, (0, 0)), q)[1])(Image.new("RGB", (W, H), "white"))
         for p in pages]
pages[0].save(os.path.join(BASE, "updated_contact_sheets.pdf"), save_all=True,
              append_images=pages[1:], resolution=120)
print(f"updated_clusters.json ({uid} clusters), report, "
      f"updated_contact_sheets.pdf ({len(pages)} pages)")
