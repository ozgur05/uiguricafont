"""Phase 10: complete font specimen -> specimen_v1.pdf.

Sections: cover; alphabet (isolated, all 18 letters + 4 marks + 4 punct);
contextual forms table (init/medi/fina/isol per letter, HarfBuzz-shaped);
ligatures; punctuation & diacritics; continuous text (shaped paragraphs);
Mueller-scan comparison (integrated render vs original scans).
Rendering via FreeType; shaping via HarfBuzz. Read-only.
"""
import json
import os

import freetype
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
REL = os.path.join(BASE, "build", "Uigurica-Regular-v1.0.ttf")
PAGE = (1240, 1754)
tt = TTFont(REL)
face = freetype.Face(REL)
blob = hb.Blob.from_file_path(REL)
hbfont = hb.Font(hb.Face(blob))

CP = {"aleph": 0x10F70, "beth": 0x10F71, "gimel-heth": 0x10F72, "waw": 0x10F73,
      "zayin": 0x10F74, "final-heth": 0x10F75, "yodh": 0x10F76, "kaph": 0x10F77,
      "lamedh": 0x10F78, "mem": 0x10F79, "nun": 0x10F7A, "samekh": 0x10F7B,
      "pe": 0x10F7C, "sadhe": 0x10F7D, "resh": 0x10F7E, "shin": 0x10F7F,
      "taw": 0x10F80, "lesh": 0x10F81}
MARKS = {"dot-above": 0x10F82, "dot-below": 0x10F83,
         "two-dots-above": 0x10F84, "two-dots-below": 0x10F85}
PUNCT = {"bar": 0x10F86, "two-bars": 0x10F87, "two-dots": 0x10F88,
         "four-dots": 0x10F89}


def blank():
    im = Image.new("RGB", PAGE, "white")
    return im, ImageDraw.Draw(im)


def draw_shaped(im, text, x, baseline, px, rtl=True, color=(0, 0, 0)):
    face.set_pixel_sizes(0, px)
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    infos, poss = buf.glyph_infos, buf.glyph_positions
    width = sum(p.x_advance for p in poss) / 1000.0 * px
    penx = x + (width if rtl else 0)
    # HB already returns visual order; advance layout left to right using
    # cluster advances but start position accounts for RTL width
    penx = x
    for gi, gp in zip(infos, poss):
        face.load_glyph(gi.codepoint, freetype.FT_LOAD_RENDER)
        bm = face.glyph.bitmap
        ox = penx + (gp.x_offset / 1000.0 * px) + face.glyph.bitmap_left
        oy = baseline - (gp.y_offset / 1000.0 * px) - face.glyph.bitmap_top
        if bm.rows:
            arr = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
            pix = Image.fromarray(255 - arr)
            solid = Image.new("RGB", pix.size, color)
            im.paste(solid, (int(ox), int(oy)), Image.fromarray(arr))
        penx += gp.x_advance / 1000.0 * px
    return width


def glyph_img(gname, px):
    face.set_pixel_sizes(0, px)
    face.load_glyph(tt.getGlyphID(gname), freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.rows == 0:
        return None, 0, 0
    arr = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
    return arr, face.glyph.bitmap_left, face.glyph.bitmap_top

pages = []

# ---- cover ----
im, dr = blank()
dr.text((90, 300), "UIGURICA", fill=(20, 20, 20))
dr.text((90, 340), "A Unicode Old Uyghur typeface", fill=(80, 80, 80))
dr.text((90, 380), "Glyph designs from F. W. K. Mueller, Uigurica I (1908)",
        fill=(80, 80, 80))
dr.text((90, 402), "and A. von Le Coq, Tuerkische Manichaica I (1912)",
        fill=(80, 80, 80))
dr.text((90, 440), "Version 1.000  -  Specimen", fill=(80, 80, 80))
draw_shaped(im, chr(CP["beth"]) + chr(CP["gimel-heth"]) + chr(CP["mem"]),
            760, 380, 150)
pages.append(im)

# ---- alphabet (isolated) ----
im, dr = blank()
dr.text((70, 50), "Alphabet - isolated forms (18 letters)", fill=(0, 0, 0))
x, y = 90, 150
for nm, cp in CP.items():
    arr, bl, bt = glyph_img(tt.getBestCmap()[cp], 96)
    if arr is not None:
        im.paste(Image.merge("RGB", [Image.fromarray(255 - arr)]*3),
                 (x, y - bt + 96))
    dr.text((x, y + 140), nm, fill=(120, 0, 0))
    x += 200
    if x > 1050:
        x, y = 90, y + 240
dr.text((70, y + 260), "Diacritics", fill=(0, 0, 0))
x = 90; yy = y + 340
for nm, cp in MARKS.items():
    # render on a dotted circle base for visibility
    draw_shaped(im, "◌" + chr(cp), x, yy + 96, 96)
    dr.text((x, yy + 150), nm, fill=(120, 0, 0))
    x += 260
pages.append(im)

# ---- contextual forms table ----
im, dr = blank()
dr.text((70, 50), "Contextual forms (HarfBuzz-shaped: isolated / initial / "
        "medial / final)", fill=(0, 0, 0))
y = 130
for nm, cp in CP.items():
    c = chr(cp); b = chr(CP["beth"])
    dr.text((70, y + 30), nm, fill=(120, 0, 0))
    seqs = [c, c + b, b + c + b, b + c]           # isol, init, medi, fina
    x = 320
    for s in seqs:
        draw_shaped(im, s, x, y + 70, 64)
        x += 220
    y += 92
    if y > 1650:
        pages.append(im); im, dr = blank(); y = 80
for lbl in ("isolated", "initial", "medial", "final"):
    pass
pages.append(im)

# ---- ligatures + punctuation ----
im, dr = blank()
dr.text((70, 50), "Ligatures & punctuation", fill=(0, 0, 0))
ligs = [g for g in tt.getGlyphOrder() if "_" in g and "uyg" in g][:12]
y = 140
dr.text((70, y), "Ligature glyphs (by name):", fill=(0, 0, 0))
y += 40
x = 90
for g in ligs:
    arr, bl, bt = glyph_img(g, 80)
    if arr is not None:
        im.paste(Image.merge("RGB", [Image.fromarray(255 - arr)]*3),
                 (x, y - bt + 80))
    dr.text((x, y + 110), g.replace("uyg", "")[:16], fill=(120, 0, 0))
    x += 300
    if x > 950:
        x, y = 90, y + 210
y += 240
dr.text((70, y), "Punctuation:", fill=(0, 0, 0))
y += 40
x = 90
for nm, cp in PUNCT.items():
    draw_shaped(im, chr(cp), x, y + 80, 96)
    dr.text((x, y + 130), nm, fill=(120, 0, 0))
    x += 260
pages.append(im)

# ---- continuous text ----
im, dr = blank()
dr.text((70, 50), "Continuous text (shaped paragraphs)", fill=(0, 0, 0))
letters = list(CP.values())
import itertools
# build pseudo-words from validated letters (no linguistic claim; layout demo)
rng = [
    [CP["beth"], CP["gimel-heth"], CP["mem"]],
    [CP["aleph"], CP["shin"], CP["kaph"]],
    [CP["nun"], CP["beth"], CP["resh"]],
    [CP["lamedh"], CP["samekh"], CP["beth"]],
    [CP["taw"], CP["waw"], CP["zayin"]],
    [CP["sadhe"], CP["gimel-heth"], CP["final-heth"]],
    [CP["yodh"], CP["mem"], CP["shin"]],
    [CP["pe"], CP["kaph"], CP["waw"], CP["mem"]],
]
for px in (72, 54, 40, 30):
    y = 150 if px == 72 else y + px + 60
    x = 1150
    line = 0
    for w in rng:
        s = "".join(chr(c) for c in w)
        wwidth = draw_shaped(im, s, 0, 0, px)  # measure
        x -= wwidth + px * 0.5
        if x < 80:
            break
        draw_shaped(im, s, x, y, px)
    dr.text((70, y - px), f"{px}px", fill=(150, 0, 0))
pages.append(im)

# ---- Mueller scan comparison ----
cs = Image.open(os.path.join(BASE, "qa", "p9_corpus_sheet.png")).convert("RGB")
cs.thumbnail((1180, 1650))
im, dr = blank()
dr.text((60, 20), "Comparison with Mueller scans (left: print scan, "
        "right: Uigurica render)", fill=(0, 0, 0))
im.paste(cs, (30, 60))
pages.append(im)

pages[0].save(os.path.join(BASE, "specimen_v1.pdf"), save_all=True,
              append_images=pages[1:], resolution=120)
print(f"specimen_v1.pdf written ({len(pages)} pages)")
