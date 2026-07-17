"""Phase 10: metrics refinement - NO outline redesign.

Problem (Phase 9 finding): crop boundaries fell at arbitrary points along the
printed baseline connector, so some joining glyphs carry long connector-only
runs that inflate their advances (waw.medi +136%, taw.medi +94%, ...).

Fix, metrics-only: re-anchor each JOINED side on the letter BODY plus a
standard connector stub, instead of the full run:
  - a column is "connector-only" if all its ink lies inside the band window
    y in [-15, 115]; body columns have ink beyond it
  - left-joined sides (init/medi): translate the outline (pure translation,
    shape untouched) so that max(ink_left, body_left - STUB) sits at -8
  - right-joined sides (medi/fina): advance = min(ink_right, body_right
    + STUB) - 8
  - free sides keep sb 10 from actual ink
Connector ink beyond the new advance overlaps the neighbour along the band -
exactly how the print works (letters share one continuous baseline stroke).
Only glyphs whose advance or origin changes by > 15 units are touched.
Outputs metrics_refinement_p10.json; font updated in place
(build/Uigurica-Regular.phase9.ttf preserves the pre-refinement state).
"""
import json
import os

import numpy as np
import pathops
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from fontTools.pens.recordingPen import RecordingPen

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
FONT = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
STUB = 45
BAND_WIN = (-15.0, 115.0)
MIN_CHANGE = 15

rep = json.load(open(os.path.join(BASE, "integration_report_p8.json"), encoding="utf-8"))
integrated = {g: v for g, v in rep["glyphs"].items()
              if v.get("status") == "production"}

tt = TTFont(FONT)
glyf, hmtx = tt["glyf"], tt["hmtx"]


def form_of(g):
    for suf in (".init", ".medi", ".fina"):
        if g.endswith(suf):
            return suf[1:]
    return "isol"


def glyph_mask(g):
    path = pathops.Path()
    glyf[g].draw(path.getPen(glyphSet=None), glyf)
    path = pathops.simplify(path, fix_winding=True, clockwise=True)
    b = path.bounds
    x0, y0 = int(np.floor(b[0])) - 4, int(np.floor(b[1])) - 4
    W, H = int(np.ceil(b[2])) - x0 + 8, int(np.ceil(b[3])) - y0 + 8
    img = Image.new("1", (W, H), 0)
    dr = ImageDraw.Draw(img)
    for cont in path.contours:
        rec = RecordingPen()
        cont.draw(rec)
        pts, last = [], None
        for op, args in rec.value:
            if op in ("moveTo", "lineTo"):
                last = args[0]
                pts.append(last)
            elif op in ("qCurveTo", "curveTo"):
                allp = [last] + [a for a in args if a is not None]
                for t in np.linspace(0.1, 1.0, 10):
                    pp = [np.array(q, float) for q in allp]
                    while len(pp) > 1:
                        pp = [(1-t)*pp[k] + t*pp[k+1] for k in range(len(pp)-1)]
                    pts.append(tuple(pp[0]))
                last = pts[-1]
        poly = [(px - x0, py - y0) for px, py in pts]
        if len(poly) >= 3:
            dr.polygon(poly, fill=1 if cont.clockwise else 0)
    return np.asarray(img, bool), x0, y0


changes = {}
for g, info in sorted(integrated.items()):
    form = form_of(g)
    if form == "isol" or g in ("dotaboveuyg", "dotbelowuyg") \
            or g.startswith("Punctuation"):
        continue
    mask, mx, my = glyph_mask(g)
    ys, xs = np.nonzero(mask)
    ink_l, ink_r = xs.min() + mx, xs.max() + mx
    # column classification
    r_lo = int(BAND_WIN[0] - my)
    r_hi = int(BAND_WIN[1] - my)
    H = mask.shape[0]
    body_cols = []
    for c in range(mask.shape[1]):
        col = np.nonzero(mask[:, c])[0]
        if len(col) == 0:
            continue
        if col.min() < r_lo or col.max() > r_hi:
            body_cols.append(c)
    if not body_cols:
        continue
    body_l = body_cols[0] + mx
    body_r = body_cols[-1] + mx
    old_adv, old_lsb = hmtx[g]

    dx = 0
    if form in ("init", "medi"):
        target_left = max(ink_l, body_l - STUB)
        dx = int(round(-8 - target_left))
    new_ink_r = ink_r + dx
    new_body_r = body_r + dx
    if form in ("medi", "fina"):
        new_adv = int(round(min(new_ink_r, new_body_r + STUB) - 8))
    else:  # init right side free
        new_adv = int(round(new_ink_r + 10))
    if abs(dx) <= MIN_CHANGE and abs(new_adv - old_adv) <= MIN_CHANGE:
        continue

    gl = glyf[g]
    if dx:
        coords, ends, flags = gl.getCoordinates(glyf)
        coords.translate((dx, 0))
        gl.coordinates = coords
    gl.recalcBounds(glyf)
    hmtx[g] = (max(new_adv, 10), int(gl.xMin))
    changes[g] = {"form": form, "dx": dx,
                  "advance": [old_adv, max(new_adv, 10)],
                  "connector_overhang_right":
                      int(round(new_ink_r - (max(new_adv, 10) + 8))),
                  "body_span": [int(body_l + dx), int(new_body_r)]}
    print(f"{g:26} {form:5} dx={dx:+4} adv {old_adv:4}->{max(new_adv,10):4} "
          f"overhang={changes[g]['connector_overhang_right']}")

tt.save(FONT)
with open(os.path.join(BASE, "metrics_refinement_p10.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {"stub_units": STUB, "band_window": BAND_WIN,
                        "rule": "joined sides anchored on body+stub; pure "
                                "translation + advance only, no reshaping",
                        "pre_state": "build/Uigurica-Regular.phase9.ttf"},
               "glyphs_changed": changes}, f, indent=1)
print(f"\n{len(changes)} glyphs re-metriced; font saved; "
      "metrics_refinement_p10.json written")
