"""Phase 3: detect printed Old Uyghur glyphs on Uigurica I scans.

Pipeline per page (36, 38, 40, 42, 44 - the pages carrying Uyghur type):
  1. Otsu binarization (analysis only; exported pixels stay original).
  2. Connected-component analysis (8-connectivity).
  3. Text-line clustering via y-interval merging.
  4. Line classification: a line is Old Uyghur iff it contains >= 2
     curved components wider than UYGHUR_WORD_MIN_W (Latin letters are
     small disconnected components; rules/dashes are straight).
     This removes Latin text, page numbers, titles, footnotes.
  5. Removal of decorative elements inside Uyghur lines:
     - Schnuerloch circles: large hollow ring components
     - lacuna hatching: clusters of >= 3 parallel steep thin strokes
  6. Touching-glyph separation: within a word image, columns where the
     only ink is the plain horizontal connecting baseline (height and
     ink-count ~ stroke thickness) for a run >= MIN_CUT_RUN are cut.
  7. Export each glyph as tight RGBA crop: RGB = original scan pixels,
     alpha = 255 on the glyph's own ink pixels, 0 elsewhere. No
     resampling, no enhancement.

Order: page, then line top-to-bottom, then right-to-left (script order).
Output: glyphs/glyphNNNNNN.png + glyphs.json
"""
import json
import os

import cv2
import numpy as np

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SCANS = os.path.join(BASE, "scans")
OUT = os.path.join(BASE, "glyphs")
QA = os.path.join(BASE, "qa")
PAGES = [36, 38, 40, 42, 44]

# --- tunables (units: pixels at 1200 dpi) ---
EDGE_MARGIN = 60            # drop components touching page edge
MIN_COMP_AREA = 120         # ignore specks smaller than this (dust)
LINE_GAP = 90               # y-gap that separates text lines
UYGHUR_WORD_MIN_W = 350     # a 'long word image' proving a Uyghur line
MIN_UYGHUR_WORDS = 2        # need >= this many long words per line
RING_MIN_SIZE = 500         # Schnuerloch ring bbox size
HATCH_MAX_THICK = 60        # hatching stroke minor-axis limit
HATCH_MIN_LEN = 80          # hatching stroke major-axis min length
HATCH_MAX_LEN = 700
HATCH_MIN_ANGLE = 30.0      # degrees from horizontal
HATCH_CLUSTER_N = 3         # >= parallel neighbors -> hatching
HATCH_NEIGHBOR_DX = 260     # proximity for hatch clustering
MIN_CUT_RUN_FACTOR = 1.6    # min connector run = factor * stroke thickness
CONNECTOR_H_FACTOR = 2.1    # connector column max height = f * stroke
MIN_SEG_W_FACTOR = 1.0      # min segment width = f * stroke thickness

os.makedirs(OUT, exist_ok=True)
os.makedirs(QA, exist_ok=True)


def stroke_thickness(mask):
    """Median ink stroke thickness via distance transform of ink pixels."""
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    vals = dt[mask > 0]
    vals = vals[vals > 0.5]
    return float(np.median(vals) * 2.0) if len(vals) else 24.0


def component_features(mask_u8, stats_row):
    """PCA-based straightness/orientation of one component's ink."""
    ys, xs = np.nonzero(mask_u8)
    pts = np.column_stack([xs, ys]).astype(np.float64)
    pts -= pts.mean(axis=0)
    cov = np.cov(pts.T)
    evals, evecs = np.linalg.eigh(cov)
    minor, major = np.sqrt(max(evals[0], 1e-9)), np.sqrt(max(evals[1], 1e-9))
    v = evecs[:, 1]
    angle = abs(np.degrees(np.arctan2(v[1], v[0])))
    angle = min(angle, 180 - angle)  # fold to [0,90]
    return minor, major, angle


def is_ring(sub, w, h, area):
    """Detect hollow near-circular ring (Schnuerloch)."""
    if w < RING_MIN_SIZE or h < RING_MIN_SIZE:
        return False
    aspect = w / h
    if not (0.72 <= aspect <= 1.38):
        return False
    fill = area / float(w * h)
    if fill > 0.30:
        return False
    # hollow center check
    ch, cw = h // 3, w // 3
    center = sub[h // 2 - ch // 2: h // 2 + ch // 2, w // 2 - cw // 2: w // 2 + cw // 2]
    return center.mean() < 0.05 * 255


def cut_positions(comp_mask, thick):
    """Find x-positions where only the plain connecting baseline runs."""
    h, w = comp_mask.shape
    col_ink = (comp_mask > 0).sum(axis=0)
    ys_any = comp_mask > 0
    y_min = np.full(w, h, dtype=np.int32)
    y_max = np.full(w, -1, dtype=np.int32)
    for x in range(w):
        col = np.nonzero(ys_any[:, x])[0]
        if len(col):
            y_min[x], y_max[x] = col[0], col[-1]
    extent = np.where(y_max >= 0, y_max - y_min + 1, 0)
    conn = (col_ink > 0) & (col_ink <= CONNECTOR_H_FACTOR * thick) & \
           (extent <= CONNECTOR_H_FACTOR * thick)
    min_run = int(MIN_CUT_RUN_FACTOR * thick)
    cuts = []
    x = 0
    while x < w:
        if conn[x]:
            x0 = x
            while x < w and conn[x]:
                x += 1
            if x - x0 >= min_run:
                cuts.append((x0 + x) // 2)
        else:
            x += 1
    return cuts


def segment_component(comp_mask, thick):
    """Split a word image at connector-only column runs; return x-slices."""
    w = comp_mask.shape[1]
    cuts = cut_positions(comp_mask, thick)
    bounds = [0] + cuts + [w]
    min_w = int(MIN_SEG_W_FACTOR * thick)
    slices = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a >= min_w and comp_mask[:, a:b].any():
            slices.append((a, b))
    return slices if len(slices) > 1 else [(0, w)]


def process_page(page_no, counter, records, fout_dir):
    path = os.path.join(SCANS, f"page{page_no}.png")
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    H, W = ink.shape

    n, labels, stats, cents = cv2.connectedComponentsWithStats(ink, connectivity=8)
    thick = stroke_thickness(ink)

    comps = []  # (idx, x, y, w, h, area)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < MIN_COMP_AREA:
            continue
        if x < EDGE_MARGIN or y < EDGE_MARGIN or \
           x + w > W - EDGE_MARGIN or y + h > H - EDGE_MARGIN:
            continue
        comps.append((i, x, y, w, h, area))

    # --- text-line clustering by y-interval merging ---
    intervals = sorted((y, y + h, idx) for idx, x, y, w, h, a in comps)
    lines = []  # [y0, y1, [idx...]]
    for y0, y1, idx in intervals:
        if lines and y0 <= lines[-1][1] + LINE_GAP:
            lines[-1][1] = max(lines[-1][1], y1)
            lines[-1][2].append(idx)
        else:
            lines.append([y0, y1, [idx]])

    by_idx = {c[0]: c for c in comps}
    glyph_boxes = []
    dropped = {"latin_lines": 0, "rings": 0, "hatch": 0}

    for y0, y1, idxs in lines:
        # classify line
        long_words = 0
        for idx in idxs:
            _, x, y, w, h, area = by_idx[idx]
            if w >= UYGHUR_WORD_MIN_W:
                sub = (labels[y:y + h, x:x + w] == idx).astype(np.uint8)
                minor, major, angle = component_features(sub, None)
                if minor > 0.06 * major or angle < 20:  # curved or horizontal
                    if not is_ring(sub * 255, w, h, area):
                        long_words += 1
        if long_words < MIN_UYGHUR_WORDS:
            dropped["latin_lines"] += 1
            continue

        # collect hatch candidates in this line
        feats = {}
        for idx in idxs:
            _, x, y, w, h, area = by_idx[idx]
            sub = (labels[y:y + h, x:x + w] == idx).astype(np.uint8)
            feats[idx] = component_features(sub, None) + (sub,)

        hatch_ids = set()
        cand = [idx for idx in idxs
                if 2 * feats[idx][0] <= HATCH_MAX_THICK
                and HATCH_MIN_LEN <= 2 * feats[idx][1] <= HATCH_MAX_LEN
                and feats[idx][2] >= HATCH_MIN_ANGLE]
        cand.sort(key=lambda i: by_idx[i][1])
        run = []
        for idx in cand:
            if run and by_idx[idx][1] - by_idx[run[-1]][1] <= HATCH_NEIGHBOR_DX:
                run.append(idx)
            else:
                if len(run) >= HATCH_CLUSTER_N:
                    hatch_ids.update(run)
                run = [idx]
        if len(run) >= HATCH_CLUSTER_N:
            hatch_ids.update(run)
        dropped["hatch"] += len(hatch_ids)

        for idx in idxs:
            _, x, y, w, h, area = by_idx[idx]
            sub = feats[idx][3]
            if idx in hatch_ids:
                continue
            if is_ring(sub * 255, w, h, area):
                dropped["rings"] += 1
                continue
            # touching-glyph separation
            for a, b in segment_component(sub, thick):
                seg = sub[:, a:b]
                cols = np.nonzero(seg.any(axis=0))[0]
                rows = np.nonzero(seg.any(axis=1))[0]
                if not len(cols) or not len(rows):
                    continue
                gx = x + a + cols[0]
                gy = y + rows[0]
                gw = cols[-1] - cols[0] + 1
                gh = rows[-1] - rows[0] + 1
                m = seg[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
                glyph_boxes.append((y0, gx, gy, gw, gh, m))

    # order: line top-to-bottom, then right-to-left
    glyph_boxes.sort(key=lambda g: (g[0], -(g[1] + g[3])))

    for line_y, gx, gy, gw, gh, m in glyph_boxes:
        counter[0] += 1
        fname = f"glyph{counter[0]:06d}.png"
        rgba = np.zeros((gh, gw, 4), dtype=np.uint8)
        crop = img[gy:gy + gh, gx:gx + gw]
        rgba[:, :, 0] = crop[:, :, 2]
        rgba[:, :, 1] = crop[:, :, 1]
        rgba[:, :, 2] = crop[:, :, 0]
        rgba[:, :, 3] = m * 255
        cv2.imwrite(os.path.join(fout_dir, fname),
                    cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        records.append({
            "page": page_no,
            "bbox": [int(gx), int(gy), int(gw), int(gh)],
            "filename": fname,
            "width": int(gw),
            "height": int(gh),
        })

    # QA overlay (downscaled)
    qa = img.copy()
    for line_y, gx, gy, gw, gh, m in glyph_boxes:
        cv2.rectangle(qa, (gx, gy), (gx + gw, gy + gh), (0, 0, 255), 6)
    qa_small = cv2.resize(qa, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(QA, f"page{page_no}_boxes.png"), qa_small)

    print(f"page{page_no}: {len(glyph_boxes)} glyphs, stroke~{thick:.0f}px, "
          f"dropped: {dropped}")
    return len(glyph_boxes)


def main():
    counter = [0]
    records = []
    total = 0
    for p in PAGES:
        total += process_page(p, counter, records, OUT)
    with open(os.path.join(BASE, "glyphs.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)
    print(f"TOTAL: {total} glyphs -> glyphs/ ; glyphs.json ({len(records)} records)")


if __name__ == "__main__":
    main()
