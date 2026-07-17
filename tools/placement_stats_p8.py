"""Phase 8 step 1: connector-band placement statistics from word context.

For every attestation behind every production master, measure where the
word's connecting-baseline band sits relative to the attestation crop:

    ratio = (band_center_y - crop_top) / crop_height    (image coords, down+)

The band is found in the attestation's WORD context (never the crop alone):
  * mueller harvest crops  -> parent word image (harvest_report.json "word")
  * lecoq crops            -> 1200-dpi page strip around bbox_hires (x +/- 3w)
  * phase6 cluster members -> parent word image via decomposition.json/
                              segments.json bbox
Band = rows whose longest horizontal ink run >= 60% of context width; if none
match (isolated narrow words), threshold decays 0.6 -> 0.35 before giving up.
Per glyph: median ratio + band thickness stats -> placement_stats_p8.json.
Read-only: no font access, no crop modification.
"""
import glob as globmod
import json
import os

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
BASE = r"C:\Users\KutadguBilim\Font\Uigurica"


def band_of(mask, min_frac=0.60):
    """(band_top, band_bot, thickness) from longest-run row profile."""
    H, W = mask.shape
    runs = np.zeros(H)
    for r in range(H):
        row = mask[r]
        if not row.any():
            continue
        # longest run of ink in this row
        d = np.diff(np.concatenate([[0], row.view(np.int8), [0]]))
        starts = np.nonzero(d == 1)[0]
        ends = np.nonzero(d == -1)[0]
        if len(starts):
            runs[r] = (ends - starts).max()
    frac = min_frac
    while frac >= 0.35:
        rows = np.nonzero(runs >= frac * W)[0]
        if len(rows) >= 2:
            # densest contiguous block
            blocks = np.split(rows, np.nonzero(np.diff(rows) > 2)[0] + 1)
            blk = max(blocks, key=len)
            return int(blk[0]), int(blk[-1]), len(blk)
        frac -= 0.05
    return None


def to_mask(img_path):
    im = Image.open(img_path)
    if im.mode == "RGBA":
        a = np.asarray(im)
        return a[:, :, 3] > 128
    g = np.asarray(im.convert("L"))
    return g < 128


def main():
    o74 = json.load(open(os.path.join(BASE, "outline_report_74.json"), encoding="utf-8"))
    o6 = json.load(open(os.path.join(BASE, "outline_report.json"), encoding="utf-8"))
    dec_m = json.load(open(os.path.join(BASE, "harvest_decisions.json"), encoding="utf-8"))
    dec_l = json.load(open(os.path.join(BASE, "harvest_decisions_lecoq.json"), encoding="utf-8"))
    hrep_m = json.load(open(os.path.join(BASE, "harvest_report.json"), encoding="utf-8"))
    hrep_l = json.load(open(os.path.join(BASE, "harvest_lecoq_report.json"), encoding="utf-8"))
    validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
    upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
    decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
    segs = {s["filename"]: s for s in json.load(open(os.path.join(BASE, "segments.json"), encoding="utf-8"))}
    pieces = {p["filename"]: p for p in decomp["pieces"]}

    meta_m = {t["glyph"]: {c["file"]: c for c in t["candidates"]} for t in hrep_m["targets"]}
    meta_l = {t["glyph"]: {c["file"]: c for c in t["candidates"]} for t in hrep_l["targets"]}

    # attestation lists per glyph, mirroring regenerate_masters_74b pools
    atts = {}  # glyph -> list of measurement specs
    for g, files in dec_m.items():
        for f in files:
            c = meta_m.get(g, {}).get(f)
            if c:
                atts.setdefault(g, []).append(("muller_word", c))
    for g, files in dec_l.items():
        for f in files:
            c = meta_l.get(g, {}).get(f)
            if c:
                atts.setdefault(g, []).append(("lecoq_strip", c))
    # phase6 members: for every production phase6 glyph AND the validated
    # extras mixed into 7.4b pools
    for cname, v in validated["mappings"].items():
        g = v.get("final_glyph")
        if g and v["validation"] in ("corrected", "confirmed"):
            c = upd["clusters"][cname]
            for m in c["members"]:
                atts.setdefault(g, []).append(("cluster_member", m))

    # word-image lookup helpers
    def word_mask(word_file):
        p = os.path.join(BASE, "glyphs", word_file)
        if not os.path.exists(p):
            p = os.path.join(BASE, "segments", word_file)
        if not os.path.exists(p):
            return None
        return to_mask(p)

    lecoq_pages = {}

    def lecoq_gray(page):
        if page not in lecoq_pages:
            lecoq_pages.clear()
            fp = os.path.join(BASE, "lecoq_scans", f"page{page:02d}.png")
            lecoq_pages[page] = np.asarray(Image.open(fp).convert("L"))
        return lecoq_pages[page]

    out = {}
    for g in sorted(atts):
        ratios, thicks = [], []
        n_ctx = 0
        for kind, spec in atts[g]:
            if kind == "muller_word":
                wm = word_mask(spec["word"])
                if wm is None:
                    continue
                b = band_of(wm)
                if b is None:
                    continue
                bx, by, bw, bh = spec["box_native"]
                # box_native is in the word's native pixel grid
                ctr = (b[0] + b[1]) / 2.0
                ratios.append((ctr - by) / max(bh, 1))
                thicks.append((b[2]) / max(bh, 1))
                n_ctx += 1
            elif kind == "lecoq_strip":
                x, y, w, h = spec["bbox_hires"]
                gpg = lecoq_gray(spec["page"])
                x0 = max(0, x - 3 * w)
                x1 = min(gpg.shape[1], x + 4 * w)
                strip = gpg[y:y + h, x0:x1] < 128
                b = band_of(strip)
                if b is None:
                    continue
                ctr = (b[0] + b[1]) / 2.0
                ratios.append(ctr / max(h, 1))
                thicks.append(b[2] / max(h, 1))
                n_ctx += 1
            else:  # cluster_member
                pc = pieces.get(spec)
                if pc:
                    parent = segs.get(pc["parent"])
                    if not parent:
                        continue
                    wm = word_mask(pc["parent"])
                    if wm is None:
                        continue
                    b = band_of(wm)
                    if b is None:
                        continue
                    px, py, pw, ph = pc["bbox"]
                    sx, sy = parent["bbox"][0], parent["bbox"][1]
                    ctr = (b[0] + b[1]) / 2.0
                    ratios.append((ctr - (py - sy)) / max(ph, 1))
                    thicks.append(b[2] / max(ph, 1))
                    n_ctx += 1
                else:
                    seg = segs.get(spec)
                    if not seg:
                        continue
                    wm = word_mask(spec)
                    if wm is None:
                        continue
                    b = band_of(wm)
                    if b is None:
                        continue
                    ctr = (b[0] + b[1]) / 2.0
                    ratios.append(ctr / max(seg["height"], 1))
                    thicks.append(b[2] / max(seg["height"], 1))
                    n_ctx += 1
        if ratios:
            out[g] = {
                "n_attestations_measured": n_ctx,
                "band_ratio_median": round(float(np.median(ratios)), 4),
                "band_ratio_mad": round(float(np.median(
                    np.abs(np.array(ratios) - np.median(ratios)))), 4),
                "band_thickness_median": round(float(np.median(thicks)), 4),
                "method": "word_context_band",
            }
        else:
            out[g] = {"n_attestations_measured": 0,
                      "method": "noto_anchor_fallback"}
        print(f"{g:26} n={n_ctx:3} "
              f"ratio={out[g].get('band_ratio_median', '-')} "
              f"mad={out[g].get('band_ratio_mad', '-')}", flush=True)

    with open(os.path.join(BASE, "placement_stats_p8.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": {
            "definition": "ratio=(band_center-crop_top)/crop_h in image "
                          "coords (down positive); band from word context "
                          "longest-run row profile >=60%->35% width",
            "band_target_font_units": 47.5}, "glyphs": out}, f, indent=1)
    print("placement_stats_p8.json written")


if __name__ == "__main__":
    main()
