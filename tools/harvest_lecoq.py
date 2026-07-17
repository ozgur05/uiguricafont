"""Phase 7.2b: targeted harvest from Le Coq 1912 (same metal type).

1. Render text pp. 4-37 + index pp. 46-57 at 1200 dpi lossless (Phase 2
   parameters, no enhancement) -> lecoq_scans/pageNN.png
2. Connected-component word candidates per page (size-filtered; Latin
   transliteration is not pre-excluded - the NCC threshold and the human
   review pass are the filters, per the no-heuristic-surgery rule)
3. Template-match the open targets (BETH/GIMEL-HETH/KAPH/MEM all forms,
   dot/two-dot marks, 4 punctuation) - font renders as LOCATE-ONLY
   templates; harvested pixels are always the scan's ink
4. Output: harvest_lecoq/<target>/candNNNN.png, harvest_lecoq_report.json,
   harvest_review_lecoq.html (checkbox sheet -> harvest_decisions_lecoq.json)
Plates pp. 63-69 (Manichaean) are never touched.  Font unmodified.
"""
import base64
import glob
import io
import json
import os

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SC = os.path.join(BASE, "lecoq_scans")
HV = os.path.join(BASE, "harvest_lecoq")
os.makedirs(SC, exist_ok=True)
os.makedirs(HV, exist_ok=True)

# Index-first navigation (user directive): the Woerterliste pp. 46-57 is the
# primary search space - every distinct word appears there once as an
# isolated headword.  Text pages are included only insofar as already
# rendered (pp. 4-21, referenced throughout the index); they carry the
# punctuation and diacritics that never appear in headword position.
# pp. 22-37 stay unrendered unless a specific index reference requires them.
PAGES = list(range(46, 58)) + list(range(4, 22))   # 1-based PDF pages
DPI = 1200
NCC_MIN = 0.60
SCALES = (0.85, 1.0, 1.15)
WORK_H = 160
MAX_PER_WORD = 2
MAX_PER_TARGET = 40

TARGETS = (["bethuyg" + s for s in ("", ".init", ".medi", ".fina")] +
           ["gimelHethuyg" + s for s in ("", ".init", ".medi", ".fina")] +
           ["kaphuyg" + s for s in ("", ".init", ".medi", ".fina")] +
           ["memuyg" + s for s in ("", ".init", ".medi", ".fina")] +
           ["dotaboveuyg", "dotbelowuyg", "twodotsaboveuyg", "twodotsbelowuyg",
            "PunctuationBar", "PunctuationTwoBars", "PunctuationTwoDots",
            "PunctuationFourDots"])

import fitz
pdf = fitz.open(glob.glob(r"C:\Users\KutadguBilim\Font\T*rkische*.pdf")[0])
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
anchor_scan = float(np.median([p["height"] for p in decomp["pieces"]]))

FONT = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
tt = TTFont(FONT)
glyf = tt["glyf"]
LETTER_BASES = ["alephuyg", "bethuyg", "gimelHethuyg", "wawuyg", "zayinuyg",
                "finalHethuyg", "yodhuyg", "kaphuyg", "lamedhuyg", "memuyg",
                "nunuyg", "samekhuyg", "peuyg", "sadheuyg", "reshuyg",
                "shinuyg", "tawuyg", "leshuyg"]
anchor_font = float(np.median([glyf[n].yMax - glyf[n].yMin
                               for n in LETTER_BASES if glyf[n].numberOfContours]))
face = freetype.Face(FONT)
face.set_pixel_sizes(0, 200)

# NOTE: Le Coq's type is the same face but the SCAN scale may differ from
# Mueller's.  Estimate the Le Coq letter-height anchor from the median
# component height on the first text page after rendering (letters dominate).
templates = {}
for g in TARGETS:
    gid = tt.getGlyphID(g)
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.width == 0:
        continue
    ink = np.array(bm.buffer, np.float32).reshape(bm.rows, bm.pitch)[:, :bm.width] / 255.0
    go = glyf[g]
    h_units = (go.yMax - go.yMin) if go.numberOfContours else 200
    templates[g] = (ink, h_units / anchor_font)   # height in scan-anchor units
print(f"{len(templates)} templates")

# ---------- segment (discovery on user-supplied low-res PN pages) ----------
# Per user directive: PN_Page_NN.png (~150 dpi) drive discovery; the exact-
# ink crop is taken from the 1200-dpi render when available (pages 4-21,
# 46-57 are cached), falling back to the PN image itself.  Matching happens
# at WORK_H per component either way, so recall is comparable and CC
# extraction is ~60x cheaper.
PN_SIZE_LIMIT = None
Image.MAX_IMAGE_PIXELS = None


def hi_res_page(page_no):
    fp = os.path.join(SC, f"page{page_no:02d}.png")
    return fp if os.path.exists(fp) else None


def components(page_no):
    fp = os.path.join(SC, f"PN_Page_{page_no:02d}.png")
    if not os.path.exists(fp):
        return None, []
    img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in stats[i])
        if 7 <= h <= 200 and w >= 7 and a >= 12 and w <= 800:
            m = (lab[y:y + h, x:x + w] == i).astype(np.float32)
            out.append((x, y, w, h, m))
    return img.shape, out


def nms(boxes, iou=0.3):
    boxes = sorted(boxes, key=lambda b: -b[4])
    keep = []
    for b in boxes:
        ok = True
        for k in keep:
            x0, y0 = max(b[0], k[0]), max(b[1], k[1])
            x1, y1 = min(b[2], k[2]), min(b[3], k[3])
            inter = max(0, x1 - x0) * max(0, y1 - y0)
            if inter / max(1e-9, min((b[2]-b[0])*(b[3]-b[1]),
                                     (k[2]-k[0])*(k[3]-k[1]))) > iou:
                ok = False
                break
        if ok:
            keep.append(b)
    return keep


cands = {g: [] for g in templates}
counter = 0
anchor_lecoq = None
ckpt = open(os.path.join(BASE, "harvest_lecoq_progress.jsonl"), "w",
            encoding="utf-8")
for pg in PAGES:
    shape_pn, comps = components(pg)
    if not comps:
        print(f"p{pg}: no PN image or no components")
        continue
    hi = hi_res_page(pg)
    hi_img = cv2.imread(hi, cv2.IMREAD_GRAYSCALE) if hi else None
    up = (hi_img.shape[1] / shape_pn[1]) if hi_img is not None else 1.0
    if anchor_lecoq is None:
        anchor_lecoq = float(np.median([h for _, _, _, h, _ in comps]))
        print(f"lecoq letter-height anchor ~ {anchor_lecoq:.0f}px (PN scale)")
    for (X, Y, W, H, m) in comps:
        s_w = WORK_H / m.shape[0]
        if s_w * m.shape[1] < 8 or s_w * m.shape[1] > 4000:
            continue
        wimg = cv2.GaussianBlur(
            cv2.resize(m, (max(4, round(m.shape[1] * s_w)), WORK_H)), (0, 0), 1.5)
        for g, (tmpl, h_rel) in templates.items():
            h_scan = h_rel * anchor_lecoq
            boxes = []
            for sc in SCALES:
                th = int(round(h_scan * sc * s_w))
                if th < 8 or th > WORK_H:
                    continue
                tw = max(4, int(round(tmpl.shape[1] * th / tmpl.shape[0])))
                if tw >= wimg.shape[1] or th >= wimg.shape[0]:
                    continue
                T = cv2.GaussianBlur(cv2.resize(tmpl, (tw, th)), (0, 0), 1.5)
                R = cv2.matchTemplate(wimg, T, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.nonzero(R >= NCC_MIN)
                for y, x in zip(ys, xs):
                    boxes.append((x, y, x + tw, y + th, float(R[y, x])))
            boxes = sorted(boxes, key=lambda b: -b[4])[:30]
            for b in nms(boxes)[:MAX_PER_WORD]:
                X0, Y0 = int(b[0] / s_w), int(b[1] / s_w)
                X1, Y1 = int(np.ceil(b[2] / s_w)), int(np.ceil(b[3] / s_w))
                # page coords (PN space) -> hi-res space for the final crop
                hx0, hy0 = int((X + max(0, X0)) * up), int((Y + max(0, Y0)) * up)
                hx1, hy1 = int((X + X1) * up) + 1, int((Y + Y1) * up) + 1
                if hi_img is not None:
                    region = hi_img[hy0:hy1, hx0:hx1]
                    if region.size == 0:
                        continue
                    _, rb = cv2.threshold(region, 0, 255,
                                          cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                    crop = rb.astype(np.float32) / 255.0
                else:
                    crop = m[max(0, Y0):Y1, max(0, X0):X1]
                if crop.size == 0 or crop.mean() < 0.03:
                    continue
                counter += 1
                td = os.path.join(HV, g.replace(".", "_"))
                os.makedirs(td, exist_ok=True)
                fn = f"cand{counter:05d}.png"
                out = np.zeros((*crop.shape, 4), np.uint8)
                out[:, :, 3] = (crop * 255).astype(np.uint8)
                Image.fromarray(out, "RGBA").save(os.path.join(td, fn))
                rec = {"file": fn, "page": int(pg), "score": round(float(b[4]), 3),
                       "bbox_hires": [hx0, hy0, hx1 - hx0, hy1 - hy0],
                       "crop_source": "1200dpi" if hi_img is not None else "PN150dpi",
                       "provenance": "lecoq1912"}
                cands[g].append(rec)
                ckpt.write(json.dumps({"glyph": g, **rec}) + "\n")
    ckpt.flush()
    print(f"p{pg}: {len(comps)} comps, total cands {sum(len(v) for v in cands.values())}")
ckpt.close()

report = []
for g, cs in cands.items():
    cs.sort(key=lambda c: -c["score"])
    keep = cs[:MAX_PER_TARGET]
    keepset = {c["file"] for c in keep}
    td = os.path.join(HV, g.replace(".", "_"))
    if os.path.isdir(td):
        for f in os.listdir(td):
            if f not in keepset:
                os.remove(os.path.join(td, f))
    report.append({"glyph": g, "template_source": "font_locate_only",
                   "n_candidates": len(keep), "candidates": keep})
    print(f"{g:24} {len(keep)} kept")

with open(os.path.join(BASE, "harvest_lecoq_report.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {"source": "lecoq1912", "pages": PAGES, "dpi": DPI,
                        "ncc_min": NCC_MIN,
                        "anchor_lecoq_px": anchor_lecoq,
                        "plates_excluded": "pp. 63-69 (Manichaean)",
                        "n_candidates": sum(r["n_candidates"] for r in report)},
               "targets": report}, f, indent=1)


def b64(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    ink = a[:, :, 3] / 255.0
    im = Image.fromarray((255 - ink * 255).astype(np.uint8))
    im.thumbnail((110, 110))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


cards = []
for r in report:
    if not r["n_candidates"]:
        continue
    td = os.path.join(HV, r["glyph"].replace(".", "_"))
    th = "".join(
        f'<label class="cd"><img src="{b64(os.path.join(td, c["file"]))}">'
        f'<div>{c["score"]:.2f} p{c["page"]}</div>'
        f'<input type="checkbox" name="{r["glyph"]}|{c["file"]}"></label>'
        for c in r["candidates"])
    cards.append(f'<div class="card"><h3>{r["glyph"]} '
                 f'<small>{r["n_candidates"]} candidates, Le Coq 1912, '
                 f'locate-only template</small></h3>'
                 f'<div class="warn">judge the SCAN ink, not Noto resemblance'
                 f'</div><div class="row">{th}</div></div>')
html = ("""<!doctype html><html><head><meta charset="utf-8"><title>Le Coq harvest review</title>
<style>body{font-family:sans-serif;margin:16px}.card{border:1px solid #ccc;border-radius:8px;margin:12px 0;padding:8px 12px}
.row{display:flex;flex-wrap:wrap;gap:8px}.cd{text-align:center;font-size:11px;border:1px solid #eee;padding:3px}
.cd img{display:block;background:#fff}.warn{color:#b00;font-size:12px}
#bar{position:sticky;top:0;background:#2c3e50;color:#fff;padding:8px 12px;border-radius:6px}</style></head><body>
<div id="bar"><b>Phase 7.2b review (Le Coq 1912)</b> - tick complete, correct instances
<button onclick="ex()">Export harvest_decisions_lecoq.json</button></div>""" +
        "".join(cards) + """
<script>function ex(){const o={};document.querySelectorAll('input:checked').forEach(i=>{
const[g,f]=i.name.split('|');(o[g]=o[g]||[]).push(f);});
const b=new Blob([JSON.stringify(o,null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='harvest_decisions_lecoq.json';a.click();}
</script></body></html>""")
with open(os.path.join(BASE, "harvest_review_lecoq.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("harvest_review_lecoq.html written")
