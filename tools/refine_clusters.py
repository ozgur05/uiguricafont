"""Phase 4.5: validate and refine Phase 4 clusters.

Input : clusters.json (Phase 4), segment_features.json, normalized/64
Output: clusters_refined.json, refinement_report.txt,
        qa/refined_sheets/ (sheets for every refined cluster)

Steps (all on the same feature space as Phase 4, rebuilt identically):
  1. VALIDATE  per-cluster: intra distances, medoid, silhouette per member
  2. OUTLIERS  member is an outlier if dist(member, own medoid) >
               max(OUT_ABS, mean + 2*std of its cluster's medoid distances)
  3. REASSIGN  outlier moves to the cluster of its nearest medoid if that
               distance < REASSIGN_MAX and clearly better (20% margin);
               otherwise it goes to quarantine (unclustered pool)
  4. MERGE     two clusters merge if medoid distance < MERGE_T and the
               merged mean intra distance stays below INTRA_CAP
  5. REPORT    every action logged; before/after metrics

No classification, no Unicode. Cluster IDs are re-issued as
refined_000... ordered by size; mapping to Phase 4 IDs is recorded.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
OUT_ABS = 0.22       # absolute outlier distance floor
REASSIGN_MAX = 0.18  # max distance to adopt an outlier
MARGIN = 0.8         # new medoid must be this fraction of old distance
MERGE_T = 0.15       # medoid-medoid distance to consider merging
INTRA_CAP = 0.14     # merged cluster must stay at least this coherent

feats = json.load(open(os.path.join(BASE, "segment_features.json"), encoding="utf-8"))["segments"]
phase4 = json.load(open(os.path.join(BASE, "clusters.json"), encoding="utf-8"))
by_name = {s["filename"]: i for i, s in enumerate(feats)}
N = len(feats)

# ---- rebuild Phase 4 feature space (identical construction) ----
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


def cdist(i, j):
    return float(1.0 - Xn[i] @ Xn[j])


# ---- load Phase 4 clusters ----
clusters = {}  # phase4 name -> list of feature indices
for name, c in phase4["clusters"].items():
    clusters[name] = [by_name[f] for f in c["members"]]

log = []
report_before = {n: len(m) for n, m in clusters.items()}


def medoid_of(members):
    if len(members) == 1:
        return members[0]
    sub = np.array([[cdist(i, j) for j in members] for i in members])
    return members[int(sub.sum(axis=0).argmin())]


# ---- 1+2: validate, find outliers ----
quarantine = []
outliers_per = {}
for name in list(clusters):
    members = clusters[name]
    if len(members) < 3:
        continue
    med = medoid_of(members)
    d = np.array([cdist(i, med) for i in members])
    thr = max(OUT_ABS, float(d.mean() + 2 * d.std()))
    out = [members[j] for j in range(len(members)) if d[j] > thr]
    if out:
        outliers_per[name] = out
        clusters[name] = [m for m in members if m not in out]
        for o in out:
            log.append(f"OUTLIER {feats[o]['filename']} left {name} "
                       f"(d={cdist(o, med):.3f} > thr={thr:.3f})")

# ---- 3: reassign or quarantine ----
medoids = {n: medoid_of(m) for n, m in clusters.items() if m}
for name, outs in outliers_per.items():
    for o in outs:
        old_d = cdist(o, medoids[name]) if name in medoids else 9.9
        best_n, best_d = None, 9.9
        for n2, med2 in medoids.items():
            d2 = cdist(o, med2)
            if d2 < best_d:
                best_n, best_d = n2, d2
        if best_d < REASSIGN_MAX and best_d < MARGIN * old_d and best_n != name:
            clusters[best_n].append(o)
            log.append(f"REASSIGN {feats[o]['filename']} -> {best_n} (d={best_d:.3f})")
        else:
            quarantine.append(o)
            log.append(f"QUARANTINE {feats[o]['filename']} (best d={best_d:.3f})")

# ---- 4: merge near-duplicate clusters ----
names = [n for n in clusters if clusters[n]]
merged_into = {}
changed = True
while changed:
    changed = False
    names = [n for n in clusters if clusters[n]]
    medoids = {n: medoid_of(clusters[n]) for n in names}
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            na, nb = names[a], names[b]
            dm = cdist(medoids[na], medoids[nb])
            if dm < MERGE_T:
                cand = clusters[na] + clusters[nb]
                med = medoid_of(cand)
                intra = float(np.mean([cdist(i, med) for i in cand]))
                if intra < INTRA_CAP:
                    log.append(f"MERGE {nb} into {na} (medoid d={dm:.3f}, "
                               f"merged intra={intra:.3f})")
                    clusters[na] = cand
                    clusters[nb] = []
                    merged_into[nb] = na
                    changed = True
                    break
        if changed:
            break

# ---- 5: emit refined clusters ----
final = [(n, m) for n, m in clusters.items() if m]
final.sort(key=lambda kv: -len(kv[1]))
refined = {}
mapping = {}
for idx, (old, members) in enumerate(final):
    med = medoid_of(members)
    d = [cdist(i, med) for i in members]
    rname = f"refined_{idx:03d}"
    mapping[old] = rname
    refined[rname] = {
        "size": len(members),
        "from_phase4": [old] + [k for k, v in merged_into.items() if v == old],
        "medoid": feats[med]["filename"],
        "mean_intra_distance": round(float(np.mean(d)), 4),
        "max_intra_distance": round(float(np.max(d)), 4),
        "median_width": int(np.median([feats[i]["trimmed_size"][0] for i in members])),
        "median_height": int(np.median([feats[i]["trimmed_size"][1] for i in members])),
        "pages": sorted({feats[i]["page"] for i in members}),
        "members": [feats[i]["filename"] for i in members],
    }

qrec = [feats[i]["filename"] for i in quarantine]
with open(os.path.join(BASE, "clusters_refined.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "source": "clusters.json (Phase 4)",
        "n_segments": N,
        "n_clusters": len(refined),
        "n_quarantined": len(qrec),
        "params": {"outlier_abs": OUT_ABS, "reassign_max": REASSIGN_MAX,
                   "margin": MARGIN, "merge_t": MERGE_T, "intra_cap": INTRA_CAP},
        "note": "anonymous shape clusters; no classification"},
        "clusters": refined, "quarantine": qrec}, f, indent=1)

with open(os.path.join(BASE, "refinement_report.txt"), "w", encoding="utf-8") as f:
    f.write(f"Phase 4.5 refinement: {len(report_before)} -> {len(refined)} clusters, "
            f"{len(qrec)} quarantined\n\nACTIONS ({len(log)}):\n")
    for line in log:
        f.write("  " + line + "\n")
    f.write(f"\n{'cluster':14} {'size':>5} {'intra':>7} {'max':>7}  medoid        from\n")
    for n, c in refined.items():
        f.write(f"{n:14} {c['size']:>5} {c['mean_intra_distance']:>7} "
                f"{c['max_intra_distance']:>7}  {c['medoid']}  {','.join(c['from_phase4'])}\n")

# sheets
SHEET = os.path.join(BASE, "qa", "refined_sheets")
os.makedirs(SHEET, exist_ok=True)
for n, c in refined.items():
    files = c["members"][:40]
    cols, rows = 8, (min(len(files), 40) + 7) // 8
    sheet = Image.new("L", (cols * 132, rows * 132 + 30), 255)
    dr = ImageDraw.Draw(sheet)
    for j, fn in enumerate(files):
        im = Image.open(os.path.join(BASE, "normalized", "128",
                                     fn.replace("glyph", "norm"))).resize((128, 128))
        sheet.paste(im, ((j % cols) * 132 + 2, (j // cols) * 132 + 32))
    dr.text((6, 6), f"{n} size={c['size']} intra={c['mean_intra_distance']} "
            f"from={','.join(c['from_phase4'])}", fill=0)
    sheet.save(os.path.join(SHEET, f"{n}.png"))
if quarantine:
    files = qrec[:40]
    cols, rows = 8, (len(files) + 7) // 8
    sheet = Image.new("L", (cols * 132, rows * 132 + 30), 255)
    dr = ImageDraw.Draw(sheet)
    for j, fn in enumerate(files):
        im = Image.open(os.path.join(BASE, "normalized", "128",
                                     fn.replace("glyph", "norm"))).resize((128, 128))
        sheet.paste(im, ((j % cols) * 132 + 2, (j // cols) * 132 + 32))
    dr.text((6, 6), f"quarantine size={len(qrec)}", fill=0)
    sheet.save(os.path.join(SHEET, "quarantine.png"))

print(f"refined: {len(refined)} clusters, {len(qrec)} quarantined, "
      f"{len(log)} actions -> clusters_refined.json")
