"""Phase 8 QA zoom: render 4 joined words at 300px/em, tight-cropped."""
import os

import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
PX = 300
WORDS = [
    ("beth-gimel-mem", ["bethuyg.init", "gimelHethuyg.medi", "memuyg.fina"]),
    ("aleph-shin-kaph", ["alephuyg.init", "shinuyg.medi", "kaphuyg.fina"]),
    ("taw-waw-zayin", ["tawuyg.medi", "wawuyg.medi", "zayinuyg.fina"]),
    ("nun-beth-resh", ["nunuyg.init", "bethuyg.medi", "reshuyg.fina"]),
]
tt = TTFont(NEW)
face = freetype.Face(NEW)
face.set_pixel_sizes(0, PX)
rows = []
for label, seq in WORDS:
    canvas = np.full((PX * 3, PX * 6), 255, np.uint8)
    baseline = PX * 3 // 2
    pen_x = PX * 6 - 60.0
    for gname in seq:
        gid = tt.getGlyphID(gname)
        face.load_glyph(gid, freetype.FT_LOAD_RENDER)
        adv = face.glyph.advance.x / 64.0
        pen_x -= adv
        bm = face.glyph.bitmap
        if bm.rows:
            img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            gx = int(pen_x + face.glyph.bitmap_left)
            gy = int(baseline - face.glyph.bitmap_top)
            h, w = img.shape
            gx2, gy2 = gx + w, gy + h
            sx0, sy0 = max(0, -gx), max(0, -gy)
            gx, gy = max(0, gx), max(0, gy)
            sub = img[sy0:sy0 + (min(gy2, canvas.shape[0]) - gy) if False else sy0 + h - max(0, gy2 - canvas.shape[0]) - sy0 + 0, :]
            # simpler safe paste
            eh = min(h - sy0, canvas.shape[0] - gy)
            ew = min(w - sx0, canvas.shape[1] - gx)
            if eh > 0 and ew > 0:
                region = canvas[gy:gy + eh, gx:gx + ew]
                canvas[gy:gy + eh, gx:gx + ew] = np.minimum(region, 255 - img[sy0:sy0 + eh, sx0:sx0 + ew])
    # crop to ink + margin, draw band lines
    ys, xs = np.nonzero(canvas < 250)
    if len(ys):
        y0, y1 = ys.min() - 20, ys.max() + 20
        x0, x1 = xs.min() - 20, xs.max() + 20
        crop = canvas[max(0, y0):y1, max(0, x0):x1]
    else:
        crop = canvas
    im = Image.merge("RGB", [Image.fromarray(crop)] * 3)
    dr = ImageDraw.Draw(im)
    b0 = baseline - max(0, y0)
    b1 = b0 - int(95 / 1000 * PX)
    dr.line([(0, b0), (im.width, b0)], fill=(0, 210, 0))
    dr.line([(0, b1), (im.width, b1)], fill=(110, 110, 255))
    dr.text((6, 4), label, fill=(200, 0, 0))
    rows.append(im)
W = max(r.width for r in rows)
H = sum(r.height + 8 for r in rows)
sheet = Image.new("RGB", (W, H), "white")
y = 0
for r in rows:
    sheet.paste(r, (W - r.width, y))
    y += r.height + 8
sheet.save(os.path.join(BASE, "qa", "phase8_zoom.png"))
print("phase8_zoom.png", sheet.size)
