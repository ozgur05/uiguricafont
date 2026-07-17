"""Phase 7.4b: regenerate masters mixing Mueller-1908 and Le Coq-1912 ink.

Same consensus + Schneider pipeline as Phase 7.4 (identical parameters), but
the per-glyph attestation pool is the UNION of three provenance-tagged
sources:
  * mueller1908 : harvest_decisions.json crops in harvest/<glyph>/
  * lecoq1912   : harvest_decisions_lecoq.json crops in
                  harvest_lecoq_filtered/<glyph>/
  * validated   : members of already-validated clusters for the exact glyph
The two printings are the SAME Berlin-academy metal type (verified), so their
ink co-stacks in one consensus.  outline_report_74.json records the provenance
mix per master (n_mueller / n_lecoq / n_validated) so no master silently
hides its source.  Font is never modified.

Supersedes regenerate_masters_74.py output: writes the same
outline_report_74.json (read by update_ledger.py) covering every harvested
glyph from either source.
"""
import json
import os

import cv2
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from skimage.measure import find_contours

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
OUT = os.path.join(BASE, "masters")
CANVAS_H = 240
PAD = 40
FIT_TOL = 1.6
CORNER_DEG = 65
PROD_MIN = 3

dec_m = json.load(open(os.path.join(BASE, "harvest_decisions.json"), encoding="utf-8"))
dec_l = json.load(open(os.path.join(BASE, "harvest_decisions_lecoq.json"), encoding="utf-8"))
validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
ginfo = validated["glyph_info"]

anchor_scan = float(np.median([p["height"] for p in decomp["pieces"]]))
tt = TTFont(os.path.join(BASE, "build", "Uigurica-Regular.ttf"))
glyf = tt["glyf"]
LETTERS = ["alephuyg", "bethuyg", "gimelHethuyg", "wawuyg", "zayinuyg",
           "finalHethuyg", "yodhuyg", "kaphuyg", "lamedhuyg", "memuyg",
           "nunuyg", "samekhuyg", "peuyg", "sadheuyg", "reshuyg", "shinuyg",
           "tawuyg", "leshuyg"]
anchor_font = float(np.median([glyf[n].yMax - glyf[n].yMin for n in LETTERS
                               if glyf[n].numberOfContours]))

# existing validated members per glyph (provenance: mueller1908, same as 7.4)
extra = {}
for cname, v in validated["mappings"].items():
    g = v.get("final_glyph")
    if g and v["validation"] in ("corrected", "confirmed"):
        c = upd["clusters"][cname]
        d = ("decomposed_segments"
             if c["representative_dir"] == "decomposed_segments" else "segments")
        extra.setdefault(g, []).extend(
            os.path.join(BASE, d, m) for m in c["members"])

# assemble provenance-tagged pool per glyph
pool = {}   # glyph -> list of (path, provenance)
for g, files in dec_m.items():
    tdir = os.path.join(BASE, "harvest", g.replace(".", "_"))
    pool.setdefault(g, []).extend(
        (os.path.join(tdir, f), "mueller1908") for f in files)
for g, files in dec_l.items():
    tdir = os.path.join(BASE, "harvest_lecoq_filtered", g.replace(".", "_"))
    pool.setdefault(g, []).extend(
        (os.path.join(tdir, f), "lecoq1912") for f in files)
for g, paths in extra.items():
    if g in pool:   # only augment glyphs we are (re)building
        pool[g].extend((p, "validated_mueller1908") for p in paths)


def load_ink(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    alpha = a[:, :, 3]
    ys, xs = np.nonzero(alpha > 0)
    if len(ys) == 0:
        return None
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gray = a[:, :, :3].mean(axis=2)
    return (a[:, :, 3] / 255.0) * (1.0 - gray / 255.0)


def consensus_of(paths):
    inks = [i for i in (load_ink(p) for p in paths) if i is not None]
    h_med = float(np.median([i.shape[0] for i in inks]))
    scaled = []
    for ink in inks:
        s = CANVAS_H / ink.shape[0]
        nw = max(1, round(ink.shape[1] * s))
        scaled.append(np.asarray(
            Image.fromarray((ink * 255).astype(np.uint8), "L")
            .resize((nw, CANVAS_H), Image.LANCZOS), np.float32) / 255.0)
    W = max(s.shape[1] for s in scaled) + 2 * PAD
    H = CANVAS_H + 2 * PAD
    stack = np.zeros((len(scaled), H, W), np.float32)
    for k, s in enumerate(scaled):
        ys, xs = np.nonzero(s > 0.2)
        oy = int(round(H / 2 - ys.mean()))
        ox = int(round(W / 2 - xs.mean()))
        y0, x0 = max(0, oy), max(0, ox)
        sy0, sx0 = max(0, -oy), max(0, -ox)
        hh = min(s.shape[0] - sy0, H - y0)
        ww = min(s.shape[1] - sx0, W - x0)
        stack[k, y0:y0 + hh, x0:x0 + ww] = s[sy0:sy0 + hh, sx0:sx0 + ww]
    for _ in range(2):
        mean = stack.mean(axis=0)
        for k in range(len(scaled)):
            (dx, dy), _ = cv2.phaseCorrelate(mean, stack[k])
            if abs(dx) > 0.3 or abs(dy) > 0.3:
                M = np.float32([[1, 0, -dx], [0, 1, -dy]])
                stack[k] = cv2.warpAffine(stack[k], M, (W, H))
    cons = stack.mean(axis=0)
    agreement = float(cons[cons >= 0.5].mean()) if (cons >= 0.5).any() else 0.0
    return cons, h_med, agreement


def clean_mask(cons):
    mask = (cons >= 0.5).astype(np.uint8)
    total = mask.sum()
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        if stats[i, 4] < 0.005 * total:
            mask[lab == i] = 0
    stroke = CANVAS_H / 10.0
    inv = (1 - mask).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if x > 0 and y > 0 and x + w < mask.shape[1] and y + h < mask.shape[0]:
            hole = lab == i
            if a < 0.3 * stroke * stroke or float(cons[hole].mean()) > 0.20:
                mask[hole] = 1
    return mask


def bezier_pt(b, t):
    mt = 1 - t
    return (b[0] * mt ** 3 + 3 * b[1] * mt ** 2 * t +
            3 * b[2] * mt * t ** 2 + b[3] * t ** 3)


def fit_cubic(pts, t1, t2, tol, depth=0):
    n = len(pts)
    if n == 2:
        d = np.linalg.norm(pts[1] - pts[0]) / 3
        return [np.array([pts[0], pts[0] + t1 * d, pts[1] + t2 * d, pts[1]])]
    u = np.zeros(n)
    u[1:] = np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
    u /= u[-1]
    for _ in range(3):
        A1 = t1[None, :] * (3 * (1 - u) ** 2 * u)[:, None]
        A2 = t2[None, :] * (3 * (1 - u) * u ** 2)[:, None]
        rhs = (pts - np.outer((1 - u) ** 3 + 3 * (1 - u) ** 2 * u, pts[0])
               - np.outer(3 * (1 - u) * u ** 2 + u ** 3, pts[-1]))
        C11 = (A1 * A1).sum(); C12 = (A1 * A2).sum(); C22 = (A2 * A2).sum()
        X1 = (A1 * rhs).sum(); X2 = (A2 * rhs).sum()
        det = C11 * C22 - C12 * C12
        if abs(det) < 1e-12:
            a1 = a2 = np.linalg.norm(pts[-1] - pts[0]) / 3
        else:
            a1 = (X1 * C22 - X2 * C12) / det
            a2 = (C11 * X2 - C12 * X1) / det
            seglen = np.linalg.norm(pts[-1] - pts[0])
            if a1 < 1e-6 * seglen or a2 < 1e-6 * seglen:
                a1 = a2 = seglen / 3
        bez = np.array([pts[0], pts[0] + t1 * a1, pts[-1] + t2 * a2, pts[-1]])
        curve = np.stack([bezier_pt(bez, t) for t in u])
        err = np.linalg.norm(curve - pts, axis=1)
        i_max = int(err.argmax())
        if err[i_max] < tol:
            return [bez]
        for i in range(1, n - 1):
            t = u[i]
            d0 = bezier_pt(bez, t) - pts[i]
            d1 = (3 * (1 - t) ** 2 * (bez[1] - bez[0]) +
                  6 * (1 - t) * t * (bez[2] - bez[1]) +
                  3 * t ** 2 * (bez[3] - bez[2]))
            denom = (d1 * d1).sum()
            if denom > 1e-12:
                u[i] = np.clip(t - (d0 * d1).sum() / denom, 0, 1)
        u = np.maximum.accumulate(u)
    if depth > 12 or i_max in (0, n - 1):
        return [bez]
    tc = pts[i_max - 1] - pts[i_max + 1]
    nc = np.linalg.norm(tc)
    tc = tc / nc if nc > 0 else t1
    return (fit_cubic(pts[:i_max + 1], t1, tc, tol, depth + 1) +
            fit_cubic(pts[i_max:], -tc, t2, tol, depth + 1))


def fit_contour(pts, tol):
    n = len(pts)
    if n < 4:
        return []
    k = max(2, n // 60)
    corners = []
    for i in range(n):
        a = pts[i] - pts[(i - k) % n]
        b = pts[(i + k) % n] - pts[i]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            continue
        ang = np.degrees(np.arccos(np.clip((a @ b) / (na * nb), -1, 1)))
        if ang > CORNER_DEG:
            corners.append((ang, i))
    corners.sort(reverse=True)
    picked = []
    for ang, i in corners:
        if all(min((i - j) % n, (j - i) % n) > k for j in picked):
            picked.append(i)
    picked.sort()
    if not picked:
        picked = [0]
    beziers = []
    for ci in range(len(picked)):
        i0, i1 = picked[ci], picked[(ci + 1) % len(picked)]
        seg = pts[i0:i1 + 1] if i1 > i0 else np.vstack([pts[i0:], pts[:i1 + 1]])
        if len(seg) < 2:
            continue
        t1 = seg[1] - seg[0]; t2 = seg[-2] - seg[-1]
        n1, n2 = np.linalg.norm(t1), np.linalg.norm(t2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        beziers.extend(fit_cubic(seg, t1 / n1, t2 / n2, tol))
    return beziers


def fit_error(beziers, pts):
    samples = np.vstack([[bezier_pt(b, t) for t in np.linspace(0, 1, 24)]
                         for b in beziers])
    d = np.sqrt(((pts[:, None, :] - samples[None, :, :]) ** 2).sum(-1)).min(1)
    return float(np.sqrt((d ** 2).mean())), float(d.max())


def svg_of(contours_em, vb, fname):
    path = ""
    for bez in contours_em:
        path += f"M {bez[0][0][0]:.1f} {bez[0][0][1]:.1f} "
        for b in bez:
            path += (f"C {b[1][0]:.1f} {b[1][1]:.1f} {b[2][0]:.1f} {b[2][1]:.1f} "
                     f"{b[3][0]:.1f} {b[3][1]:.1f} ")
        path += "Z "
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">'
                f'<path d="{path}" fill="black" fill-rule="nonzero"/></svg>')


def glif_of(contours_em, name, adv, height_em, fname):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<glyph name="{name}" format="2">',
             f' <advance width="{adv:.0f}"/>', " <outline>"]
    for bez in contours_em:
        lines.append("  <contour>")
        x0, y0 = bez[0][0]
        lines.append(f'   <point x="{x0:.1f}" y="{height_em - y0:.1f}" type="curve"/>')
        for b in bez:
            lines.append(f'   <point x="{b[1][0]:.1f}" y="{height_em - b[1][1]:.1f}"/>')
            lines.append(f'   <point x="{b[2][0]:.1f}" y="{height_em - b[2][1]:.1f}"/>')
            lines.append(f'   <point x="{b[3][0]:.1f}" y="{height_em - b[3][1]:.1f}" type="curve"/>')
        lines = lines[:-1] if np.allclose(bez[-1][3], bez[0][0], atol=0.6) else lines
        lines.append("  </contour>")
    lines += [" </outline>", "</glyph>"]
    with open(fname, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


report = []
pages = []
for gname in sorted(pool):
    tagged = pool[gname]
    paths = [p for p, _ in tagged]
    provs = [pr for _, pr in tagged]
    n_all = len(paths)
    n_m = sum(1 for pr in provs if pr == "mueller1908")
    n_l = sum(1 for pr in provs if pr == "lecoq1912")
    n_v = sum(1 for pr in provs if pr.startswith("validated"))
    cons, h_med, agreement = consensus_of(paths)
    mask = clean_mask(cons)
    field = cv2.GaussianBlur(
        cv2.resize(mask.astype(np.float32), None, fx=2, fy=2,
                   interpolation=cv2.INTER_LINEAR), (0, 0), 3.6)

    def smooth_closed(p, w=7):
        kk = np.ones(w) / w
        ext = np.vstack([p[-w:], p, p[:w]])
        sm = np.column_stack([np.convolve(ext[:, d], kk, "same") for d in (0, 1)])
        return sm[w:-w]

    def shoelace(p):
        return 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) -
                         np.dot(p[:, 1], np.roll(p[:, 0], 1)))

    contours = [smooth_closed(np.column_stack([c_[:, 1], c_[:, 0]]) / 2.0)
                for c_ in find_contours(field, 0.5) if len(c_) >= 8]
    contours = [p for p in contours if shoelace(p) >= 40.0]
    beziers_all, pts_all = [], []
    for pts in contours:
        if np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        bez = fit_contour(pts, FIT_TOL)
        if bez:
            beziers_all.append(bez)
            pts_all.append(pts)
    if not beziers_all:
        print(f"{gname}: NO CONTOURS - skipped")
        continue
    errs = [fit_error(b, p) for b, p in zip(beziers_all, pts_all)]
    rms = float(np.mean([e[0] for e in errs]))
    dmax = float(np.max([e[1] for e in errs]))
    em_per_px = anchor_font / anchor_scan * (h_med / CANVAS_H)
    allpts = np.vstack([b.reshape(-1, 2) for bez in beziers_all for b in bez])
    x_min, y_min = allpts.min(axis=0)
    x_max, y_max = allpts.max(axis=0)
    contours_em = [[(b - [x_min, y_min]) * em_per_px for b in bez]
                   for bez in beziers_all]
    w_em = (x_max - x_min) * em_per_px
    h_em = (y_max - y_min) * em_per_px
    fid = "harvest_" + gname.replace(".", "_")
    svg_of(contours_em, f"0 0 {w_em:.0f} {h_em:.0f}",
           os.path.join(OUT, "svg", fid + ".svg"))
    glif_of(contours_em, gname, w_em + 60, h_em,
            os.path.join(OUT, "glif", fid + ".glif"))
    status = "production" if n_all >= PROD_MIN else "draft"
    quality = float(np.clip(agreement, 0, 1) * np.clip(1 - rms / (2 * FIT_TOL), 0, 1))

    pg = Image.new("RGB", (1140, 420), "white")
    dr = ImageDraw.Draw(pg)
    dr.text((10, 6), f"{gname}  M={n_m} LeCoq={n_l} val={n_v} (tot {n_all}) "
            f"status={status} agreement={agreement:.2f} rms={rms:.2f}px "
            f"quality={quality:.2f}", fill=(0, 0, 0))
    rep0 = load_ink(paths[0])
    def paste_gray(arr, x, label):
        im = Image.fromarray((255 - arr * 255).astype(np.uint8), "L")
        im.thumbnail((340, 320))
        pg.paste(im.convert("RGB"), (x, 46))
        dr.text((x, 380), label, fill=(0, 0, 0))
    paste_gray(rep0 / max(rep0.max(), 1e-6), 20, f"first att ({provs[0]})")
    paste_gray(cons, 400, "aligned consensus (mixed ink)")
    fitim = Image.new("L", (int(x_max - x_min) + 8, int(y_max - y_min) + 8), 255)
    fdr = ImageDraw.Draw(fitim)
    for bez in beziers_all:
        for b in bez:
            seq = [tuple(bezier_pt(b, t) - [x_min - 4, y_min - 4])
                   for t in np.linspace(0, 1, 24)]
            fdr.line(seq, fill=0, width=2)
    fitim.thumbnail((340, 320))
    pg.paste(fitim.convert("RGB"), (780, 46))
    dr.text((780, 380), "fitted Bezier outline", fill=(0, 0, 0))
    pages.append(pg)

    gi = ginfo[gname]
    report.append({
        "glyph": gname, "codepoint": gi["codepoint"],
        "unicode_name": gi["unicode_name"], "contextual_form": gi["form"],
        "attestations_total": n_all,
        "provenance": {"mueller1908": n_m, "lecoq1912": n_l,
                       "validated_mueller1908": n_v},
        "status": status,
        "consensus_agreement": round(agreement, 3),
        "n_cubic_segments": int(sum(len(b) for b in beziers_all)),
        "fitting_error_rms_px": round(rms, 3),
        "fitting_error_max_px": round(dmax, 3),
        "outline_quality_score": round(quality, 3),
        "files": {"svg": f"masters/svg/{fid}.svg",
                  "glif": f"masters/glif/{fid}.glif"},
    })
    print(f"{gname:22} M={n_m} L={n_l} v={n_v} [{status:10}] "
          f"agree={agreement:.2f} rms={rms:.2f} q={quality:.2f}")

pages[0].save(os.path.join(OUT, "overlays_harvest.pdf"), save_all=True,
              append_images=pages[1:], resolution=110)
with open(os.path.join(BASE, "outline_report_74.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "source": "harvest_decisions.json (Mueller) + harvest_decisions_lecoq"
                  ".json (Le Coq) + existing validated members; same metal "
                  "type, co-stacked with per-master provenance",
        "production_min": PROD_MIN,
        "n_masters": len(report),
        "production": sum(1 for r in report if r["status"] == "production"),
        "draft": sum(1 for r in report if r["status"] == "draft")},
        "outlines": report}, f, indent=1)
print(f"\n{len(report)} harvest masters -> masters/ ; outline_report_74.json ; "
      "overlays_harvest.pdf")
