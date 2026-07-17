"""Phase 8 QA: automated join-connectivity audit.

For every ordered pair (A left-joining, B right-joining) among the replaced
glyphs, composite A+B with the merged advances (RTL layout, 16-unit overlap
zone) at 100px/em and count connected components of the pair's ink.
1 component = joined; >1 = broken join (or genuinely detached piece).
Glyphs whose own render already has >1 component are noted and their
baseline component count is used as the reference.
"""
import json
import os

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
PX = 100
rep = json.load(open(os.path.join(BASE, "integration_report_p8.json"), encoding="utf-8"))
glyphs = [g for g, v in rep["glyphs"].items() if v.get("status") == "production"]
A_SET = [g for g in glyphs if g.endswith(".init") or g.endswith(".medi")]
B_SET = [g for g in glyphs if g.endswith(".medi") or g.endswith(".fina")]

tt = TTFont(NEW)
face = freetype.Face(NEW)
face.set_pixel_sizes(0, PX)

cache = {}
def gdata(g):
    if g not in cache:
        face.load_glyph(tt.getGlyphID(g), freetype.FT_LOAD_RENDER)
        bm = face.glyph.bitmap
        img = (np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
               if bm.rows else np.zeros((1, 1), np.uint8))
        cache[g] = (img > 100, face.glyph.bitmap_left, face.glyph.bitmap_top,
                    face.glyph.advance.x / 64.0)
    return cache[g]

def ncc(mask):
    n, _ = cv2.connectedComponents(mask.astype(np.uint8), 8)
    return n - 1

def compose(a, b):
    ia, la, ta, adva = gdata(a)
    ib, lb, tb, advb = gdata(b)
    W, H, OY = 1400, 700, 350
    canvas = np.zeros((H, W), bool)
    pen = 1200.0
    for (img, l, t, adv) in ((ia, la, ta, adva), (ib, lb, tb, advb)):
        pen -= adv
        gx, gy = int(pen + l), int(OY - t)
        h, w = img.shape
        sx0, sy0 = max(0, -gx), max(0, -gy)
        eh = min(h - sy0, H - max(0, gy))
        ew = min(w - sx0, W - max(0, gx))
        if eh > 0 and ew > 0:
            canvas[max(0, gy):max(0, gy) + eh, max(0, gx):max(0, gx) + ew] |= \
                img[sy0:sy0 + eh, sx0:sx0 + ew]
    return canvas

solo = {g: ncc(gdata(g)[0]) for g in set(A_SET) | set(B_SET)}
multi = {g: n for g, n in solo.items() if n > 1}
if multi:
    print("glyphs with >1 own component:", multi)

broken = []
for a in A_SET:
    for b in B_SET:
        n = ncc(compose(a, b))
        if n > solo[a] + solo[b] - 1:
            broken.append((a, b, n))
print(f"\npairs tested: {len(A_SET) * len(B_SET)}  broken: {len(broken)}")
for a, b, n in broken[:60]:
    print(f"  {a:26} + {b:26} cc={n}")
with open(os.path.join(BASE, "qa", "phase8_join_audit.json"), "w", encoding="utf-8") as f:
    json.dump({"tested": len(A_SET) * len(B_SET),
               "own_components": solo,
               "broken_pairs": [{"a": a, "b": b, "cc": n} for a, b, n in broken]},
              f, indent=1)
print("qa/phase8_join_audit.json written")
