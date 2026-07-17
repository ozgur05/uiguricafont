"""Render the glyphs/pairs implicated by the join audit for inspection."""
import os

import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
PX = 220
tt = TTFont(NEW)
face = freetype.Face(NEW)
face.set_pixel_sizes(0, PX)

PAIRS = [("bethuyg.init", "leshuyg.fina"), ("bethuyg.init", "nunuyg.medi"),
         ("bethuyg.init", "peuyg.fina"), ("gimelHethuyg.init", "peuyg.fina")]
SOLO = ["sadheuyg.init", "gimelHethuyg.init", "bethuyg.init", "peuyg.fina"]

def draw_seq(seq):
    W, H, OY = PX * 5, PX * 3, PX * 3 // 2
    canvas = np.full((H, W), 255, np.uint8)
    pen = W - 60.0
    for g in seq:
        face.load_glyph(tt.getGlyphID(g), freetype.FT_LOAD_RENDER)
        pen -= face.glyph.advance.x / 64.0
        bm = face.glyph.bitmap
        if bm.rows:
            img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            gx, gy = int(pen + face.glyph.bitmap_left), int(OY - face.glyph.bitmap_top)
            h, w = img.shape
            sx0, sy0 = max(0, -gx), max(0, -gy)
            eh, ew = min(h - sy0, H - max(0, gy)), min(w - sx0, W - max(0, gx))
            if eh > 0 and ew > 0:
                r = canvas[max(0,gy):max(0,gy)+eh, max(0,gx):max(0,gx)+ew]
                canvas[max(0,gy):max(0,gy)+eh, max(0,gx):max(0,gx)+ew] = \
                    np.minimum(r, 255 - img[sy0:sy0+eh, sx0:sx0+ew])
    ys, xs = np.nonzero(canvas < 250)
    y0, y1, x0, x1 = ys.min()-14, ys.max()+14, xs.min()-14, xs.max()+14
    crop = canvas[max(0,y0):y1, max(0,x0):x1]
    im = Image.merge("RGB", [Image.fromarray(crop)] * 3)
    dr = ImageDraw.Draw(im)
    b0 = OY - max(0, y0)
    dr.line([(0, b0), (im.width, b0)], fill=(0, 210, 0))
    dr.line([(0, b0 - int(95/1000*PX)), (im.width, b0 - int(95/1000*PX))],
            fill=(110, 110, 255))
    return im

tiles = [(f"{a} + {b}", draw_seq([a, b])) for a, b in PAIRS]
tiles += [(g, draw_seq([g])) for g in SOLO]
W = max(t.width for _, t in tiles) + 20
H = sum(t.height + 34 for _, t in tiles)
sheet = Image.new("RGB", (W, H), "white")
dr = ImageDraw.Draw(sheet)
y = 0
for label, t in tiles:
    dr.text((6, y + 2), label, fill=(200, 0, 0))
    sheet.paste(t, (10, y + 18))
    y += t.height + 34
sheet.save(os.path.join(BASE, "qa", "phase8_offenders.png"))
print("done", sheet.size)
