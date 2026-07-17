"""Phase 10: version bump to 1.000 + name/head/OS2 metadata for release.

Metadata only - no glyph outline or metric is touched here. Updates:
  head.fontRevision -> 1.000
  name IDs 3 (Unique ID), 5 (Version string) -> 1.000
  name ID 5 keeps the Noto provenance line
Writes build/Uigurica-Regular-v1.0.ttf (the release binary) and leaves
build/Uigurica-Regular.ttf as the working copy (also updated to match).
"""
import os

from fontTools.ttLib import TTFont

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SRC = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
REL = os.path.join(BASE, "build", "Uigurica-Regular-v1.0.ttf")
VER = "1.000"
VSTR = ("Version 1.000; Uigurica " + VER +
        "; glyph designs from F.W.K. Mueller, Uigurica I (1908) and "
        "A. von Le Coq, Tuerkische Manichaica I (1912); "
        "technical base Noto Serif Old Uyghur 1.004")
UID = f"1.000;UIGR;Uigurica-Regular;Mueller1908+LeCoq1912"

tt = TTFont(SRC)
tt["head"].fontRevision = 1.000
name = tt["name"]
# Phase1 Noto base uses only the Windows platform (3,1,0x409); match it and
# never emit legacy Mac (platformID 1) records (fontbakery mac-names FAIL).
name.removeNames(platformID=1)
for nid, val in [(3, UID), (5, VSTR)]:
    name.setName(val, nid, 3, 1, 0x409)
# ensure family/subfamily/full/postscript are Uigurica (already, but assert)
assert name.getDebugName(1) == "Uigurica"
assert name.getDebugName(6) == "Uigurica-Regular"
tt.save(SRC)
tt.save(REL)
print("version ->", tt["head"].fontRevision)
print("ID3:", name.getDebugName(3))
print("ID5:", name.getDebugName(5))
print("wrote", os.path.basename(REL))
