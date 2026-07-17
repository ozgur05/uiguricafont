"""Phase 8: integrate validated Mueller/Le Coq masters into Uigurica-Regular.

Design sources: production masters ONLY (Phases 6 + 7.4b consensus outlines).
Noto remains for glyphs without a production master. GSUB/GPOS untouched;
only glyf + hmtx entries of replaced glyphs change (plus derived head/maxp).

Pipeline per glyph:
  0. restore font from backup if present (idempotent re-runs)
  1. best master (7.4b preferred; phase6 by attestation count then quality)
  2. cubic GLIF -> contours; REMOVE stray contours (detached, <12% of the
     largest contour's area, not a hole) - neighbour-ink/diacritic
     contamination; logged per glyph
  3. vertical: word-context band ratio (placement_stats_p8.json) puts the
     connector-band center at y=47.5 (Noto band 0..95); marks/punct keep the
     Noto glyph's own vertical center (fallback recorded)
  4. horizontal: Noto RTL join convention - JOIN EDGES ANCHOR ON BAND-ROW
     INK (y in 0..95 after placement), not the global bbox (an ascender tip
     leaning over the neighbour must not define the join point):
       isolated lsb=10/rsb=10 ; init: band ink to -8, rsb 10 from global ;
       medi: band -8 and band adv+8 ; fina: lsb 10 global, band adv+8
  5. join-stub: where band-row ink still stops short of the join point,
     prolong the terminal horizontally at its own thickness; where a
     terminal covers <20 units of the band core [10,85], bridge to the band
     core - restoring the printed connection the crop cut off; all logged
  6. pathops simplify (winding fix, overlap/self-intersection removal)
     -> cu2qu (max_err 1.0) -> TTGlyphPen -> glyf/hmtx
Backup: build/Uigurica-Regular.phase1-noto.ttf (created on first run).
"""
import json
import os
import shutil

import numpy as np
import pathops
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.pointPen import PointToSegmentPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ufoLib.glifLib import readGlyphFromString
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
FONT = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
BACKUP = os.path.join(BASE, "build", "Uigurica-Regular.phase1-noto.ttf")
BAND_LO, BAND_HI = 0.0, 95.0
BAND_CTR = (BAND_LO + BAND_HI) / 2.0
CORE_LO, CORE_HI = 10.0, 85.0
JOIN_L, SB = -8.0, 10.0
JOIN_OVER = 8.0
MAX_ERR = 1.0
STRAY_FRAC = 0.12

MARKS = {"dotaboveuyg", "dotbelowuyg", "twodotsaboveuyg", "twodotsbelowuyg"}
PUNCT = {"PunctuationBar", "PunctuationTwoBars", "PunctuationTwoDots",
         "PunctuationFourDots"}


def form_of(g):
    if g in MARKS or g in PUNCT:
        return "nonjoining"
    for suf in (".init", ".medi", ".fina"):
        if g.endswith(suf):
            return suf[1:]
    return "isol"


def select_masters():
    o74 = json.load(open(os.path.join(BASE, "outline_report_74.json"), encoding="utf-8"))["outlines"]
    o6 = json.load(open(os.path.join(BASE, "outline_report.json"), encoding="utf-8"))["outlines"]
    best = {}
    for o in o6:
        g = o.get("glyph_name")
        if not g or o["source_image_count"] < 3:
            continue
        key = (0, o["source_image_count"], o["outline_quality_score"])
        if g not in best or key > best[g]["key"]:
            best[g] = {"key": key, "glif": o["files"]["glif"],
                       "src": f"phase6:{o['cluster']}",
                       "n_att": o["source_image_count"],
                       "provenance": {"mueller1908": o["source_image_count"]},
                       "quality": o["outline_quality_score"]}
    for o in o74:
        if o["status"] != "production":
            continue
        g = o["glyph"]
        key = (1, o["attestations_total"], o["outline_quality_score"])
        if g not in best or key > best[g]["key"]:
            best[g] = {"key": key, "glif": o["files"]["glif"],
                       "src": "phase7.4b", "n_att": o["attestations_total"],
                       "provenance": o["provenance"],
                       "quality": o["outline_quality_score"]}
    return best


def load_contours(path):
    """GLIF -> list of RecordingPen op-lists, one per contour."""
    class G:
        pass
    rec = RecordingPen()
    readGlyphFromString(open(path, encoding="utf-8").read(), G(),
                        PointToSegmentPen(rec))
    contours, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    if cur:
        contours.append(cur)
    return contours


def contour_path(ops, dx=0.0, dy=0.0):
    p = pathops.Path()
    pen = p.getPen()
    for op, args in ops:
        if op == "closePath" or op == "endPath":
            pen.closePath()
        else:
            getattr(pen, op)(*[(x + dx, y + dy) for x, y in args])
    return p


def drop_strays(contours):
    """Remove small detached contours (not holes). Returns kept, n_removed."""
    paths = [contour_path(c) for c in contours]
    areas, boxes = [], []
    for p in paths:
        b = p.bounds
        boxes.append(b)
        areas.append(abs((b[2] - b[0]) * (b[3] - b[1])))
    if not areas:
        return contours, 0
    a_max = max(areas)
    keep, removed = [], 0
    for i, (c, p, a, b) in enumerate(zip(contours, paths, areas, boxes)):
        if a >= STRAY_FRAC * a_max:
            keep.append(c)
            continue
        cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        inside = any(j != i and areas[j] > a and paths[j].contains((cx, cy))
                     for j in range(len(paths)))
        if inside:      # hole or nested detail - keep
            keep.append(c)
        else:
            removed += 1
    return keep, removed


def rasterize(path, pad=8):
    """1 unit/px mask of the path (winding-corrected beforehand)."""
    b = path.bounds
    x0, y0 = int(np.floor(b[0])) - pad, int(np.floor(b[1])) - pad
    w = int(np.ceil(b[2])) - x0 + pad
    h = int(np.ceil(b[3])) - y0 + pad
    img = Image.new("1", (max(w, 4), max(h, 4)), 0)
    dr = ImageDraw.Draw(img)
    for cont in path.contours:
        pts = []
        rec = RecordingPen()
        cont.draw(rec)
        # flatten
        last = None
        for op, args in rec.value:
            if op == "moveTo":
                last = args[0]
                pts.append(last)
            elif op == "lineTo":
                last = args[0]
                pts.append(last)
            elif op in ("curveTo", "qCurveTo"):
                segs = [a for a in args if a is not None]
                allp = [last] + list(segs)
                for t in np.linspace(0.08, 1.0, 12):
                    # de Casteljau on the polyline of control points
                    pp = [np.array(q, float) for q in allp]
                    while len(pp) > 1:
                        pp = [(1 - t) * pp[k] + t * pp[k + 1]
                              for k in range(len(pp) - 1)]
                    pts.append(tuple(pp[0]))
                last = pts[-1]
        poly = [(px - x0, py - y0) for px, py in pts]
        if len(poly) >= 3:
            dr.polygon(poly, fill=0 if not cont.clockwise else 1)
    # note: with clockwise=True simplify, outers are clockwise=True
    return np.asarray(img, bool), x0, y0


def band_extent(mask, x_org, y_org, ylo=BAND_LO, yhi=BAND_HI):
    """min/max x of ink whose y in [ylo,yhi]; None if no band ink."""
    r0 = int(ylo - y_org)
    r1 = int(yhi - y_org)
    H = mask.shape[0]
    r0c, r1c = max(0, r0), min(H, r1)
    if r1c <= r0c:
        return None
    sub = mask[r0c:r1c]
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return None
    return float(xs.min() + x_org), float(xs.max() + x_org)


def terminal_rows(mask, x_org, y_org, x_at, side, probe=26):
    """y-range of ink within `probe` units inward of x_at."""
    c = int(x_at - x_org)
    W = mask.shape[1]
    if side == "left":
        cols = slice(max(0, c), min(W, c + probe))
    else:
        cols = slice(max(0, c - probe), min(W, c + 1))
    ys, _ = np.nonzero(mask[:, cols])
    if len(ys) == 0:
        return None
    return float(ys.min() + y_org), float(ys.max() + y_org)


def rect(x0, y0, x1, y1):
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0))
    pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return p


def integrate():
    stats = json.load(open(os.path.join(BASE, "placement_stats_p8.json"), encoding="utf-8"))["glyphs"]
    best = select_masters()
    print(f"{len(best)} production masters selected")

    if os.path.exists(BACKUP):
        shutil.copy2(BACKUP, FONT)      # idempotent re-run
        print("restored working font from phase1 backup")
    else:
        shutil.copy2(FONT, BACKUP)
        print("backup written")
    tt = TTFont(FONT)
    glyf, hmtx = tt["glyf"], tt["hmtx"]

    report = {}
    for g in sorted(best):
        if g not in glyf.keys():
            report[g] = {"skipped": "glyph not in font"}
            continue
        info = best[g]
        contours = load_contours(os.path.join(BASE, info["glif"]))
        contours, n_stray = drop_strays(contours)

        def build(dx_, dy_):
            p = pathops.Path()
            pen_ = p.getPen()
            for c_ in contours:
                contour_path(c_, dx_, dy_).draw(pen_)
            return pathops.simplify(p, fix_winding=True, clockwise=True)

        raw = build(0, 0)
        x0, y0, x1, y1 = raw.bounds
        w_ink, h_ink = x1 - x0, y1 - y0
        form = form_of(g)
        old_glyph = glyf[g]
        old_adv, old_lsb = hmtx[g]

        # ---- vertical ----
        st = stats.get(g, {})
        noto_ctr_y = ((old_glyph.yMin + old_glyph.yMax) / 2.0
                      if old_glyph.numberOfContours else BAND_CTR)
        if form == "nonjoining":
            dy = noto_ctr_y - (y0 + y1) / 2.0
            v_method = "noto_vertical_center"
        elif st.get("method") == "word_context_band" and st.get("n_attestations_measured", 0):
            ratio = st["band_ratio_median"]
            dy = BAND_CTR - (y1 - ratio * h_ink)
            v_method = f"word_context_band(ratio={ratio})"
        else:
            dy = noto_ctr_y - (y0 + y1) / 2.0
            v_method = "noto_anchor_fallback"

        placed = build(0, dy)
        mask, mx, my = rasterize(placed)
        bx = band_extent(mask, mx, my)

        # ---- horizontal anchoring ----
        stubs = []
        g_x0, g_x1 = placed.bounds[0], placed.bounds[2]
        if form in ("init", "medi"):
            anchor = bx[0] if bx else g_x0
            dx = JOIN_L - anchor
        elif form in ("fina", "isol"):
            dx = SB - g_x0
        else:
            noto_ctr_x = ((old_glyph.xMin + old_glyph.xMax) / 2.0
                          if old_glyph.numberOfContours else old_adv / 2.0)
            dx = noto_ctr_x - (g_x0 + g_x1) / 2.0
        placed = build(dx, dy)
        mask, mx, my = rasterize(placed)
        bx = band_extent(mask, mx, my)
        g_x0, g_x1 = placed.bounds[0], placed.bounds[2]

        if form == "init":
            adv = int(round(g_x1 + SB))
        elif form == "medi":
            adv = int(round((bx[1] if bx else g_x1) - JOIN_OVER))
        elif form == "fina":
            adv = int(round((bx[1] if bx else g_x1) - JOIN_OVER))
        elif form == "isol":
            adv = int(round(g_x1 + SB))
        else:
            adv = old_adv
        adv = max(adv, 10)

        # ---- join stubs / bridges ----
        joins = {"init": ["left"], "medi": ["left", "right"],
                 "fina": ["right"]}.get(form, [])
        # every joining terminal must fully cover the COMMON band core so
        # that any two adjacent stubs are guaranteed to overlap
        COMMON_LO, COMMON_HI = 25.0, 70.0
        for side in joins:
            xj = JOIN_L if side == "left" else adv + JOIN_OVER
            tr = terminal_rows(mask, mx, my, xj, side)
            bxn = band_extent(mask, mx, my, -30, 130)
            edge = (bxn[0] if side == "left" else bxn[1]) if bxn else None
            gap = ((edge - xj) if side == "left" else (xj - edge)) if edge is not None else None
            need_h = gap is not None and gap > 0.5
            need_v = not (tr and tr[0] <= COMMON_LO + 0.5
                          and tr[1] >= COMMON_HI - 0.5)
            if not (need_h or need_v):
                continue
            cov = (min(tr[1], CORE_HI) - max(tr[0], CORE_LO)) if tr else 0
            ylo = max(min(COMMON_LO, tr[0] if tr else COMMON_LO), -30)
            yhi = min(max(COMMON_HI, tr[1] if tr else COMMON_HI), 130)
            # stub spans from the join point into the existing ink
            inward = 30.0
            if side == "left":
                p = rect(xj, ylo, (edge if edge is not None else xj) + inward, yhi)
            else:
                p = rect((edge if edge is not None else xj) - inward, ylo, xj, yhi)
            placed = pathops.op(placed, p, pathops.PathOp.UNION, fix_winding=True)
            stubs.append({"side": side,
                          "h_gap": round(gap, 1) if gap is not None else None,
                          "band_coverage_before": round(cov, 1),
                          "y_range": [round(ylo, 1), round(yhi, 1)]})
            mask, mx, my = rasterize(placed)

        # ---- finalize ----
        simplified = pathops.simplify(placed, fix_winding=True, clockwise=True)
        ttpen = TTGlyphPen(None)
        qpen = Cu2QuPen(ttpen, max_err=MAX_ERR, reverse_direction=False)
        simplified.draw(qpen)
        new_glyph = ttpen.glyph()
        glyf[g] = new_glyph
        new_glyph.recalcBounds(glyf)
        final_adv = adv if form != "nonjoining" else old_adv
        hmtx[g] = (final_adv,
                   int(round(new_glyph.xMin)) if new_glyph.numberOfContours else 0)

        report[g] = {
            "master": info["glif"], "source": info["src"],
            "attestations": info["n_att"], "provenance": info["provenance"],
            "quality": info["quality"],
            "vertical_method": v_method, "dy": round(dy, 1),
            "stray_contours_removed": n_stray,
            "advance": {"old": old_adv, "new": final_adv},
            "lsb": {"old": old_lsb, "new": hmtx[g][1]},
            "join_stubs": stubs,
            "n_contours": new_glyph.numberOfContours,
            "status": "production",
        }
        print(f"{g:26} {form:5} adv {old_adv:4}->{final_adv:4} dy={dy:6.1f} "
              f"strays={n_stray} stubs={len(stubs)}", flush=True)

    # draft codepoints: current font outlines retained, reference recorded
    o74 = json.load(open(os.path.join(BASE, "outline_report_74.json"), encoding="utf-8"))["outlines"]
    for o in o74:
        if o["status"] == "draft" and o["glyph"] not in report:
            report[o["glyph"]] = {
                "status": "draft-not-integrated",
                "kept": "existing font outline (Noto)",
                "draft_master_reference": o["files"],
                "attestations": o["attestations_total"],
                "reason": "insufficient attestations (<3); see coverage_gaps_74b.md",
            }

    tt.save(FONT)
    with open(os.path.join(BASE, "integration_report_p8.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": {
            "font": "build/Uigurica-Regular.ttf",
            "backup": "build/Uigurica-Regular.phase1-noto.ttf",
            "band_units": [BAND_LO, BAND_HI],
            "join_convention": "init left -8 / medi -8..adv+8 / fina adv+8 "
                               "(band-row anchored) / free sb 10",
            "stray_rule": f"detached non-hole contours < {STRAY_FRAC:.0%} of largest",
            "cu2qu_max_err": MAX_ERR,
            "n_replaced": sum(1 for v in report.values()
                              if v.get("status") == "production")},
            "glyphs": report}, f, indent=1)
    n = sum(1 for v in report.values() if v.get("status") == "production")
    print(f"\nfont saved; {n} glyphs replaced; integration_report_p8.json written")


if __name__ == "__main__":
    integrate()
