"""Phase 8 QA: before/after outline sheet + FreeType joined specimen.

Renders every replaced glyph from the backup (Noto) and the new font side by
side with the joining band (y 0..95) marked, then renders RTL-joined test
words from the NEW font at the shaped-glyph level (manual RTL layout with
our advances; GSUB not exercised - glyphs are addressed by name).
"""
import json
import os

import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
OLD = os.path.join(BASE, "build", "Uigurica-Regular.phase1-noto.ttf")
rep = json.load(open(os.path.join(BASE, "integration_report_p8.json"), encoding="utf-8"))
glyphs = [g for g, v in rep["glyphs"].items() if v.get("status") == "production"]

PX_EM = 120  # pixels per em for rendering


def render(fontpath, gname, tt):
    face = freetype.Face(fontpath)
    face.set_pixel_sizes(0, PX_EM)
    gid = tt.getGlyphID(gname)
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width] if bm.rows else np.zeros((1, 1), np.uint8)
    return img, face.glyph.bitmap_left, face.glyph.bitmap_top, face.glyph.advance.x / 64.0


tt_new = TTFont(NEW)
tt_old = TTFont(OLD)

# ---------- before/after sheet ----------
CELL_W, CELL_H = 340, 260
ORIGIN_Y = 170          # baseline row inside cell
cols = 2
pages = []
per_page = 8
for start in range(0, len(glyphs), per_page):
    chunk = glyphs[start:start + per_page]
    pg = Image.new("RGB", (CELL_W * 2 + 220, CELL_H * len(chunk) + 30), "white")
    dr = ImageDraw.Draw(pg)
    dr.text((10, 6), "Phase 8 before(Noto) / after(Mueller-LeCoq master); "
            "green=baseline y0, blue=join band 0..95", fill=(0, 0, 0))
    for row, g in enumerate(chunk):
        ytop = 30 + row * CELL_H
        dr.text((10, ytop + 8), g, fill=(180, 0, 0))
        dr.text((10, ytop + 24), f"adv {rep['glyphs'][g]['advance']['old']}"
                f"->{rep['glyphs'][g]['advance']['new']}", fill=(0, 0, 0))
        for col, (fp, tt) in enumerate([(OLD, tt_old), (NEW, tt_new)]):
            img, bl, bt, adv = render(fp, g, tt)
            ox = 220 + col * CELL_W
            oy = ytop + ORIGIN_Y
            # band + baseline
            band0 = oy - int(0 / 1000 * PX_EM)
            band1 = oy - int(95 / 1000 * PX_EM)
            dr.line([(ox, band0), (ox + CELL_W - 20, band0)], fill=(0, 200, 0))
            dr.line([(ox, band1), (ox + CELL_W - 20, band1)], fill=(80, 80, 255))
            if img.size > 1:
                pix = Image.fromarray(255 - img)
                pg.paste(Image.merge("RGB", (pix, pix, pix)),
                         (ox + 30 + bl, oy - bt))
            dr.text((ox + 30, ytop + CELL_H - 26),
                    "Noto" if col == 0 else "master", fill=(0, 0, 0))
    pages.append(pg)
pages[0].save(os.path.join(BASE, "qa", "phase8_before_after.pdf"),
              save_all=True, append_images=pages[1:], resolution=100)
print("phase8_before_after.pdf:", len(pages), "pages")

# ---------- joined specimen (manual RTL layout from NEW font) ----------
WORDS = [
    # (label, glyph sequence in logical order first->last letter)
    ("beth-gimel-mem", ["bethuyg.init", "gimelHethuyg.medi", "memuyg.fina"]),
    ("aleph-shin-kaph", ["alephuyg.init", "shinuyg.medi", "kaphuyg.fina"]),
    ("taw-waw-zayin(Rjoin)", ["tawuyg.medi", "wawuyg.medi", "zayinuyg.fina"]),
    ("lamedh-samekh-beth", ["lamedhuyg.init", "samekhuyg.medi", "bethuyg.fina"]),
    ("nun-beth-resh", ["nunuyg.init", "bethuyg.medi", "reshuyg.fina"]),
    ("sadhe-gimel-finalHeth", ["sadheuyg.init", "gimelHethuyg.medi", "finalHethuyg.fina"]),
    ("isolated row", ["bethuyg", "gimelHethuyg", "kaphuyg", "yodhuyg", "leshuyg", "shinuyg"]),
    ("punct: bar twodots", ["PunctuationBar", "PunctuationTwoDots"]),
]
face = freetype.Face(NEW)
face.set_pixel_sizes(0, PX_EM)
H = 200 * len(WORDS) + 40
sheet = Image.new("RGB", (1500, H), "white")
dr = ImageDraw.Draw(sheet)
dr.text((10, 8), "Phase 8 joined specimen - NEW font, manual RTL layout "
        "(advances as merged); baseline green, band top blue", fill=(0, 0, 0))
y = 40
for label, seq in WORDS:
    dr.text((10, y + 10), label, fill=(180, 0, 0))
    baseline = y + 130
    dr.line([(200, baseline), (1480, baseline)], fill=(0, 220, 0))
    dr.line([(200, baseline - int(95 / 1000 * PX_EM)),
             (1480, baseline - int(95 / 1000 * PX_EM))], fill=(120, 120, 255))
    # RTL: first letter at the right; pen moves left by each advance
    pen_x = 1440.0
    for gname in seq:
        gid = tt_new.getGlyphID(gname)
        face.load_glyph(gid, freetype.FT_LOAD_RENDER)
        adv = face.glyph.advance.x / 64.0
        pen_x -= adv
        bm = face.glyph.bitmap
        if bm.rows:
            img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            pix = Image.fromarray(255 - img)
            gx = int(pen_x + face.glyph.bitmap_left)
            gy = int(baseline - face.glyph.bitmap_top)
            # multiply-paste (ink overlaps at joins must not erase)
            region = sheet.crop((gx, gy, gx + pix.width, gy + pix.height))
            arr = np.minimum(np.asarray(region)[:, :, 0], np.asarray(pix))
            sheet.paste(Image.merge("RGB", [Image.fromarray(arr)] * 3), (gx, gy))
        pen_x -= 0  # no tracking
    y += 200
sheet.save(os.path.join(BASE, "qa", "phase8_specimen.png"))
print("phase8_specimen.png done")
