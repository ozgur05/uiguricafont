"""Phase 3 (final): glyph segmentation dataset from Uigurica I pp. 36-45.

Fixes over the first attempt (detect_glyphs.py):
  - scan-border strips (tall components near page edge) removed BEFORE
    line clustering; they previously merged all lines into one cluster
  - long-word test no longer accepts straight horizontal components
    (rules, dashes); requires curvature AND w>=500 AND h>=100
  - dust threshold raised to 300 px^2 (a printed diacritic dot is ~600+)
  - stroke thickness = 4 * median(distance transform) ~= 13 px
  - records include area, centroid, aspect ratio
  - outputs: segments/ (RGBA crops), segments.json, glyphs.json (alias),
    contact_sheet.pdf, qa/ overlays, validation report

Only pages 36/38/40/42/44 carry Old Uyghur type (37/39/41/43/45 are
Latin transliteration + German, verified visually).
"""
import json
import os

import cv2
import numpy as np

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SCANS = os.path.join(BASE, "scans")
SEG = os.path.join(BASE, "segments")
QA = os.path.join(BASE, "qa")
PAGES = [36, 38, 40, 42, 44]

EDGE_FRAME = 200          # reject components intersecting outer frame
MAX_COMP_H = 1000         # taller = scan artifact (text max ~450)
MAX_COMP_W = 4000         # wider = rule/border (longest word ~2700)
MIN_COMP_AREA = 300       # dust threshold
LINE_GAP = 120            # y-gap merging for line clustering
LONG_W, LONG_H = 500, 60   # 'long Uyghur word' proof dimensions
MIN_LONG_WORDS = 2
CURVE_RATIO = 0.02        # PCA minor/major: rules ~0.004, flat words >=0.03
RING_MIN = 500
HATCH = dict(max_thick=60, min_len=80, max_len=700, min_angle=30.0,
             cluster_n=4, neighbor_dx=260)
CUT_H_FACTOR = 3.0        # connector col height <= f*stroke (~38px)
CUT_MIN_RUN = 60          # px; real inter-letter connectors are 100-350px,
                          # within-letter flat spots are <= ~52px
MIN_SEG_W_FACTOR = 1.2

os.makedirs(SEG, exist_ok=True)
os.makedirs(QA, exist_ok=True)


def pca_features(sub):
    ys, xs = np.nonzero(sub)
    pts = np.column_stack([xs, ys]).astype(np.float64)
    pts -= pts.mean(axis=0)
    cov = np.cov(pts.T) if len(pts) > 1 else np.eye(2)
    evals, evecs = np.linalg.eigh(cov)
    minor = np.sqrt(max(evals[0], 1e-9))
    major = np.sqrt(max(evals[1], 1e-9))
    v = evecs[:, 1]
    ang = abs(np.degrees(np.arctan2(v[1], v[0])))
    return minor, major, min(ang, 180 - ang)


def is_ring(sub, w, h, area):
    if w < RING_MIN or h < RING_MIN:
        return False
    if not (0.72 <= w / h <= 1.38):
        return False
    if area / float(w * h) > 0.30:
        return False
    ch, cw = h // 3, w // 3
    c = sub[h // 2 - ch // 2:h // 2 + ch // 2, w // 2 - cw // 2:w // 2 + cw // 2]
    return c.mean() < 0.05


def segment_word(sub, stroke):
    """Split at column runs where only the plain baseline connector runs."""
    h, w = sub.shape
    col_ink = sub.sum(axis=0)
    y_top = np.argmax(sub, axis=0)
    y_bot = h - 1 - np.argmax(sub[::-1], axis=0)
    extent = np.where(col_ink > 0, y_bot - y_top + 1, 0)
    lim = CUT_H_FACTOR * stroke
    conn = (col_ink > 0) & (col_ink <= lim) & (extent <= lim)
    min_run = CUT_MIN_RUN
    cuts, x = [], 0
    while x < w:
        if conn[x]:
            x0 = x
            while x < w and conn[x]:
                x += 1
            if x - x0 >= min_run:
                cuts.append((x0 + x) // 2)
        else:
            x += 1
    bounds = [0] + cuts + [w]
    min_w = int(MIN_SEG_W_FACTOR * stroke)
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a >= min_w and sub[:, a:b].any():
            out.append((a, b))
    return out if out else [(0, w)]


def process_page(page_no, counter, records, report):
    img = cv2.imread(os.path.join(SCANS, f"page{page_no}.png"), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    H, W = ink.shape

    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    v = dt[ink > 0]
    stroke = float(4 * np.median(v[v > 0.5]))

    n, labels, stats, cents = cv2.connectedComponentsWithStats(ink, connectivity=8)
    rep = dict(raw=0, dust=0, edge=0, artifact=0, latin=0, ring=0, hatch=0, kept=0)
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        rep["raw"] += 1
        if area < MIN_COMP_AREA:
            rep["dust"] += 1
            continue
        if x < EDGE_FRAME or y < EDGE_FRAME or \
           x + w > W - EDGE_FRAME or y + h > H - EDGE_FRAME:
            rep["edge"] += 1
            continue
        if h > MAX_COMP_H or w > MAX_COMP_W:
            rep["artifact"] += 1
            continue
        comps.append((i, x, y, w, h, area))

    # line clustering
    lines = []
    for y0, y1, idx in sorted((c[2], c[2] + c[4], c[0]) for c in comps):
        if lines and y0 <= lines[-1][1] + LINE_GAP:
            lines[-1][1] = max(lines[-1][1], y1)
            lines[-1][2].append(idx)
        else:
            lines.append([y0, y1, [idx]])

    by_idx = {c[0]: c for c in comps}
    boxes = []
    for y0, y1, idxs in lines:
        subs, feats = {}, {}
        for idx in idxs:
            _, x, y, w, h, a = by_idx[idx]
            subs[idx] = (labels[y:y + h, x:x + w] == idx).astype(np.uint8)
            feats[idx] = pca_features(subs[idx])
        long_words = sum(
            1 for idx in idxs
            if by_idx[idx][3] >= LONG_W and by_idx[idx][4] >= LONG_H
            and feats[idx][0] > CURVE_RATIO * feats[idx][1]
            and not is_ring(subs[idx], by_idx[idx][3], by_idx[idx][4], by_idx[idx][5]))
        if long_words < MIN_LONG_WORDS:
            rep["latin"] += len(idxs)
            continue

        # hatching: clusters of parallel steep thin strokes
        hatch_ids = set()
        cand = [i for i in idxs
                if 2 * feats[i][0] <= HATCH["max_thick"]
                and HATCH["min_len"] <= 2 * feats[i][1] <= HATCH["max_len"]
                and feats[i][2] >= HATCH["min_angle"]]
        cand.sort(key=lambda i: by_idx[i][1])
        run = []
        for i in cand:
            if run and by_idx[i][1] - by_idx[run[-1]][1] <= HATCH["neighbor_dx"]:
                run.append(i)
            else:
                if len(run) >= HATCH["cluster_n"]:
                    hatch_ids.update(run)
                run = [i]
        if len(run) >= HATCH["cluster_n"]:
            hatch_ids.update(run)

        # expand each hatch cluster to a zone: any component lying fully
        # between the cluster's extremes (merged double-strokes etc.) is
        # part of the lacuna marking, not a glyph
        if hatch_ids:
            hx0 = min(by_idx[i][1] for i in hatch_ids)
            hx1 = max(by_idx[i][1] + by_idx[i][3] for i in hatch_ids)
            hy0 = min(by_idx[i][2] for i in hatch_ids)
            hy1 = max(by_idx[i][2] + by_idx[i][4] for i in hatch_ids)
            for idx in idxs:
                _, x, y, w, h, a = by_idx[idx]
                if idx not in hatch_ids and x >= hx0 - 30 and x + w <= hx1 + 30 \
                        and y >= hy0 - 60 and y + h <= hy1 + 60:
                    hatch_ids.add(idx)
        rep["hatch"] += len(hatch_ids)

        # rings (Schnuerloch): detect first, then also drop anything whose
        # bbox lies inside a ring (the small inner circle of the mark)
        ring_boxes = []
        for idx in idxs:
            _, x, y, w, h, a = by_idx[idx]
            if is_ring(subs[idx], w, h, a):
                ring_boxes.append((x, y, w, h))

        for idx in idxs:
            _, x, y, w, h, a = by_idx[idx]
            if idx in hatch_ids:
                continue
            if any(x >= rx and y >= ry and x + w <= rx + rw and y + h <= ry + rh
                   for rx, ry, rw, rh in ring_boxes):
                rep["ring"] += 1
                continue
            if is_ring(subs[idx], w, h, a):
                rep["ring"] += 1
                continue
            for s0, s1 in segment_word(subs[idx], stroke):
                seg = subs[idx][:, s0:s1]
                cols = np.nonzero(seg.any(axis=0))[0]
                rows = np.nonzero(seg.any(axis=1))[0]
                m = seg[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
                boxes.append((y0, x + s0 + cols[0], y + rows[0],
                              int(cols[-1] - cols[0] + 1),
                              int(rows[-1] - rows[0] + 1), m))

    boxes.sort(key=lambda g: (g[0], -(g[1] + g[3])))
    rep["kept"] = len(boxes)

    for line_y, gx, gy, gw, gh, m in boxes:
        counter[0] += 1
        fname = f"glyph{counter[0]:06d}.png"
        crop = img[gy:gy + gh, gx:gx + gw]
        rgba = np.dstack([crop[:, :, 2], crop[:, :, 1], crop[:, :, 0], m * 255])
        cv2.imwrite(os.path.join(SEG, fname), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        area = int(m.sum())
        ys, xs = np.nonzero(m)
        records.append({
            "page": page_no,
            "bbox": [int(gx), int(gy), int(gw), int(gh)],
            "area": area,
            "centroid": [round(float(gx + xs.mean()), 1), round(float(gy + ys.mean()), 1)],
            "aspect_ratio": round(gw / gh, 3),
            "filename": fname,
            "width": gw,
            "height": gh,
        })

    qa = img.copy()
    for line_y, gx, gy, gw, gh, m in boxes:
        cv2.rectangle(qa, (gx, gy), (gx + gw, gy + gh), (0, 0, 255), 6)
    cv2.imwrite(os.path.join(QA, f"page{page_no}_boxes.png"),
                cv2.resize(qa, (W // 8, H // 8), interpolation=cv2.INTER_AREA))

    report[page_no] = rep
    print(f"page{page_no}: stroke~{stroke:.1f}px kept={rep['kept']} "
          f"rejected: dust={rep['dust']} edge={rep['edge']} "
          f"artifact={rep['artifact']} latin={rep['latin']} "
          f"ring={rep['ring']} hatch={rep['hatch']}")


def main():
    counter, records, report = [0], [], {}
    for p in PAGES:
        process_page(p, counter, records, report)

    with open(os.path.join(BASE, "segments.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)
    with open(os.path.join(BASE, "glyphs.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)

    # --- validation estimates ---
    widths = np.array([r["width"] for r in records])
    med_w = float(np.median(widths))
    merged = int((widths > 2.4 * med_w).sum())
    split = int((widths < 0.25 * med_w).sum())
    small = int(np.sum(np.array([r["area"] for r in records]) < 900))
    tot = {k: sum(rep[k] for rep in report.values())
           for k in ("raw", "dust", "edge", "artifact", "latin", "ring", "hatch", "kept")}
    print("\n=== VALIDATION ===")
    print(f"total raw components: {tot['raw']}")
    print(f"kept glyph segments:  {tot['kept']}")
    print(f"rejected: dust={tot['dust']} edge/border={tot['edge']} "
          f"artifact={tot['artifact']} latin/page-numbers={tot['latin']} "
          f"rings={tot['ring']} hatching={tot['hatch']}")
    print(f"median segment width: {med_w:.0f}px")
    print(f"estimated MERGED glyphs (w > 2.4x median, still letter groups): {merged}")
    print(f"estimated SPLIT fragments (w < 0.25x median): {split}")
    print(f"low-confidence small segments (area < 900 px^2, kept): {small}")

    with open(os.path.join(BASE, "segmentation_report.json"), "w") as f:
        json.dump({"per_page": report, "totals": tot,
                   "median_width": med_w, "estimated_merged": merged,
                   "estimated_split_fragments": split,
                   "low_confidence_small": small}, f, indent=1)

    contact_sheet(records)


def contact_sheet(records):
    """Tile all crops (composited on white) into a multi-page PDF."""
    from PIL import Image, ImageDraw

    COLS, ROWS = 8, 11
    CELL_W, CELL_H = 250, 200
    THUMB_H = 150
    PAGE_W, PAGE_H = COLS * CELL_W, ROWS * CELL_H + 40
    pages, pos = [], 0
    per_page = COLS * ROWS
    while pos < len(records):
        sheet = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(sheet)
        batch = records[pos:pos + per_page]
        for k, r in enumerate(batch):
            im = Image.open(os.path.join(SEG, r["filename"])).convert("RGBA")
            scale = min(THUMB_H / im.height, (CELL_W - 20) / im.width, 1.0)
            if scale < 1.0:
                im = im.resize((max(1, int(im.width * scale)),
                                max(1, int(im.height * scale))), Image.LANCZOS)
            cx = (k % COLS) * CELL_W
            cy = (k // COLS) * CELL_H
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert("RGB"),
                        (cx + (CELL_W - im.width) // 2,
                         cy + (THUMB_H - im.height) // 2 + 10))
            draw.text((cx + 8, cy + THUMB_H + 18),
                      f"{r['filename'][5:11]} p{r['page']} {r['width']}x{r['height']}",
                      fill="black")
        draw.text((10, PAGE_H - 24),
                  f"Uigurica Phase 3 contact sheet - {pos + 1}..{pos + len(batch)} of {len(records)}",
                  fill="black")
        pages.append(sheet)
        pos += per_page
    pages[0].save(os.path.join(BASE, "contact_sheet.pdf"), save_all=True,
                  append_images=pages[1:], resolution=150)
    print(f"contact_sheet.pdf: {len(pages)} sheet pages")


if __name__ == "__main__":
    main()
