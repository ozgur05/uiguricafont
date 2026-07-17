"""Phase 3.5: normalize every glyph segment + compute shape descriptors.

Per segment (from segments/):
  1. trim transparent margins
  2. preserve aspect ratio, uniform scale, Lanczos resample
  3. center on canvas
  4. emit normalized versions: 64x64, 96x96, 128x128
     (mode L, black ink on white; normalized/64|96|128/normNNNNNN.png)
  5. compute descriptors -> segment_features.json
     - Hu moments (log-scaled, from original-resolution mask)
     - Zernike moments (numpy implementation, order<=8, magnitudes,
       computed on the 128x128 normalized ink; mahotas has no cp314 wheel)
     - contour descriptors (counts, perimeter, compactness, solidity,
       extent, eccentricity, orientation)
     - skeleton metrics (length, endpoints, branchpoints) + skeleton PNG
     - stroke density and stroke width

No classification, no clustering, no Unicode, no font comparison.
"""
import json
import math
import os

import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SEG = os.path.join(BASE, "segments")
NRM = os.path.join(BASE, "normalized")
SKEL = os.path.join(BASE, "features", "skeletons")
SIZES = (64, 96, 128)

for s in SIZES:
    os.makedirs(os.path.join(NRM, str(s)), exist_ok=True)
os.makedirs(SKEL, exist_ok=True)

records = json.load(open(os.path.join(BASE, "segments.json"), encoding="utf-8"))


# ---------- Zernike moments (numpy; standard definition, unit disk) ------
def zernike_magnitudes(img, order=8):
    """|A_nm| for n<=order, m>=0, n-m even. img: 2D float ink map."""
    h, w = img.shape
    ys, xs = np.mgrid[0:h, 0:w]
    x = (xs - (w - 1) / 2) / ((w - 1) / 2)
    y = (ys - (h - 1) / 2) / ((h - 1) / 2)
    rho = np.hypot(x, y)
    theta = np.arctan2(y, x)
    disk = rho <= 1.0
    wgt = img * disk
    mass = wgt.sum()
    if mass <= 0:
        return {}
    out = {}
    for n in range(order + 1):
        for m in range(n % 2, n + 1, 2):
            R = np.zeros_like(rho)
            for k in range((n - m) // 2 + 1):
                c = ((-1) ** k * math.factorial(n - k) /
                     (math.factorial(k) * math.factorial((n + m) // 2 - k) *
                      math.factorial((n - m) // 2 - k)))
                R += c * rho ** (n - 2 * k)
            V = R * np.exp(-1j * m * theta)
            A = (n + 1) / np.pi * (wgt * V)[disk].sum() / mass
            out[f"z{n}_{m}"] = round(float(abs(A)), 6)
    return out


def skeleton_metrics(mask):
    sk = skeletonize(mask > 0)
    n_px = int(sk.sum())
    if n_px == 0:
        return sk, 0, 0, 0
    nb = cv2.filter2D(sk.astype(np.uint8), -1,
                      np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], np.uint8),
                      borderType=cv2.BORDER_CONSTANT)
    ends = int(((nb == 1) & sk).sum())
    branches = int(((nb >= 3) & sk).sum())
    return sk, n_px, ends, branches


features = []
zernike_note = ("numpy implementation (order<=8, magnitudes, on 128x128 "
                "normalized ink); mahotas unavailable for Python 3.14")

for r in records:
    im = Image.open(os.path.join(SEG, r["filename"])).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    alpha = a[:, :, 3]

    # 1. trim transparent margins
    ys, xs = np.nonzero(alpha > 0)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    a = a[y0:y1, x0:x1]
    alpha = alpha[y0:y1, x0:x1]
    gray = a[:, :, :3].mean(axis=2)
    ink = (alpha / 255.0) * (1.0 - gray / 255.0)  # 0..1
    h, w = ink.shape
    mask = (alpha > 127).astype(np.uint8)

    # 2-4. normalized canvases
    norm128 = None
    for S in SIZES:
        scale = S / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        ink_s = np.asarray(Image.fromarray((ink * 255).astype(np.uint8), "L")
                           .resize((nw, nh), Image.LANCZOS), dtype=np.float32) / 255.0
        canvas = np.zeros((S, S), np.float32)
        dx, dy = (S - nw) // 2, (S - nh) // 2
        canvas[dy:dy + nh, dx:dx + nw] = ink_s
        if S == 128:
            norm128 = canvas
        Image.fromarray((255 - canvas * 255).astype(np.uint8), "L").save(
            os.path.join(NRM, str(S), r["filename"].replace("glyph", "norm")))

    # 5a. Hu moments (log-scaled) on original-resolution mask
    hu = cv2.HuMoments(cv2.moments(mask, binaryImage=True)).flatten()
    hu_log = [round(float(-np.sign(v) * np.log10(abs(v))), 6) if v != 0 else 0.0
              for v in hu]

    # 5b. Zernike
    zern = zernike_magnitudes(norm128)

    # 5c. contour descriptors -- on a lightly CLOSED mask: the halftone
    # dithering of the source print riddles the raw mask with sub-stroke
    # holes (200+ per word), which would swamp hole counts, perimeter and
    # skeleton branchpoints with noise. 5x5 closing is well below stroke
    # scale (~13px) and does not alter letterform topology.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cmask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cnts, hier = cv2.findContours(cmask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    n_outer = n_holes = 0
    perim = 0.0
    if hier is not None:
        for i, c in enumerate(cnts):
            perim += cv2.arcLength(c, True)
            if hier[0][i][3] == -1:
                n_outer += 1
            else:
                n_holes += 1
    area = float(cmask.sum())
    compactness = float(4 * np.pi * area / perim ** 2) if perim > 0 else 0.0
    hull = cv2.convexHull(np.column_stack(np.nonzero(cmask)[::-1]))
    hull_area = float(cv2.contourArea(hull)) if len(hull) >= 3 else area
    solidity = round(area / hull_area, 5) if hull_area > 0 else 1.0
    extent = round(area / (w * h), 5)
    ecc = orient = 0.0
    big = max(cnts, key=cv2.contourArea) if cnts else None
    if big is not None and len(big) >= 5:
        (cx_, cy_), (MA, ma), ang = cv2.fitEllipse(big)
        if max(MA, ma) > 0:
            b_, a_ = sorted((MA, ma))
            ecc = round(math.sqrt(max(0.0, 1 - (b_ / a_) ** 2)), 5)
            orient = round(ang, 2)

    # 5d. skeleton (on the closed mask, same rationale as contours)
    sk, sk_len, sk_ends, sk_branch = skeleton_metrics(cmask)
    Image.fromarray(np.where(sk, 0, 255).astype(np.uint8), "L").save(
        os.path.join(SKEL, r["filename"].replace("glyph", "skel")))

    # 5e. stroke density / width (raw mask for density; closed for width)
    dt = cv2.distanceTransform(cmask, cv2.DIST_L2, 5)
    sw = float(2 * dt[sk].mean()) if sk_len else 0.0
    density = round(area / (w * h), 5)

    features.append({
        "filename": r["filename"],
        "page": r["page"],
        "bbox": r["bbox"],
        "trimmed_size": [int(w), int(h)],
        "normalized": {str(S): f"normalized/{S}/" +
                       r["filename"].replace("glyph", "norm") for S in SIZES},
        "hu_moments_log": hu_log,
        "zernike": zern,
        "contour": {
            "n_contours": n_outer, "n_holes": n_holes,
            "perimeter": round(perim, 1), "area": area,
            "compactness": round(compactness, 5), "solidity": solidity,
            "extent": extent, "eccentricity": ecc, "orientation_deg": orient,
        },
        "skeleton": {
            "length_px": sk_len, "endpoints": sk_ends,
            "branchpoints": sk_branch,
            "image": "features/skeletons/" + r["filename"].replace("glyph", "skel"),
        },
        "stroke": {"density": density, "width_mean_px": round(sw, 2)},
    })

meta = {"zernike_implementation": zernike_note,
        "canvas_sizes": list(SIZES),
        "count": len(features),
        "mask_note": ("hu_moments and stroke.density use the raw ink mask; "
                      "contour and skeleton descriptors use a 5x5-closed "
                      "mask to suppress halftone micro-holes of the source "
                      "print (stroke ~13px, closing well below that)")}
with open(os.path.join(BASE, "segment_features.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": meta, "segments": features}, f, indent=1)

print(f"normalized {len(features)} segments at {SIZES} -> normalized/")
print(f"skeletons -> features/skeletons/ ; descriptors -> segment_features.json")
