"""Phase 4.6a: decompose word clusters into letter-level subunits.

Input : clusters_refined.json (Phase 4.5), segments/*.png, segment_features.json
Output: decomposed_segments/subNNNNNN.png  (RGBA, exact ink, transparent bg)
        decomposition.json          (per-piece provenance + per-word cuts,
                                     confidence per cut, unsplit reasons)
        qa/decomposition/*.png      (cut-overlay QA for sampled words)

Word clusters := (median_width >= 200 AND w/h >= 1.8) OR median_width >= 300.
This excludes the single-stroke clusters (final tails 128px, slivers 146px)
and all diacritic/dot clusters.

Cutting (per word, on 5x5-closed mask to bridge halftone noise):
  t        = 4 * median(distance transform at ink)      [stroke thickness]
  column is CONNECTOR iff its ink forms ONE vertical band (gaps < 3px merged)
             of extent <= EXTENT_F * t
  a run of >= MIN_RUN connector columns yields one cut at its thinnest column
  pieces narrower than MIN_PIECE_F * t are merged into their narrower neighbor

Each candidate cut gets a CONFIDENCE in [0,1]:
  conf = 0.5 * run_score  (run length vs 50px; longer flat = more likely a
                           true inter-letter connector)
       + 0.5 * thin_score (extent at cut vs stroke t; a bare single-stroke
                           baseline scores 1, a 2t-thick junction scores 0)
Cuts below CONF_MIN are NOT applied; a word whose every candidate fails
the gate is left unchanged and the reason is recorded. Pieces are
anonymous subunits; no classification, no Unicode.
"""
import json
import os

import cv2
import numpy as np
from PIL import Image

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SUB = os.path.join(BASE, "decomposed_segments")
QA = os.path.join(BASE, "qa", "decomposition")
os.makedirs(SUB, exist_ok=True)
os.makedirs(QA, exist_ok=True)

EXTENT_F = 2.0    # connector column: ink extent <= this * stroke
BAND_GAP = 3      # vertical ink gaps below this merge into one band
MIN_RUN = 20      # connector run length (px) required for a cut candidate
CONF_MIN = 0.40   # apply a cut only at/above this confidence
MIN_PIECE_F = 2.5 # minimum piece width in stroke units
QA_EVERY = 8      # save every Nth cut word as overlay QA

refined = json.load(open(os.path.join(BASE, "clusters_refined.json"), encoding="utf-8"))
feats = json.load(open(os.path.join(BASE, "segment_features.json"), encoding="utf-8"))["segments"]
finfo = {s["filename"]: s for s in feats}

word_clusters = {}
for name, c in refined["clusters"].items():
    r = c["median_width"] / max(c["median_height"], 1)
    if (c["median_width"] >= 200 and r >= 1.8) or c["median_width"] >= 300:
        word_clusters[name] = c["members"]
n_words = sum(len(m) for m in word_clusters.values())
print(f"word clusters: {sorted(word_clusters)} -> {n_words} words")


def column_bands(col):
    """number of ink bands (gaps < BAND_GAP merged) and total extent."""
    ys = np.flatnonzero(col)
    if len(ys) == 0:
        return 0, 0
    gaps = np.diff(ys)
    return int(1 + (gaps >= BAND_GAP).sum()), int(ys[-1] - ys[0] + 1)


pieces = []
word_records = []
counter = 0
qa_saved = 0
word_idx = 0

for cname in sorted(word_clusters):
    for fname in word_clusters[cname]:
        word_idx += 1
        im = Image.open(os.path.join(BASE, "segments", fname)).convert("RGBA")
        arr = np.asarray(im)
        alpha = arr[:, :, 3]
        ys, xs = np.nonzero(alpha > 0)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        arr = arr[y0:y1, x0:x1]
        alpha = alpha[y0:y1, x0:x1]
        mask = (alpha > 127).astype(np.uint8)
        H, W = mask.shape

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        cmask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        dt = cv2.distanceTransform(cmask, cv2.DIST_L2, 5)
        ink_dt = dt[cmask > 0]
        t = 4.0 * float(np.median(ink_dt)) if len(ink_dt) else 12.8

        # connector columns
        conn = np.zeros(W, bool)
        for x in range(W):
            nb, ext = column_bands(cmask[:, x])
            if nb == 1 and ext <= EXTENT_F * t:
                conn[x] = True

        # runs -> cut candidates at thinnest column, with confidence
        candidates = []  # (cut_x, confidence, run_len, extent_at_cut)
        rejected = []
        x = 0
        while x < W:
            if conn[x]:
                x2 = x
                while x2 + 1 < W and conn[x2 + 1]:
                    x2 += 1
                run = x2 - x + 1
                if run >= MIN_RUN:
                    seg_counts = cmask[:, x:x2 + 1].sum(axis=0)
                    cx = x + int(seg_counts.argmin())
                    _, ext = column_bands(cmask[:, cx])
                    run_score = min(1.0, run / 50.0)
                    thin_score = max(0.0, min(1.0, (EXTENT_F * t - ext) /
                                              max(EXTENT_F * t - t, 1.0)))
                    conf = round(0.5 * run_score + 0.5 * thin_score, 3)
                    (candidates if conf >= CONF_MIN else rejected).append(
                        (cx, conf, run, ext))
                x = x2 + 1
            else:
                x += 1
        cuts = [c[0] for c in candidates]
        conf_by_x = {c[0]: c for c in candidates}

        # piece intervals; merge narrow pieces into narrower neighbor
        bounds = [0] + cuts + [W]
        iv = [[bounds[i], bounds[i + 1]] for i in range(len(bounds) - 1)]
        min_w = MIN_PIECE_F * t
        changed = True
        while changed and len(iv) > 1:
            changed = False
            widths = [b - a for a, b in iv]
            j = int(np.argmin(widths))
            if widths[j] < min_w:
                if j == 0:
                    iv[1][0] = iv[0][0]
                elif j == len(iv) - 1:
                    iv[-2][1] = iv[-1][1]
                else:
                    if widths[j - 1] <= widths[j + 1]:
                        iv[j - 1][1] = iv[j][1]
                    else:
                        iv[j + 1][0] = iv[j][0]
                iv.pop(j)
                changed = True
        final_cuts = [a for a, b in iv[1:]]

        meta = finfo[fname]
        px0, py0 = meta["bbox"][0], meta["bbox"][1]
        piece_files = []
        for pi, (a, b) in enumerate(iv):
            sl = arr[:, a:b]
            al = sl[:, :, 3]
            yy, xx = np.nonzero(al > 0)
            if len(yy) == 0:
                continue
            sl = sl[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
            counter += 1
            sf = f"sub{counter:06d}.png"
            Image.fromarray(sl, "RGBA").save(os.path.join(SUB, sf))
            piece_files.append(sf)
            pieces.append({
                "filename": sf,
                "parent": fname,
                "parent_cluster": cname,
                "piece_index": pi,
                "n_pieces_in_parent": len(iv),
                "page": meta["page"],
                # bbox in page coords: parent bbox + trim offset + slice
                "bbox": [int(px0 + x0 + a + xx.min()),
                         int(py0 + y0 + yy.min()),
                         int(xx.max() - xx.min() + 1),
                         int(yy.max() - yy.min() + 1)],
                "width": int(xx.max() - xx.min() + 1),
                "height": int(yy.max() - yy.min() + 1),
            })
        if len(iv) == 1:
            if rejected:
                reason = ("all cut candidates below confidence gate: " +
                          ", ".join(f"x={c[0]} conf={c[1]}" for c in rejected))
            elif not conn.any():
                reason = "no connector-thin columns (letters joined thickly)"
            else:
                reason = ("connector runs shorter than MIN_RUN "
                          f"({MIN_RUN}px) — no safe separation point")
        else:
            reason = None
        word_records.append({
            "parent": fname, "cluster": cname, "stroke_px": round(t, 1),
            "cuts": [{"x_trimmed": cx,
                      "confidence": conf_by_x[cx][1],
                      "run_px": conf_by_x[cx][2],
                      "extent_px": conf_by_x[cx][3]}
                     for cx in final_cuts if cx in conf_by_x],
            "rejected_candidates": [{"x_trimmed": c[0], "confidence": c[1]}
                                    for c in rejected],
            "unsplit_reason": reason,
            "n_pieces": len(iv), "pieces": piece_files})

        if final_cuts and word_idx % QA_EVERY == 0:
            qa = cv2.cvtColor(255 - (mask * 255), cv2.COLOR_GRAY2BGR)
            for cx in final_cuts:
                cv2.line(qa, (cx, 0), (cx, H - 1), (0, 0, 255), 2)
            cv2.imwrite(os.path.join(QA, fname.replace("glyph", "cuts")), qa)
            qa_saved += 1

npieces = [w["n_pieces"] for w in word_records]
dist = {str(k): int((np.array(npieces) == k).sum()) for k in sorted(set(npieces))}
n_split = sum(1 for w in word_records if w["n_pieces"] > 1)
all_confs = [c["confidence"] for w in word_records for c in w["cuts"]]
with open(os.path.join(BASE, "decomposition.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "source": "clusters_refined.json (Phase 4.5) word clusters",
        "word_clusters": sorted(word_clusters),
        "n_words": len(word_records),
        "n_words_split": n_split,
        "n_words_unsplit": len(word_records) - n_split,
        "n_pieces": len(pieces),
        "n_cuts": len(all_confs),
        "cut_confidence_mean": round(float(np.mean(all_confs)), 3) if all_confs else None,
        "pieces_per_word_hist": dist,
        "params": {"extent_f": EXTENT_F, "band_gap": BAND_GAP,
                   "min_run_px": MIN_RUN, "conf_min": CONF_MIN,
                   "min_piece_f": MIN_PIECE_F},
        "note": ("cuts gated by confidence; uncertain words left whole with "
                 "reason recorded; pieces are anonymous; no classification")},
        "pieces": pieces, "words": word_records}, f, indent=1)

print(f"{len(word_records)} words: {n_split} split, "
      f"{len(word_records) - n_split} left whole -> {len(pieces)} pieces; "
      f"hist: {dist}; mean cut confidence "
      f"{np.mean(all_confs):.3f}" if all_confs else "no cuts")
print(f"{qa_saved} QA overlays -> qa/decomposition/")
