"""Phase 1, step 2: extract cmap, GSUB, GPOS, GDEF, GlyphOrder to TTX files.

Each table is dumped as standalone TTX XML under extracted/ so it can be
inspected, diffed, and re-imported later. Also writes a plain-text
GlyphOrder list and a cmap summary for human reading.
"""
import os

from fontTools.ttLib import TTFont

SRC = r"C:\Users\KutadguBilim\Font\NotoSerifOldUyghur-fixed.ttf"
OUT = r"C:\Users\KutadguBilim\Font\Uigurica\extracted"
os.makedirs(OUT, exist_ok=True)

font = TTFont(SRC)

# Per-table TTX dumps (GlyphOrder is included automatically alongside each,
# but we also dump it explicitly).
for tag in ("cmap", "GSUB", "GPOS", "GDEF", "GlyphOrder"):
    path = os.path.join(OUT, f"{tag.strip()}.ttx")
    font.saveXML(path, tables=[tag])
    print("wrote", path)

# Full-font TTX for reference (all tables).
full = os.path.join(OUT, "NotoSerifOldUyghur-fixed.full.ttx")
font.saveXML(full)
print("wrote", full)

# Human-readable glyph order.
with open(os.path.join(OUT, "glyph_order.txt"), "w", encoding="utf-8") as f:
    for i, g in enumerate(font.getGlyphOrder()):
        f.write(f"{i}\t{g}\n")
print("wrote glyph_order.txt")

# Human-readable cmap: codepoint -> glyph name.
best = font.getBestCmap()
with open(os.path.join(OUT, "cmap_summary.txt"), "w", encoding="utf-8") as f:
    for cp in sorted(best):
        f.write(f"U+{cp:04X}\t{best[cp]}\n")
print("wrote cmap_summary.txt", f"({len(best)} mappings)")

print("OK")
