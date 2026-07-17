"""Phase 1, step 3: build Uigurica-Regular.ttf from the fixed Noto source.

Strictly a re-identification build:
  - family name -> "Uigurica"
  - PostScript name -> "Uigurica-Regular"
  - version string updated, provenance kept in the name table
Everything else (glyf outlines, cmap, GSUB, GPOS, GDEF, metrics, hinting)
is carried over untouched.
"""
import os

from fontTools.ttLib import TTFont

SRC = r"C:\Users\KutadguBilim\Font\NotoSerifOldUyghur-fixed.ttf"
OUT_DIR = r"C:\Users\KutadguBilim\Font\Uigurica\build"
OUT = os.path.join(OUT_DIR, "Uigurica-Regular.ttf")
os.makedirs(OUT_DIR, exist_ok=True)

FAMILY = "Uigurica"
SUBFAMILY = "Regular"
FULL = f"{FAMILY} {SUBFAMILY}"
PSNAME = "Uigurica-Regular"
VERSION = "Version 0.100"
UNIQUE_ID = f"0.100;UIGR;{PSNAME}"

font = TTFont(SRC)
name = font["name"]

# Name records to set (Windows platform 3/1/0x409 and Mac 1/0/0 both handled
# by setName for every platform already present in the table).
new_names = {
    1: FAMILY,
    2: SUBFAMILY,
    3: UNIQUE_ID,
    4: FULL,
    5: f"{VERSION}; based on Noto Serif Old Uyghur 1.004 (fixed)",
    6: PSNAME,
    # Typographic family/subfamily: set explicitly so apps don't fall back
    # to stale values (source has none, but be safe).
    16: FAMILY,
    17: SUBFAMILY,
}

# Description record documenting provenance (Phase 1 = technical foundation).
new_names[10] = (
    "Uigurica: a Unicode Old Uyghur font project based on the printed forms "
    "of F. W. K. Mueller's Uigurica I. Phase 1 technical foundation derived "
    "from Noto Serif Old Uyghur (SIL OFL 1.1); glyph outlines and OpenType "
    "shaping unchanged."
)

platforms = sorted({(r.platformID, r.platEncID, r.langID) for r in name.names})
for nid, value in new_names.items():
    for platID, encID, langID in platforms:
        name.setName(value, nid, platID, encID, langID)

# head.fontRevision to match the version string.
font["head"].fontRevision = 0.100

font.save(OUT)
print("wrote", OUT, f"({os.path.getsize(OUT)} bytes)")
