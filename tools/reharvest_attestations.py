"""Phase 7.2: template-guided multi-attestation re-harvest.

Objective: close the codepoint ledger gaps from attestation_inventory.json
by LOCATING new attestations inside the original word segments via template
matching.  Matching only - no boundary heuristics, no connector removal, no
reconnection (phase_architecture.json: no_synthetic_ink).

Templates, in trust order
  A. muller_master   : consensus bitmaps of Phase 6 masters (validated ink)
  B. font_locate_only: FreeType renders of the target glyph - used ONLY to
                       locate candidate windows; flagged; the harvested ink
                       is always the scan's.  Needed for letters that have
                       no Mueller source yet (LAMEDH, NUN, SAMEKH, SHIN,
                       marks, punctuation).

Search space: all Phase 4.6 parent word segments (the 564 words) PLUS all
segments in human_unmapped word clusters - i.e. real printed words only.

Method per (target, word)
  - word ink at working height; template scaled to its expected height
    from font metrics x scan anchor, swept at scales {0.85, 1.0, 1.15}
  - cv2.matchTemplate TM_CCOEFF_NORMED on blurred ink
  - windows >= NCC_MIN kept, non-max suppressed (IoU 0.3)
  - right-joining targets (zayinuyg, finalHethuyg): window center must lie
    in the FINAL-position zone (left 38% of the word; RTL layout mapped to
    left-to-right print as established in Phase 5) or the word be single-
    lettered; violating windows are dropped, count reported
  - the candidate crop = the word's own ink inside the window, exact pixels

Output
  harvest/<target>/candNNN.png     exact-ink RGBA crops
  harvest_report.json              per target: template source, windows,
                                   scores, positions, per-word provenance
  harvest_review.html              approve/reject sheet (same mechanism as
                                   Phase 5.5), exports harvest_decisions.json
Nothing is promoted automatically; masters are not regenerated here.
"""
import base64
import io
import json
import os

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
HARV = os.path.join(BASE, "harvest")
os.makedirs(HARV, exist_ok=True)

NCC_MIN = 0.52
SCALES = (0.85, 1.0, 1.15)
MAX_PER_WORD = 3
MAX_PER_TARGET = 40
WORK_H = 160
FINAL_ZONE = 0.38          # left fraction of word = final position (RTL)

validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
inventory = json.load(open(os.path.join(BASE, "attestation_inventory.json"), encoding="utf-8"))
outline = json.load(open(os.path.join(BASE, "outline_report.json"), encoding="utf-8"))
ginfo = validated["glyph_info"]

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
FPX_PER_UNIT = 200.0 / tt["head"].unitsPerEm

RIGHT_JOINING = {"zayinuyg", "finalHethuyg"}

# ---------------- targets from the codepoint ledger ----------------
# missing -> font_locate_only templates; direct-but-thin -> muller_master
ledger = {e["codepoint"]: e for e in inventory["codepoint_ledger"]}
CP2GLYPHS = {}
for g, gi in ginfo.items():
    if gi["codepoint"] and gi["category"] in ("letter", "mark", "punctuation"):
        CP2GLYPHS.setdefault(gi["codepoint"], []).append(g)

targets = []
for cp, e in ledger.items():
    if e["state"] == "missing":
        for g in CP2GLYPHS.get(cp, []):
            targets.append({"glyph": g, "codepoint": cp,
                            "template_source": "font_locate_only"})
    elif e["state"] == "direct" and e.get("action"):
        # thin direct coverage: reuse the existing Mueller master as template
        for o in outline["outlines"]:
            if o["glyph_name"] and ginfo.get(o["glyph_name"], {}).get("codepoint") == cp:
                targets.append({"glyph": o["glyph_name"], "codepoint": cp,
                                "template_source": "muller_master",
                                "master_cluster": o["cluster"]})
                break
print(f"targets: {len(targets)} "
      f"({sum(1 for t in targets if t['template_source'] == 'muller_master')} "
      f"muller, {sum(1 for t in targets if t['template_source'] == 'font_locate_only')} locate-only)")


# ---------------- template builders ----------------
def load_ink(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    alpha = a[:, :, 3]
    ys, xs = np.nonzero(alpha > 0)
    if len(ys) == 0:
        return None
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gray = a[:, :, :3].mean(axis=2)
    return (a[:, :, 3] / 255.0) * (1.0 - gray / 255.0)


def font_template(gname):
    gid = tt.getGlyphID(gname)
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.width == 0:
        return None, 0
    ink = np.array(bm.buffer, np.float32).reshape(bm.rows, bm.pitch)[:, :bm.width] / 255.0
    # expected height in scan px
    g = glyf[gname]
    h_units = (g.yMax - g.yMin) if g.numberOfContours else bm.rows / FPX_PER_UNIT
    h_scan = h_units / anchor_font * anchor_scan
    return ink, h_scan


def master_template(cluster):
    # rebuild consensus quickly from the cluster members (same as Phase 6)
    c = upd["clusters"][cluster]
    d = ("decomposed_segments" if c["representative_dir"] == "decomposed_segments"
         else "segments")
    inks = [load_ink(os.path.join(BASE, d, m)) for m in c["members"]]
    inks = [i for i in inks if i is not None]
    hs = [i.shape[0] for i in inks]
    H = 200
    stack = []
    Wm = 0
    scaled = []
    for ink in inks:
        s = H / ink.shape[0]
        nw = max(1, round(ink.shape[1] * s))
        scaled.append(cv2.resize(ink, (nw, H)))
        Wm = max(Wm, nw)
    canvas = np.zeros((len(scaled), H, Wm), np.float32)
    for k, s in enumerate(scaled):
        canvas[k, :, (Wm - s.shape[1]) // 2:(Wm - s.shape[1]) // 2 + s.shape[1]] = s
    cons = canvas.mean(axis=0)
    return (cons >= 0.5).astype(np.float32), float(np.median(hs))


# ---------------- search space: parent words ----------------
word_files = sorted({w["parent"] for w in decomp["words"]})
# add whole segments of human_unmapped WORD clusters not already parents
for cname, v in validated["mappings"].items():
    if v["validation"] == "human_unmapped" and v["cluster_type"] == "word segment":
        for m in upd["clusters"][cname]["members"]:
            if m.startswith("glyph"):
                word_files.append(m)
word_files = sorted(set(word_files))
words = {}
for wf in word_files:
    ink = load_ink(os.path.join(BASE, "segments", wf))
    if ink is not None and ink.shape[1] >= 40:
        words[wf] = ink
print(f"search space: {len(words)} word images")

seg_meta = {s["filename"]: s for s in
            json.load(open(os.path.join(BASE, "segments.json"), encoding="utf-8"))}


def page_of(wf):
    m = seg_meta.get(wf)
    return m["page"] if m else None


# ---------------- matching ----------------
def nms(boxes, iou=0.3):
    boxes = sorted(boxes, key=lambda b: -b["score"])
    keep = []
    for b in boxes:
        ok = True
        for k in keep:
            x0 = max(b["x0"], k["x0"]); y0 = max(b["y0"], k["y0"])
            x1 = min(b["x1"], k["x1"]); y1 = min(b["y1"], k["y1"])
            inter = max(0, x1 - x0) * max(0, y1 - y0)
            a = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
            bb = (k["x1"] - k["x0"]) * (k["y1"] - k["y0"])
            if inter / max(1e-9, min(a, bb)) > iou:
                ok = False
                break
        if ok:
            keep.append(b)
    return keep


report = []
counter = 0
for t in targets:
    gname = t["glyph"]
    if t["template_source"] == "muller_master":
        tmpl, h_scan = master_template(t["master_cluster"])
    else:
        tmpl, h_scan = font_template(gname)
    if tmpl is None or tmpl.shape[0] < 4:
        continue
    base = gname.split(".")[0]
    rj = base in RIGHT_JOINING
    tdir = os.path.join(HARV, gname.replace(".", "_"))
    os.makedirs(tdir, exist_ok=True)
    cands = []
    rj_dropped = 0
    for wf, wink in words.items():
        s_w = WORK_H / wink.shape[0]
        wimg = cv2.GaussianBlur(
            cv2.resize(wink, (max(1, round(wink.shape[1] * s_w)), WORK_H)),
            (0, 0), 1.5)
        boxes = []
        for sc in SCALES:
            th = h_scan * sc * s_w * (wink.shape[0] / anchor_scan) \
                if False else h_scan * sc * s_w
            th = int(round(th))
            if th < 8 or th > WORK_H:
                continue
            tw = max(4, int(round(tmpl.shape[1] * th / tmpl.shape[0])))
            if tw >= wimg.shape[1] or th >= wimg.shape[0]:
                continue
            T = cv2.GaussianBlur(cv2.resize(tmpl, (tw, th)), (0, 0), 1.5)
            R = cv2.matchTemplate(wimg, T, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.nonzero(R >= NCC_MIN)
            for y, x in zip(ys, xs):
                boxes.append({"x0": x, "y0": y, "x1": x + tw, "y1": y + th,
                              "score": float(R[y, x]), "scale": sc})
        boxes = nms(boxes)[:MAX_PER_WORD]
        for b in boxes:
            cx = (b["x0"] + b["x1"]) / 2 / wimg.shape[1]
            if rj and cx > FINAL_ZONE and wimg.shape[1] > 1.6 * (b["x1"] - b["x0"]):
                rj_dropped += 1
                continue
            # exact-ink crop back at native scale
            X0 = int(b["x0"] / s_w); X1 = int(np.ceil(b["x1"] / s_w))
            Y0 = int(b["y0"] / s_w); Y1 = int(np.ceil(b["y1"] / s_w))
            crop = wink[max(0, Y0):Y1, max(0, X0):X1]
            if crop.size == 0 or crop.max() < 0.3:
                continue
            counter += 1
            fn = f"cand{counter:04d}.png"
            out = np.zeros((*crop.shape, 4), np.uint8)
            out[:, :, 3] = (crop * 255).astype(np.uint8)
            Image.fromarray(out, "RGBA").save(os.path.join(tdir, fn))
            cands.append({"file": fn, "word": wf, "page": page_of(wf),
                          "score": round(b["score"], 3),
                          "scale": b["scale"],
                          "x_center_frac": round(cx, 3),
                          "box_native": [X0, Y0, X1 - X0, Y1 - Y0]})
    cands.sort(key=lambda c: -c["score"])
    cands = cands[:MAX_PER_TARGET]
    report.append({"glyph": gname, "codepoint": t["codepoint"],
                   "template_source": t["template_source"],
                   "n_candidates": len(cands),
                   "right_joining_windows_dropped": rj_dropped,
                   "candidates": cands})
    print(f"{gname:24} [{t['template_source']:16}] {len(cands):3} candidates"
          + (f" (rj-dropped {rj_dropped})" if rj_dropped else ""))

with open(os.path.join(BASE, "harvest_report.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "method": "TM_CCOEFF_NORMED sliding template, scales 0.85/1.0/1.15, "
                  f"NCC >= {NCC_MIN}, NMS IoU 0.3",
        "no_synthetic_ink": True,
        "locate_only_note": ("font_locate_only templates find WHERE a shape "
                             "sits; the crop is always the scan's own ink"),
        "right_joining_rule": f"final zone = left {FINAL_ZONE:.0%} of word",
        "n_targets": len(report),
        "n_candidates": sum(r["n_candidates"] for r in report)},
        "targets": report}, f, indent=1)

# ---------------- review sheet ----------------
def b64(arr):
    im = Image.fromarray((255 - arr * 255).astype(np.uint8)).convert("L")
    im.thumbnail((120, 120))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


cards = []
for r in report:
    if not r["n_candidates"]:
        continue
    tdir = os.path.join(HARV, r["glyph"].replace(".", "_"))
    thumbs = ""
    for c in r["candidates"]:
        ink = load_ink(os.path.join(tdir, c["file"]))
        thumbs += (f'<label class="cd"><img src="{b64(ink)}">'
                   f'<div>{c["score"]:.2f} p{c["page"]}</div>'
                   f'<input type="checkbox" name="{r["glyph"]}|{c["file"]}">'
                   f'</label>')
    warn = ("" if r["template_source"] == "muller_master" else
            '<div class="warn">template = font render (locate-only); judge '
            'the SCAN ink, not resemblance to Noto</div>')
    cards.append(f'<div class="card"><h3>{r["glyph"]} {r["codepoint"]} '
                 f'<small>{r["template_source"]}, {r["n_candidates"]} candidates'
                 f'</small></h3>{warn}<div class="row">{thumbs}</div></div>')

html = ("""<!doctype html><html><head><meta charset="utf-8"><title>Uigurica harvest review</title>
<style>body{font-family:sans-serif;margin:16px}.card{border:1px solid #ccc;border-radius:8px;margin:12px 0;padding:8px 12px}
.row{display:flex;flex-wrap:wrap;gap:8px}.cd{text-align:center;font-size:11px;border:1px solid #eee;padding:3px}
.cd img{display:block;background:#fff}.warn{color:#b00;font-size:12px;margin:4px 0}
#bar{position:sticky;top:0;background:#2c3e50;color:#fff;padding:8px 12px;border-radius:6px}</style></head><body>
<div id="bar"><b>Phase 7.2 harvest review</b> - tick every crop that is a complete, correct instance of the target
<button onclick="ex()">Export harvest_decisions.json</button></div>""" +
        "".join(cards) + """
<script>function ex(){const out={};document.querySelectorAll('input:checked').forEach(i=>{
const[g,f]=i.name.split('|');(out[g]=out[g]||[]).push(f);});
const b=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='harvest_decisions.json';a.click();}
</script></body></html>""")
with open(os.path.join(BASE, "harvest_review.html"), "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nharvest_report.json, harvest_review.html "
      f"({sum(r['n_candidates'] for r in report)} candidates)")
