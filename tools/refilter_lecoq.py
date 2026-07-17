"""Phase 7.2b post-filter: rebuild Le Coq candidate selection from checkpoint.

The live harvest wrote every raw match to harvest_lecoq_progress.jsonl before
per-target truncation. The naive top-40-by-score selection was poisoned by
saturated NCC scores (>=0.98 on near-constant blurred windows -> noise blobs).
Re-selects with: saturation cut, per-glyph NMS, mask-shape sanity on the
actual hi-res ink, then top-40 per target.

PAGE-MAJOR: every 1200-dpi render is loaded exactly once (the per-glyph
ordering of the first version reloaded each render up to 24x and was
unusably slow). Crops are Otsu-binarized from the hi-res region - harvested
pixels remain the scan's own ink. No synthetic ink anywhere.
"""
import json
import os
import shutil

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = r"C:\Users\KutadguBilim\Font\Uigurica"
CKPT = os.path.join(ROOT, "harvest_lecoq_progress.jsonl")
SCANS = os.path.join(ROOT, "lecoq_scans")
OUT = os.path.join(ROOT, "harvest_lecoq_filtered")
SAT_MAX = 0.98
INK_MIN, INK_MAX = 0.04, 0.62
MAIN_CC_MIN = 0.55
PER_TARGET = 40

# multi-part targets legitimately have several pieces
MAX_CC = {
    "twodotsaboveuyg": 5, "twodotsbelowuyg": 5,
    "PunctuationTwoDots": 5, "PunctuationFourDots": 7,
    "PunctuationTwoBars": 5,
}
DEF_MAX_CC = 6


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / float(aw * ah + bw * bh - inter) if inter else 0.0


def main():
    rows = [json.loads(l) for l in open(CKPT, encoding="utf-8")]
    print("raw checkpoint rows:", len(rows), flush=True)
    rows = [r for r in rows if r["score"] < SAT_MAX]
    print("after saturation cut:", len(rows), flush=True)

    # pass A (no images): per-glyph NMS, page-local, high score wins
    survivors = []
    by_glyph = {}
    for r in rows:
        by_glyph.setdefault(r["glyph"], []).append(r)
    for glyph, cands in by_glyph.items():
        cands.sort(key=lambda r: -r["score"])
        kept = []
        for r in cands:
            if any(k["page"] == r["page"]
                   and iou(k["bbox_hires"], r["bbox_hires"]) > 0.30
                   for k in kept):
                continue
            kept.append(r)
        survivors.extend(kept)
    print("after NMS:", len(survivors), flush=True)

    # pass B (page-major, each render loaded once): shape sanity + crop write
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    by_page = {}
    for r in survivors:
        by_page.setdefault(r["page"], []).append(r)
    passed = []
    for page in sorted(by_page):
        fp = os.path.join(SCANS, f"page{page:02d}.png")
        if not os.path.exists(fp):
            continue
        g = np.asarray(Image.open(fp).convert("L"))
        n_ok = 0
        for r in by_page[page]:
            x, y, w, h = r["bbox_hires"]
            reg = g[y:y + h, x:x + w]
            if reg.size == 0:
                continue
            _, binv = cv2.threshold(reg, 0, 255,
                                    cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ink = binv > 0
            frac = float(ink.mean())
            if not (INK_MIN <= frac <= INK_MAX):
                continue
            _, _, stats, _ = cv2.connectedComponentsWithStats(binv, 8)
            areas = sorted(stats[1:, cv2.CC_STAT_AREA], reverse=True)
            if not areas:
                continue
            big = [a for a in areas if a >= max(9, 0.01 * ink.sum())]
            if len(big) > MAX_CC.get(r["glyph"], DEF_MAX_CC):
                continue
            if (r["glyph"] not in MAX_CC
                    and areas[0] / float(ink.sum()) < MAIN_CC_MIN):
                continue
            tdir = os.path.join(OUT, r["glyph"].replace(".", "_"))
            os.makedirs(tdir, exist_ok=True)
            rgba = np.zeros((*ink.shape, 4), np.uint8)
            rgba[:, :, 3] = ink * 255
            Image.fromarray(rgba).save(os.path.join(tdir, r["file"]))
            passed.append({**r, "ink_frac": round(frac, 3),
                           "n_cc": int(len(big))})
            n_ok += 1
        print(f"p{page}: {n_ok}/{len(by_page[page])} passed shape check",
              flush=True)

    # pass C (no images): top-40 per glyph, prune crops, write report
    report = {"meta": {"source": "lecoq1912", "filter": {
        "saturation_max": SAT_MAX, "ink_frac": [INK_MIN, INK_MAX],
        "main_cc_min": MAIN_CC_MIN, "per_target": PER_TARGET}}, "targets": []}
    n_total = 0
    by_glyph = {}
    for r in passed:
        by_glyph.setdefault(r["glyph"], []).append(r)
    for glyph in sorted(by_glyph):
        sel = sorted(by_glyph[glyph], key=lambda r: -r["score"])[:PER_TARGET]
        keep = {r["file"] for r in sel}
        tdir = os.path.join(OUT, glyph.replace(".", "_"))
        for f in os.listdir(tdir):
            if f not in keep:
                os.remove(os.path.join(tdir, f))
        report["targets"].append({"glyph": glyph, "n_candidates": len(sel),
                                  "candidates": [
            {"file": r["file"], "page": int(r["page"]),
             "score": float(r["score"]), "ink_frac": r["ink_frac"],
             "n_cc": r["n_cc"],
             "bbox_hires": [int(v) for v in r["bbox_hires"]],
             "provenance": "lecoq1912"} for r in sel]})
        n_total += len(sel)
        print(f" {glyph:24} kept {len(sel):3}  "
              f"top={sel[0]['score'] if sel else '-'}", flush=True)

    report["meta"]["n_candidates"] = n_total
    with open(os.path.join(ROOT, "harvest_lecoq_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("total kept:", n_total)


if __name__ == "__main__":
    main()
