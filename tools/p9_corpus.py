"""Phase 9 area 7: corpus validation - rendered words vs the printed source.

For every Mueller word whose pieces ALL belong to human-validated clusters
with a glyph identity, lay out the glyph sequence RTL with the integrated
font and compare the render against the word's own scan image:
    IoU, scan-ink coverage, connected-component delta (join continuity).
The same words are rendered with the phase1 Noto backup - the print-fidelity
delta between the two fonts is the headline metric of the whole project.
Validation only. Outputs p9_corpus.json + qa/p9_corpus_sheet.png.
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

validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
segs = {s["filename"]: s for s in json.load(open(os.path.join(BASE, "segments.json"), encoding="utf-8"))}

member2cluster = {}
for cname, c in upd["clusters"].items():
    for m in c["members"]:
        member2cluster[m] = cname
cluster2glyph = {}
for cname, v in validated["mappings"].items():
    g = v.get("final_glyph")
    if g and not g.startswith("__") and v["validation"] in ("corrected", "confirmed"):
        cluster2glyph[cname] = g

# words -> ordered piece glyphs (piece_index ascending = visual left->right)
words = {}
for p in decomp["pieces"]:
    words.setdefault(p["parent"], []).append(p)
qualified = []
for parent, pieces in words.items():
    pieces.sort(key=lambda p: p["piece_index"])
    gl = []
    ok = True
    for p in pieces:
        c = member2cluster.get(p["filename"])
        g = cluster2glyph.get(c)
        if not g:
            ok = False
            break
        gl.append(g)
    if ok and parent in segs:
        # logical order (first letter) = highest piece_index (RTL)
        qualified.append((parent, gl[::-1]))
# whole-word members (single validated unit)
for m, c in member2cluster.items():
    if m.startswith("glyph") and c in cluster2glyph and m in segs \
            and m not in dict(qualified):
        qualified.append((m, [cluster2glyph[c]]))
print(f"{len(qualified)} fully-validated words")

tt = TTFont(NEW)


def render_word(fontpath, seq, px):
    face = freetype.Face(fontpath)
    face.set_pixel_sizes(0, px)
    W, H, OY = px * 14, px * 6, px * 3
    canvas = np.zeros((H, W), bool)
    pen = W - px
    for g in seq:
        try:
            gid = tt.getGlyphID(g)
        except KeyError:
            return None
        face.load_glyph(gid, freetype.FT_LOAD_RENDER)
        pen -= face.glyph.advance.x / 64.0
        bm = face.glyph.bitmap
        if bm.rows:
            im = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            gx, gy = int(pen + face.glyph.bitmap_left), int(OY - face.glyph.bitmap_top)
            if gx < 0:
                continue
            eh, ew = min(im.shape[0], H - gy), min(im.shape[1], W - gx)
            if eh > 0 and ew > 0 and gy >= 0:
                canvas[gy:gy+eh, gx:gx+ew] |= im[:eh, :ew] > 100
    ys, xs = np.nonzero(canvas)
    if not len(ys):
        return None
    return canvas[ys.min():ys.max()+1, xs.min():xs.max()+1]


def scan_mask(fname):
    p = os.path.join(BASE, "glyphs", fname)
    if not os.path.exists(p):
        p = os.path.join(BASE, "segments", fname)
    im = Image.open(p)
    if im.mode == "RGBA":
        m = np.asarray(im)[:, :, 3] > 128
    else:
        m = np.asarray(im.convert("L")) < 128
    ys, xs = np.nonzero(m)
    if not len(ys):
        return None
    return m[ys.min():ys.max()+1, xs.min():xs.max()+1]


def compare(scan, seq, fontpath):
    """scale render to scan height, xcorr-align, IoU + coverage + CC delta."""
    r0 = render_word(fontpath, seq, 100)
    if r0 is None or scan is None:
        return None
    sh = scan.shape[0]
    px = max(12, int(round(100 * sh / r0.shape[0])))
    r = render_word(fontpath, seq, px)
    if r is None:
        return None
    # pad to common canvas, align by ink centroid then phase correlate
    H = max(scan.shape[0], r.shape[0]) + 40
    W = max(scan.shape[1], r.shape[1]) + 40
    def put(m):
        c = np.zeros((H, W), np.float32)
        ys, xs = np.nonzero(m)
        oy, ox = int(H/2 - ys.mean()), int(W/2 - xs.mean())
        for (y, x) in ((max(0, oy), max(0, ox)),):
            hh = min(m.shape[0], H - y); ww = min(m.shape[1], W - x)
            c[y:y+hh, x:x+ww] = m[:hh, :ww]
        return c
    A, B = put(scan.astype(np.float32)), put(r.astype(np.float32))
    (dx, dy), _ = cv2.phaseCorrelate(A, B)
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    B = cv2.warpAffine(B, M, (W, H))
    a, b = A > 0.5, B > 0.5
    inter, union = (a & b).sum(), (a | b).sum()
    ncc_scan = cv2.connectedComponents(a.astype(np.uint8), 8)[0] - 1
    ncc_rend = cv2.connectedComponents(b.astype(np.uint8), 8)[0] - 1
    return {"iou": round(float(inter / max(union, 1)), 3),
            "coverage": round(float(inter / max(a.sum(), 1)), 3),
            "cc_scan": int(ncc_scan), "cc_render": int(ncc_rend)}


results = []
for parent, seq in qualified:
    scan = scan_mask(parent)
    mn = compare(scan, seq, NEW)
    mo = compare(scan, seq, OLD)
    if mn and mo:
        results.append({"word": parent, "glyphs": seq,
                        "n_letters": len(seq), "new": mn, "old": mo})
print(f"{len(results)} words compared")

iou_n = [r["new"]["iou"] for r in results]
iou_o = [r["old"]["iou"] for r in results]
cov_n = [r["new"]["coverage"] for r in results]
cov_o = [r["old"]["coverage"] for r in results]
better = sum(1 for r in results if r["new"]["iou"] > r["old"]["iou"])
summary = {
    "n_words": len(results),
    "iou_median": {"mueller_font": round(float(np.median(iou_n)), 3),
                   "noto_font": round(float(np.median(iou_o)), 3)},
    "iou_mean": {"mueller_font": round(float(np.mean(iou_n)), 3),
                 "noto_font": round(float(np.mean(iou_o)), 3)},
    "coverage_median": {"mueller_font": round(float(np.median(cov_n)), 3),
                        "noto_font": round(float(np.median(cov_o)), 3)},
    "words_where_mueller_beats_noto": better,
    "join_continuity_ok": sum(1 for r in results
                              if r["new"]["cc_render"] <= r["new"]["cc_scan"] + 1),
}
print(json.dumps(summary, indent=1))
with open(os.path.join(BASE, "p9_corpus.json"), "w", encoding="utf-8") as f:
    json.dump({"summary": summary, "words": results}, f, indent=1)

# visual sheet: 12 words spread across the IoU range, scan vs new render
results.sort(key=lambda r: -r["new"]["iou"])
picks = results[::max(1, len(results)//12)][:12]
rows = []
for r in picks:
    scan = scan_mask(r["word"])
    rend = render_word(NEW, r["glyphs"],
                       max(12, int(round(100 * scan.shape[0] /
                           max(render_word(NEW, r["glyphs"], 100).shape[0], 1)))))
    h = 90
    def th(m):
        im = Image.fromarray((255 - m * 255).astype(np.uint8))
        im.thumbnail((420, h))
        return im
    a, b = th(scan), th(rend)
    row = Image.new("RGB", (900, h + 26), "white")
    row.paste(a.convert("RGB"), (10, 20))
    row.paste(b.convert("RGB"), (460, 20))
    d = ImageDraw.Draw(row)
    d.text((10, 2), f"{r['word']} scan", fill=(0, 0, 0))
    d.text((460, 2), f"render IoU={r['new']['iou']} (noto {r['old']['iou']})",
           fill=(180, 0, 0))
    rows.append(row)
sheet = Image.new("RGB", (900, sum(r.height for r in rows)), "white")
y = 0
for r in rows:
    sheet.paste(r, (0, y)); y += r.height
sheet.save(os.path.join(BASE, "qa", "p9_corpus_sheet.png"))
print("qa/p9_corpus_sheet.png written")
