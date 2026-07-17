"""Phase 1, step 4: verify Uigurica-Regular.ttf against the source font.

Checks, table by table:
  1. font loads and every table decompiles cleanly
  2. glyph order identical
  3. cmap: every Unicode mapping preserved, all subtables identical
  4. GSUB / GPOS / GDEF binary-identical after recompilation
  5. glyf outlines binary-identical (no outline changed)
  6. hmtx advance/lsb identical
  7. name table carries the new identity
Exits non-zero on any mismatch.
"""
import sys

from fontTools.ttLib import TTFont

SRC = r"C:\Users\KutadguBilim\Font\NotoSerifOldUyghur-fixed.ttf"
NEW = r"C:\Users\KutadguBilim\Font\Uigurica\build\Uigurica-Regular.ttf"

src = TTFont(SRC)
new = TTFont(NEW)
failures = []


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# 1. Full decompile of every table.
bad = []
for tag in new.keys():
    try:
        new[tag]  # forces decompile
    except Exception as e:  # noqa: BLE001
        bad.append((tag, e))
check("all tables decompile", not bad, str(bad) if bad else f"{len(new.keys())} tables")

# 2. Glyph order.
check(
    "glyph order identical",
    src.getGlyphOrder() == new.getGlyphOrder(),
    f"{len(new.getGlyphOrder())} glyphs",
)

# 3. cmap.
src_best, new_best = src.getBestCmap(), new.getBestCmap()
check("cmap best mapping identical", src_best == new_best, f"{len(new_best)} codepoints")
src_subs = {(t.platformID, t.platEncID, t.format): t.cmap for t in src["cmap"].tables}
new_subs = {(t.platformID, t.platEncID, t.format): t.cmap for t in new["cmap"].tables}
check("cmap all subtables identical", src_subs == new_subs, f"{len(new_subs)} subtables")

# 4-6. Binary comparison of layout, outline and metric tables.
for tag in ("GSUB", "GPOS", "GDEF", "glyf", "loca", "hmtx", "cvt ", "fpgm", "prep", "gasp", "post", "OS/2", "hhea", "maxp"):
    if tag not in src:
        continue
    s = src[tag].compile(src)
    n = new[tag].compile(new)
    check(f"{tag.strip()} binary identical", s == n, f"{len(n)} bytes")

# 7. New identity.
nm = new["name"]
ident = {i: nm.getDebugName(i) for i in (1, 2, 4, 6)}
check(
    "name table identity",
    ident == {1: "Uigurica", 2: "Regular", 4: "Uigurica Regular", 6: "Uigurica-Regular"},
    str(ident),
)
# fontRevision is 16.16 fixed-point; 0.100 stores as ~0.1000061.
check("head.fontRevision", abs(new["head"].fontRevision - 0.100) < 1 / 65536 + 1e-9, str(new["head"].fontRevision))

# 8. Old Uyghur shaping sanity: GSUB has ougr script with init/medi/fina.
gsub = new["GSUB"].table
ougr = next((s for s in gsub.ScriptList.ScriptRecord if s.ScriptTag == "ougr"), None)
check("GSUB has ougr script", ougr is not None)
if ougr:
    feat_idx = ougr.Script.DefaultLangSys.FeatureIndex
    tags = {gsub.FeatureList.FeatureRecord[i].FeatureTag for i in feat_idx}
    need = {"init", "medi", "fina"}
    check("ougr has init/medi/fina", need <= tags, str(sorted(tags)))

print()
if failures:
    print(f"{len(failures)} FAILURE(S):", failures)
    sys.exit(1)
print("ALL CHECKS PASSED")
