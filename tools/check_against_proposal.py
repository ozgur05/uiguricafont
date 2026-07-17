"""Cross-check NotoSerifOldUyghur-fixed.ttf against L2/20-191 (final proposal).

Verifies for each of the 26 encoded Old Uyghur characters:
  - cmap presence
  - joining behavior implemented in GSUB (init/medi/fina coverage)
against the proposal's normative model:
  - 18 letters: all dual-joining EXCEPT zayin (right) and final heth (right)
  - 4 combining marks (should be GDEF class 3, carry mark anchors)
  - 4 punctuation signs (non-joining)
Also checks script extensions U+0640 (tatweel) and U+10AF2 (Manichaean
double dot within dot) that the proposal specifies for Old Uyghur.
"""
from fontTools.ttLib import TTFont

SRC = r"C:\Users\KutadguBilim\Font\NotoSerifOldUyghur-fixed.ttf"
font = TTFont(SRC)
cmap = font.getBestCmap()
gsub = font["GSUB"].table
gdef = font["GDEF"].table.GlyphClassDef.classDefs

# L2/20-191 normative joining (section 6.6/6.8; note: section 9.4 line for
# zayin says 'D' but 6.6/6.8 and the document history say right-joining).
LETTERS = {
    0x10F70: ("ALEPH", "dual"), 0x10F71: ("BETH", "dual"),
    0x10F72: ("GIMEL-HETH", "dual"), 0x10F73: ("WAW", "dual"),
    0x10F74: ("ZAYIN", "right"), 0x10F75: ("FINAL HETH", "right"),
    0x10F76: ("YODH", "dual"), 0x10F77: ("KAPH", "dual"),
    0x10F78: ("LAMEDH", "dual"), 0x10F79: ("MEM", "dual"),
    0x10F7A: ("NUN", "dual"), 0x10F7B: ("SAMEKH", "dual"),
    0x10F7C: ("PE", "dual"), 0x10F7D: ("SADHE", "dual"),
    0x10F7E: ("RESH", "dual"), 0x10F7F: ("SHIN", "dual"),
    0x10F80: ("TAW", "dual"), 0x10F81: ("LESH", "dual"),
}
MARKS = {0x10F82: "COMBINING DOT ABOVE", 0x10F83: "COMBINING DOT BELOW",
         0x10F84: "COMBINING TWO DOTS ABOVE", 0x10F85: "COMBINING TWO DOTS BELOW"}
PUNCT = {0x10F86: "PUNCTUATION BAR", 0x10F87: "PUNCTUATION TWO BARS",
         0x10F88: "PUNCTUATION TWO DOTS", 0x10F89: "PUNCTUATION FOUR DOTS"}

# Build feature -> single-sub mapping (which base glyphs have init/medi/fina).
feat_subs = {"init": {}, "medi": {}, "fina": {}}
feat_lookups = {}
for rec in gsub.FeatureList.FeatureRecord:
    if rec.FeatureTag in feat_subs:
        feat_lookups.setdefault(rec.FeatureTag, set()).update(rec.Feature.LookupListIndex)

def collect_single_subs(lookup, out):
    for st in lookup.SubTable:
        if st.LookupType == 7:  # extension
            st = st.ExtSubTable
        if hasattr(st, "mapping"):
            out.update(st.mapping)

for tag, idxs in feat_lookups.items():
    for i in idxs:
        collect_single_subs(gsub.LookupList.Lookup[i], feat_subs[tag])

print(f"{'cp':8} {'name':22} {'joining':7} {'glyph':22} init  medi  fina  verdict")
conflicts = []
for cp, (nm, joining) in sorted(LETTERS.items()):
    g = cmap.get(cp)
    if not g:
        conflicts.append(f"U+{cp:04X} {nm}: NOT IN CMAP")
        continue
    has = {t: g in feat_subs[t] for t in ("init", "medi", "fina")}
    if joining == "dual":
        ok = all(has.values())
    else:  # right-joining: fina only
        ok = has["fina"] and not has["init"] and not has["medi"]
    mark = "OK" if ok else "CONFLICT"
    if not ok:
        conflicts.append(
            f"U+{cp:04X} {nm}: proposal says {joining}-joining, font has "
            f"init={has['init']} medi={has['medi']} fina={has['fina']}")
    print(f"U+{cp:04X} {nm:22} {joining:7} {g:22} {str(has['init']):5} {str(has['medi']):5} {str(has['fina']):5} {mark}")

print()
for cp, nm in sorted(MARKS.items()):
    g = cmap.get(cp)
    cls = gdef.get(g)
    ok = g and cls == 3
    if not ok:
        conflicts.append(f"U+{cp:04X} {nm}: expected GDEF mark class 3, got {cls}")
    print(f"U+{cp:04X} {nm:28} glyph={g} GDEF class={cls} {'OK' if ok else 'CONFLICT'}")

print()
for cp, nm in sorted(PUNCT.items()):
    g = cmap.get(cp)
    joins = any(g in feat_subs[t] for t in feat_subs)
    ok = g and not joins
    if not ok:
        conflicts.append(f"U+{cp:04X} {nm}: missing or unexpectedly joining")
    print(f"U+{cp:04X} {nm:28} glyph={g} joins={joins} {'OK' if ok else 'CONFLICT'}")

print()
for cp, nm in ((0x0640, "ARABIC TATWEEL (script ext)"), (0x10AF2, "MANICHAEAN PUNCT DOUBLE DOT (script ext)"),
               (0x200C, "ZWNJ (terminal connections, sec 8.4)"), (0x25CC, "DOTTED CIRCLE (mark display)")):
    g = cmap.get(cp)
    print(f"U+{cp:04X} {nm:44} {'present: ' + g if g else 'ABSENT'}")
    if not g:
        conflicts.append(f"U+{cp:04X} {nm}: absent from cmap")

print()
if conflicts:
    print(f"{len(conflicts)} CONFLICT(S):")
    for c in conflicts:
        print(" -", c)
else:
    print("NO CONFLICTS between Noto implementation and L2/20-191 model")
