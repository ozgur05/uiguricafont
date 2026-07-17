"""Phase 9 areas 4+5+6: metrics comparison, multi-size rendering validation,
regression specimen + difference images. Validation only.

Outputs: p9_metrics_render.json, render_comparison/*.png,
         difference_images/*.png
"""
import json
import os

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
OLD = os.path.join(BASE, "build", "Uigurica-Regular.phase1-noto.ttf")
RC = os.path.join(BASE, "render_comparison")
DI = os.path.join(BASE, "difference_images")
os.makedirs(RC, exist_ok=True)
os.makedirs(DI, exist_ok=True)

rep = json.load(open(os.path.join(BASE, "integration_report_p8.json"), encoding="utf-8"))
integrated = [g for g, v in rep["glyphs"].items() if v.get("status") == "production"]

tt_new, tt_old = TTFont(NEW), TTFont(OLD)
res = {"metrics": {}, "rendering": {}, "regression": {}}

# ---------------- area 4: metrics ----------------
gn, go = tt_new["glyf"], tt_old["glyf"]
hn, ho = tt_new["hmtx"], tt_old["hmtx"]
sig = []
table = {}
for g in integrated:
    a_n, l_n = hn[g]; a_o, l_o = ho[g]
    bn = (gn[g].xMin, gn[g].yMin, gn[g].xMax, gn[g].yMax) if gn[g].numberOfContours else (0,0,0,0)
    bo = (go[g].xMin, go[g].yMin, go[g].xMax, go[g].yMax) if go[g].numberOfContours else (0,0,0,0)
    rsb_n, rsb_o = a_n - bn[2], a_o - bo[2]
    d = {"adv": [a_o, a_n], "lsb": [l_o, l_n], "rsb": [rsb_o, rsb_n],
         "bbox_old": bo, "bbox_new": bn,
         "height": [bo[3] - bo[1], bn[3] - bn[1]]}
    table[g] = d
    if a_o and abs(a_n - a_o) / a_o > 0.25:
        sig.append(f"{g}: advance {a_o}->{a_n} ({(a_n-a_o)/a_o:+.0%})")
    if abs((bn[3]-bn[1]) - (bo[3]-bo[1])) > 0.5 * max(bo[3]-bo[1], 1):
        sig.append(f"{g}: height {bo[3]-bo[1]}->{bn[3]-bn[1]}")
res["metrics"] = {"per_glyph": table, "significant_deviations": sig}
print(f"metrics: {len(sig)} significant deviations")

# ---------------- area 5: rendering sizes ----------------
SIZES = [10, 12, 16, 24, 36, 72, 50, 100]   # 50/100 = 12pt @ 300/600 dpi
face = freetype.Face(NEW)
ids = tt_new

def rget(g, px, path_face=None):
    f = path_face or face
    f.set_pixel_sizes(0, px)
    f.load_glyph(ids.getGlyphID(g), freetype.FT_LOAD_RENDER)
    bm = f.glyph.bitmap
    if bm.rows == 0:
        return np.zeros((1, 1), np.uint8)
    return np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]

def ncc_(m):
    n, _ = cv2.connectedComponents((m > 100).astype(np.uint8), 8)
    return n - 1

def nholes(m):
    inv = (m <= 100).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, 4)
    H, W = m.shape
    holes = 0
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if x > 0 and y > 0 and x + w < W and y + h < H and a >= 4:
            holes += 1
    return holes

rend = {"dropouts": [], "counter_loss": [], "empty": []}
for g in integrated:
    ref = rget(g, 72)
    ref_cc, ref_holes = ncc_(ref), nholes(ref)
    for px in SIZES:
        m = rget(g, px)
        if m.max() == 0:
            rend["empty"].append(f"{g}@{px}px")
            continue
        cc = ncc_(m)
        if cc > ref_cc and px >= 16:
            rend["dropouts"].append(f"{g}@{px}px: {ref_cc}->{cc} pieces")
        if px >= 24 and nholes(m) < ref_holes:
            rend["counter_loss"].append(f"{g}@{px}px: holes {ref_holes}->{nholes(m)}")
res["rendering"] = {**rend, "sizes_tested": SIZES,
                    "summary": f"{len(rend['empty'])} empty, "
                               f"{len(rend['dropouts'])} dropouts, "
                               f"{len(rend['counter_loss'])} counter losses"}
print("rendering:", res["rendering"]["summary"])

# join continuity at small size (12px) for the six specimen junctions
face12 = freetype.Face(NEW)
words = [["bethuyg.init", "gimelHethuyg.medi", "memuyg.fina"],
         ["alephuyg.init", "shinuyg.medi", "kaphuyg.fina"],
         ["tawuyg.medi", "wawuyg.medi", "zayinuyg.fina"],
         ["lamedhuyg.init", "samekhuyg.medi", "bethuyg.fina"],
         ["nunuyg.init", "bethuyg.medi", "reshuyg.fina"],
         ["sadheuyg.init", "gimelHethuyg.medi", "finalHethuyg.fina"]]
def word_cc(seq, px):
    face12.set_pixel_sizes(0, px)
    W, H, OY = px * 12, px * 6, px * 3
    canvas = np.zeros((H, W), bool)
    pen = W - px
    for g in seq:
        face12.load_glyph(ids.getGlyphID(g), freetype.FT_LOAD_RENDER)
        pen -= face12.glyph.advance.x / 64.0
        bm = face12.glyph.bitmap
        if bm.rows:
            im = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            gx, gy = int(pen + face12.glyph.bitmap_left), int(OY - face12.glyph.bitmap_top)
            eh = min(im.shape[0], H - gy); ew = min(im.shape[1], W - gx)
            if eh > 0 and ew > 0 and gx >= 0 and gy >= 0:
                canvas[gy:gy+eh, gx:gx+ew] |= im[:eh, :ew] > 100
    n, _ = cv2.connectedComponents(canvas.astype(np.uint8), 8)
    return n - 1
join_small = {f"word{i}": {px: word_cc(w, px) for px in (12, 24, 72)}
              for i, w in enumerate(words)}
res["rendering"]["word_components_by_size"] = join_small
broken12 = sum(1 for v in join_small.values() if v[12] > v[72])
print(f"small-size join check: {broken12}/6 words gain pieces at 12px")

# ---------------- area 6: regression specimen + difference ----------------
uyg = [g for g in tt_new.getGlyphOrder() if "uyg" in g or "Punctuation" in g]
face_old = freetype.Face(OLD)
PXR = 64
changed, unchanged = [], []
for g in uyg:
    a = rget(g, PXR)
    b = rget(g, PXR, face_old)
    H = max(a.shape[0], b.shape[0]); W = max(a.shape[1], b.shape[1])
    A = np.zeros((H, W), np.uint8); A[:a.shape[0], :a.shape[1]] = a
    B = np.zeros((H, W), np.uint8); B[:b.shape[0], :b.shape[1]] = b
    diff = (A > 100) ^ (B > 100)
    frac = diff.mean()
    (changed if frac > 0.005 else unchanged).append(g)
    if frac > 0.005:
        rgb = np.stack([np.where((B > 100) & ~(A > 100), 255, 0),
                        np.where((A > 100) & ~(B > 100), 180, 0),
                        np.zeros_like(A)], -1).astype(np.uint8)
        rgb[(A > 100) & (B > 100)] = (60, 60, 60)
        Image.fromarray(255 - np.maximum(A, B)).save(
            os.path.join(RC, f"{g.replace('.', '_')}.png"))
        Image.fromarray(255 - rgb).save(
            os.path.join(DI, f"{g.replace('.', '_')}.png"))
exp = set(g.replace(".", "_") for g in integrated)
got = set(g.replace(".", "_") for g in changed)
res["regression"] = {
    "rendered_at_px": PXR,
    "n_changed": len(changed), "n_unchanged": len(unchanged),
    "changed": sorted(changed),
    "changed_matches_integrated": sorted(got) == sorted(
        g.replace(".", "_") for g in integrated),
    "unexpected_changes": sorted(got - exp),
    "expected_but_unchanged": sorted(exp - got),
}
print(f"regression: {len(changed)} changed / {len(unchanged)} unchanged; "
      f"matches integrated set: {res['regression']['changed_matches_integrated']}")
if res["regression"]["unexpected_changes"]:
    print("  unexpected:", res["regression"]["unexpected_changes"])

with open(os.path.join(BASE, "p9_metrics_render.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=1)
print("p9_metrics_render.json written")
