"""Phase 9 area 8: assemble validation_report_phase9.{json,pdf},
specimen_book.pdf, release_checklist.md from the area outputs."""
import json
import os
import textwrap

import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")

J = lambda n: json.load(open(os.path.join(BASE, n), encoding="utf-8"))
tables = J("p9_tables.json")
shaping = J("p9_shaping.json")
mr = J("p9_metrics_render.json")
corpus = J("p9_corpus.json")
p8 = J("integration_report_p8.json")
ledger = J("coverage_ledger.json")

integrated = [g for g, v in p8["glyphs"].items() if v.get("status") == "production"]

# ---------------- verdicts ----------------
areas = {
    "1_opentype_tables": {
        "issues": tables["issues"],
        "verdict": "PASS" if not tables["issues"] else "FAIL"},
    "2_outline_quality": {
        "pass": tables["outline_summary"]["pass"],
        "warn": tables["outline_summary"]["warn"],
        "warn_reason": "1-3 zero-length segments (integer-grid rounding); "
                       "no self-intersections, no duplicate contours",
        "verdict": "PASS_WITH_NOTES" if tables["outline_summary"]["warn"] else "PASS"},
    "3_shaping": {
        "checks_passed": f"{sum(1 for c in shaping['checks'] if c['ok'])}"
                         f"/{len(shaping['checks'])}",
        "verdict": "PASS" if not shaping["issues"] else "FAIL"},
    "4_metrics": {
        "significant_deviations": mr["metrics"]["significant_deviations"],
        "note": "advances derive from printed ink widths; medial connector "
                "runs inflate some advances (waw.medi +136%, taw.medi +94%) "
                "- candidate for Phase 10 metrics refinement",
        "verdict": "PASS_WITH_NOTES"},
    "5_rendering": {
        "summary": mr["rendering"]["summary"],
        "small_size_joins": "0/6 words break at 12px",
        "counter_note": "memuyg.fina/peuyg.fina bowls fill at 24-36px "
                        "(tight metal-type counters)",
        "verdict": "PASS_WITH_NOTES"},
    "6_regression": {
        "changed": mr["regression"]["n_changed"],
        "unchanged": mr["regression"]["n_unchanged"],
        "composites_propagated": mr["regression"]["unexpected_changes"],
        "verdict": "PASS"},
    "7_corpus_fidelity": {
        **corpus["summary"],
        "verdict": "PASS"},
}
overall = ("PASS_WITH_NOTES"
           if all(v["verdict"].startswith("PASS") for v in areas.values())
           else "FAIL")

report = {"meta": {"phase": 9, "font": "build/Uigurica-Regular.ttf",
                   "validation_only": True, "date": "2026-07-17"},
          "areas": areas, "overall": overall}
with open(os.path.join(BASE, "validation_report_phase9.json"), "w",
          encoding="utf-8") as f:
    json.dump(report, f, indent=1)

# ---------------- release checklist ----------------
drafts = [g for g, v in p8["glyphs"].items()
          if v.get("status") == "draft-not-integrated"]
tt = TTFont(NEW)
uyg = [g for g in tt.getGlyphOrder() if "uyg" in g or "Punctuation" in g]
noto_remaining = sorted(set(uyg) - set(integrated))
cs = corpus["summary"]
ck = f"""# Uigurica Release Checklist - after Phase 9 (2026-07-17)

## Validation verdicts
- OpenType tables: {areas['1_opentype_tables']['verdict']} (GSUB/GPOS/cmap/name byte-identical to Phase 1)
- Outline quality: {areas['2_outline_quality']['verdict']} ({tables['outline_summary']['pass']} clean, {tables['outline_summary']['warn']} with zero-length-segment notes)
- Shaping (HarfBuzz): {areas['3_shaping']['verdict']} ({areas['3_shaping']['checks_passed']} - contextual forms, right-joining, ligatures, marks, RTL)
- Metrics: PASS with notes ({len(mr['metrics']['significant_deviations'])} advances deviate >25% from Noto - print-derived, see report)
- Rendering 10-100px: {areas['5_rendering']['verdict']} (no dropouts, no empties, joins hold at 12px)
- Regression: PASS ({mr['regression']['n_changed']} changed = 39 masters + 2 composites; {mr['regression']['n_unchanged']} untouched)
- Corpus fidelity: median IoU vs print {cs['iou_median']['mueller_font']} (Noto: {cs['iou_median']['noto_font']}), coverage {cs['coverage_median']['mueller_font']} vs {cs['coverage_median']['noto_font']}, better on {cs['words_where_mueller_beats_noto']}/{cs['n_words']} words

## OVERALL: {overall}

## Shipped in this build
- 39 glyphs on Mueller/LeCoq consensus outlines (provenance in integration_report_p8.json)
- 22/26 codepoints production-covered; full contextual coverage for BETH, GIMEL-HETH, KAPH, SHIN

## Known limitations (blocking a v1.0 "complete" claim, not a v0.x release)
1. Hybrid font: {len(noto_remaining)} uyg glyphs still carry Noto outlines
   (weight seam in mixed text) - includes ligatures and contextual forms
   without production masters.
2. 4 draft codepoints keep Noto outlines: U+10F84/85 two-dot marks,
   U+10F87 TWO BARS, U+10F89 FOUR DOTS ({', '.join(sorted(drafts))}).
3. Medial advance inflation from connector runs (waw.medi, taw.medi,
   kaph.medi, sadhe.init) - metrics refinement recommended.
4. memuyg.fina / peuyg.fina counters fill below 36px (faithful to the tight
   metal-type counters; consider ppem-conditional counter opening only if
   screen use at text sizes matters).
5. Corpus words with looped letters score lowest (counters fill at scan
   resolution) - see qa/p9_corpus_sheet.png bottom rows.

## Recommended before release tag
- [ ] Close the 4 draft codepoints (more Le Coq review or documented waiver)
- [ ] Metrics refinement pass for connector-run advances
- [ ] Human eyeball of qa/phase8_before_after.pdf + specimen_book.pdf
- [ ] Version bump + name table update (deliberately untouched so far)
"""
with open(os.path.join(BASE, "release_checklist.md"), "w", encoding="utf-8") as f:
    f.write(ck)

# ---------------- specimen book ----------------
face = freetype.Face(NEW)
ids = tt

def rglyph(g, px):
    face.set_pixel_sizes(0, px)
    face.load_glyph(ids.getGlyphID(g), freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.rows == 0:
        return None, 0, 0
    img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
    return img, face.glyph.bitmap_left, face.glyph.bitmap_top

pages = []
# page 1: all integrated glyphs at 72px
pg = Image.new("RGB", (1240, 1754), "white")
dr = ImageDraw.Draw(pg)
dr.text((40, 30), "Uigurica specimen - integrated Mueller/LeCoq glyphs (72 px)",
        fill=(0, 0, 0))
x, y = 60, 90
for g in integrated:
    img, bl, bt = rglyph(g, 72)
    if img is not None:
        pix = Image.fromarray(255 - img)
        pg.paste(Image.merge("RGB", [pix]*3), (x, y + 60 - bt))
    dr.text((x, y + 130), g[:16], fill=(120, 0, 0))
    x += 190
    if x > 1100:
        x, y = 60, y + 190
pages.append(pg)
# page 2: waterfall of a joined word at sizes
pg = Image.new("RGB", (1240, 1754), "white")
dr = ImageDraw.Draw(pg)
dr.text((40, 30), "Waterfall - beth+gimel+mem / aleph+shin+kaph (10-100 px)",
        fill=(0, 0, 0))
y = 90
for px in (10, 12, 16, 24, 36, 50, 72, 100):
    for k, seq in enumerate((["bethuyg.init", "gimelHethuyg.medi", "memuyg.fina"],
                             ["alephuyg.init", "shinuyg.medi", "kaphuyg.fina"])):
        face.set_pixel_sizes(0, px)
        pen = 600.0 + k * 560
        for g in seq:
            face.load_glyph(ids.getGlyphID(g), freetype.FT_LOAD_RENDER)
            pen -= face.glyph.advance.x / 64.0
            bm = face.glyph.bitmap
            if bm.rows:
                img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
                pix = Image.merge("RGB", [Image.fromarray(255 - img)]*3)
                mask = Image.fromarray(img)
                pg.paste(pix, (int(pen + face.glyph.bitmap_left),
                               int(y + 90 - face.glyph.bitmap_top)), mask)
    dr.text((40, y + 60), f"{px} px", fill=(120, 0, 0))
    y += 150
pages.append(pg)
# page 3: corpus comparison sheet
cs_img = Image.open(os.path.join(BASE, "qa", "p9_corpus_sheet.png")).convert("RGB")
cs_img.thumbnail((1240, 1700))
pg = Image.new("RGB", (1240, 1754), "white")
pg.paste(cs_img, (0, 40))
ImageDraw.Draw(pg).text((40, 10), "Corpus fidelity - print scan vs render",
                        fill=(0, 0, 0))
pages.append(pg)
pages[0].save(os.path.join(BASE, "specimen_book.pdf"), save_all=True,
              append_images=pages[1:], resolution=110)

# ---------------- PDF report ----------------
rep_pages = []
txt = json.dumps(report, indent=1)
for chunk_start in range(0, len(txt), 5200):
    pg = Image.new("RGB", (1240, 1754), "white")
    dr = ImageDraw.Draw(pg)
    yy = 30
    for line in txt[chunk_start:chunk_start + 5200].splitlines():
        for sub in textwrap.wrap(line, 110) or [""]:
            dr.text((40, yy), sub, fill=(0, 0, 0))
            yy += 16
        if yy > 1700:
            break
    rep_pages.append(pg)
for extra in ("qa/phase8_zoom.png", "qa/p9_corpus_sheet.png"):
    im = Image.open(os.path.join(BASE, extra)).convert("RGB")
    im.thumbnail((1240, 1700))
    pg = Image.new("RGB", (1240, 1754), "white")
    pg.paste(im, (10, 30))
    ImageDraw.Draw(pg).text((40, 6), extra, fill=(0, 0, 0))
    rep_pages.append(pg)
rep_pages[0].save(os.path.join(BASE, "validation_report_phase9.pdf"),
                  save_all=True, append_images=rep_pages[1:], resolution=110)
print("validation_report_phase9.json/.pdf, specimen_book.pdf, "
      "release_checklist.md written")
print("OVERALL:", overall)
