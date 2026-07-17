"""Phase 7.2b re-score: rank Le Coq survivors by hi-res template NCC.

The discovery pass matched on ~150-dpi PN components resized to 160px and
Gaussian-blurred - at that resolution NCC cannot tell letterforms from paper
texture (noise scores 0.9x, real type 0.65-0.80). This pass re-scores every
NMS survivor on its 1200-dpi Otsu ink mask against the font template rendered
at the candidate's own height, with only light smoothing. Templates remain
LOCATE/RANK-ONLY - kept pixels are always the scan's ink.

Filters: saturation cut (<0.98 low-res score), per-glyph NMS, ink-fraction
and fragmentation sanity, aspect-ratio gate vs template, hi-res NCC >= NCC_HI
(letters) / >= NCC_HI_MARKS (dots/bars: less internal structure, laxer gate).
Output ranked by hi-res score: harvest_lecoq_filtered/, harvest_lecoq_report
.json, harvest_review_lecoq.html (checkboxes -> harvest_decisions_lecoq.json).
"""
import base64
import io
import json
import os
import shutil

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = r"C:\Users\KutadguBilim\Font\Uigurica"
CKPT = os.path.join(ROOT, "harvest_lecoq_progress.jsonl")
SCANS = os.path.join(ROOT, "lecoq_scans")
OUT = os.path.join(ROOT, "harvest_lecoq_filtered")
SAT_MAX = 0.98
INK_MIN, INK_MAX = 0.04, 0.62
PER_TARGET = 40
NCC_HI = 0.45
NCC_HI_MARKS = 0.35
ASPECT_TOL = (0.55, 1.8)   # candidate aspect / template aspect
PAD = 0.22                 # slide margin for alignment search

MARKS = {"dotaboveuyg", "dotbelowuyg", "twodotsaboveuyg", "twodotsbelowuyg",
         "PunctuationBar", "PunctuationTwoBars", "PunctuationTwoDots",
         "PunctuationFourDots"}


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / float(aw * ah + bw * bh - inter) if inter else 0.0


def load_templates(targets):
    face = freetype.Face(os.path.join(ROOT, "build", "Uigurica-Regular.ttf"))
    face.set_pixel_sizes(0, 220)
    tt = TTFont(os.path.join(ROOT, "build", "Uigurica-Regular.ttf"))
    out = {}
    for g in targets:
        face.load_glyph(tt.getGlyphID(g), freetype.FT_LOAD_RENDER)
        bm = face.glyph.bitmap
        if bm.width == 0:
            continue
        ink = np.array(bm.buffer, np.float32).reshape(
            bm.rows, bm.pitch)[:, :bm.width] / 255.0
        ys, xs = np.nonzero(ink > 0.15)
        ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        out[g] = ink
    return out


def hi_ncc(mask, tmpl):
    """Max NCC of template slid over the padded candidate mask, both at the
    candidate's ink-box height, light sigma-1 smoothing."""
    ys, xs = np.nonzero(mask)
    if len(ys) < 30:
        return 0.0
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h = 96
    sw = h / m.shape[0]
    mw = max(6, round(m.shape[1] * sw))
    m = cv2.resize(m, (mw, h))
    th = h
    tw = max(6, round(tmpl.shape[1] * th / tmpl.shape[0]))
    T = cv2.resize(tmpl, (tw, th))
    py, px = int(h * PAD), int(max(tw, mw) * PAD)
    canvas = np.zeros((h + 2 * py, mw + 2 * px), np.float32)
    canvas[py:py + h, px:px + mw] = m
    if T.shape[0] >= canvas.shape[0] or T.shape[1] >= canvas.shape[1]:
        return 0.0
    A = cv2.GaussianBlur(canvas, (0, 0), 1.0)
    B = cv2.GaussianBlur(T, (0, 0), 1.0)
    R = cv2.matchTemplate(A, B, cv2.TM_CCOEFF_NORMED)
    return float(R.max())


def main():
    rows = [json.loads(l) for l in open(CKPT, encoding="utf-8")]
    rows = [r for r in rows if r["score"] < SAT_MAX]
    by_glyph = {}
    for r in rows:
        by_glyph.setdefault(r["glyph"], []).append(r)
    survivors = []
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
    print(f"{len(survivors)} NMS survivors", flush=True)

    templates = load_templates(sorted(by_glyph))
    print(f"{len(templates)} templates", flush=True)

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
            tmpl = templates.get(r["glyph"])
            if tmpl is None:
                continue
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
            ys, xs = np.nonzero(ink)
            if len(ys) < 30:
                continue
            bh = ys.max() - ys.min() + 1
            bw = xs.max() - xs.min() + 1
            rel = (bw / bh) / (tmpl.shape[1] / tmpl.shape[0])
            if not (ASPECT_TOL[0] <= rel <= ASPECT_TOL[1]):
                continue
            s_hi = hi_ncc(ink, tmpl)
            gate = NCC_HI_MARKS if r["glyph"] in MARKS else NCC_HI
            if s_hi < gate:
                continue
            tdir = os.path.join(OUT, r["glyph"].replace(".", "_"))
            os.makedirs(tdir, exist_ok=True)
            rgba = np.zeros((*ink.shape, 4), np.uint8)
            rgba[:, :, 3] = ink * 255
            Image.fromarray(rgba).save(os.path.join(tdir, r["file"]))
            passed.append({**r, "score_hi": round(s_hi, 3),
                           "ink_frac": round(frac, 3)})
            n_ok += 1
        print(f"p{page}: {n_ok}/{len(by_page[page])} pass hi-res gate",
              flush=True)

    report = {"meta": {"source": "lecoq1912", "rescore": {
        "saturation_max": SAT_MAX, "ncc_hi": NCC_HI,
        "ncc_hi_marks": NCC_HI_MARKS, "aspect_tol": list(ASPECT_TOL),
        "per_target": PER_TARGET,
        "note": "ranked by 1200-dpi template NCC; low-res discovery score "
                "kept as score_lo; templates locate/rank only"}},
        "targets": []}
    n_total = 0
    by_g = {}
    for r in passed:
        by_g.setdefault(r["glyph"], []).append(r)
    for glyph in sorted(templates):
        sel = sorted(by_g.get(glyph, []), key=lambda r: -r["score_hi"])[:PER_TARGET]
        keep = {r["file"] for r in sel}
        tdir = os.path.join(OUT, glyph.replace(".", "_"))
        if os.path.isdir(tdir):
            for f in os.listdir(tdir):
                if f not in keep:
                    os.remove(os.path.join(tdir, f))
        report["targets"].append({"glyph": glyph, "n_candidates": len(sel),
                                  "template_source": "font_locate_only",
                                  "candidates": [
            {"file": r["file"], "page": int(r["page"]),
             "score_hi": r["score_hi"], "score_lo": float(r["score"]),
             "ink_frac": r["ink_frac"],
             "bbox_hires": [int(v) for v in r["bbox_hires"]],
             "provenance": "lecoq1912"} for r in sel]})
        n_total += len(sel)
        print(f" {glyph:24} kept {len(sel):3}  "
              f"top_hi={sel[0]['score_hi'] if sel else '-'}", flush=True)
    report["meta"]["n_candidates"] = n_total
    with open(os.path.join(ROOT, "harvest_lecoq_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("total kept:", n_total, flush=True)

    # ---- review sheet ----
    def b64(path):
        a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
        ink = a[:, :, 3] / 255.0
        im = Image.fromarray((255 - ink * 255).astype(np.uint8))
        im.thumbnail((110, 110))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    cards = []
    for r in report["targets"]:
        if not r["n_candidates"]:
            cards.append(f'<div class="card"><h3>{r["glyph"]} '
                         f'<small>0 candidates survived the hi-res gate'
                         f'</small></h3></div>')
            continue
        tdir = os.path.join(OUT, r["glyph"].replace(".", "_"))
        th = "".join(
            f'<label class="cd"><img src="{b64(os.path.join(tdir, c["file"]))}">'
            f'<div>{c["score_hi"]:.2f} p{c["page"]}</div>'
            f'<input type="checkbox" name="{r["glyph"]}|{c["file"]}"></label>'
            for c in r["candidates"])
        cards.append(f'<div class="card"><h3>{r["glyph"]} '
                     f'<small>{r["n_candidates"]} candidates, Le Coq 1912, '
                     f'ranked by 1200-dpi NCC, locate-only template</small></h3>'
                     f'<div class="warn">judge the SCAN ink, not Noto '
                     f'resemblance</div><div class="row">{th}</div></div>')
    html = ("""<!doctype html><html><head><meta charset="utf-8"><title>Le Coq harvest review</title>
<style>body{font-family:sans-serif;margin:16px}.card{border:1px solid #ccc;border-radius:8px;margin:12px 0;padding:8px 12px}
.row{display:flex;flex-wrap:wrap;gap:8px}.cd{text-align:center;font-size:11px;border:1px solid #eee;padding:3px}
.cd img{display:block;background:#fff}.warn{color:#b00;font-size:12px}
#bar{position:sticky;top:0;background:#2c3e50;color:#fff;padding:8px 12px;border-radius:6px}</style></head><body>
<div id="bar"><b>Phase 7.2b review (Le Coq 1912, re-scored)</b> - tick complete, correct instances
<button onclick="ex()">Export harvest_decisions_lecoq.json</button></div>""" +
            "".join(cards) + """
<script>function ex(){const o={};document.querySelectorAll('input:checked').forEach(i=>{
const[g,f]=i.name.split('|');(o[g]=o[g]||[]).push(f);});
const b=new Blob([JSON.stringify(o,null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='harvest_decisions_lecoq.json';a.click();}
</script></body></html>""")
    with open(os.path.join(ROOT, "harvest_review_lecoq.html"), "w",
              encoding="utf-8") as f:
        f.write(html)
    print("harvest_review_lecoq.html written", flush=True)


if __name__ == "__main__":
    main()
