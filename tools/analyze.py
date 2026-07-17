"""Phase 1, step 1: analyze NotoSerifOldUyghur-fixed.ttf structure."""
import sys

import fontTools
from fontTools.ttLib import TTFont

SRC = r"C:\Users\KutadguBilim\Font\NotoSerifOldUyghur-fixed.ttf"

print("fontTools version:", fontTools.version)
font = TTFont(SRC)

print("\n== Tables ==")
print(sorted(font.keys()))

print("\n== Basic metrics ==")
head = font["head"]
print("unitsPerEm:", head.unitsPerEm)
maxp = font["maxp"]
print("numGlyphs:", maxp.numGlyphs)
hhea = font["hhea"]
print("ascent/descent/lineGap:", hhea.ascent, hhea.descent, hhea.lineGap)
os2 = font["OS/2"]
print("OS/2 version:", os2.version, "usWeightClass:", os2.usWeightClass)
print("fsType:", os2.fsType)

print("\n== name table (key IDs) ==")
name = font["name"]
for nid in (0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17):
    rec = name.getDebugName(nid)
    if rec:
        print(f"  {nid}: {rec}")

print("\n== cmap ==")
cmap_table = font["cmap"]
for sub in cmap_table.tables:
    print(f"  subtable: platformID={sub.platformID} platEncID={sub.platEncID} format={sub.format} entries={len(sub.cmap) if hasattr(sub, 'cmap') else '?'}")
best = font.getBestCmap()
print("best cmap size:", len(best))
uy = sorted(cp for cp in best if 0x10F70 <= cp <= 0x10FAF)
print("Old Uyghur block codepoints mapped:", len(uy))
print("range:", hex(min(uy)), "-", hex(max(uy)) if uy else "none")
other = sorted(cp for cp in best if not (0x10F70 <= cp <= 0x10FAF))
print("non-OldUyghur codepoints:", [f"U+{cp:04X}" for cp in other])

print("\n== GlyphOrder ==")
go = font.getGlyphOrder()
print("count:", len(go))
print("first 20:", go[:20])
print("last 10:", go[-10:])

for tag in ("GSUB", "GPOS", "GDEF"):
    print(f"\n== {tag} ==")
    if tag not in font:
        print("  (absent)")
        continue
    t = font[tag].table
    if tag in ("GSUB", "GPOS"):
        scripts = [s.ScriptTag for s in t.ScriptList.ScriptRecord] if t.ScriptList else []
        feats = [f.FeatureTag for f in t.FeatureList.FeatureRecord] if t.FeatureList else []
        nlk = t.LookupList.LookupCount if t.LookupList else 0
        print("  scripts:", scripts)
        print("  features:", sorted(set(feats)), f"({len(feats)} records)")
        print("  lookups:", nlk)
        if t.LookupList:
            from collections import Counter
            types = Counter(lk.LookupType for lk in t.LookupList.Lookup)
            print("  lookup types:", dict(types))
    else:
        print("  GlyphClassDef:", bool(t.GlyphClassDef))
        if t.GlyphClassDef:
            from collections import Counter
            print("  class counts:", dict(Counter(t.GlyphClassDef.classDefs.values())))
        print("  MarkAttachClassDef:", bool(t.MarkAttachClassDef))
        print("  LigCaretList:", bool(t.LigCaretList))
        print("  AttachList:", bool(t.AttachList))

print("\nOK")
