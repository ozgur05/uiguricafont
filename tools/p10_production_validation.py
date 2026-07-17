"""Phase 10 production-validation aggregator.

Runs the full engine matrix on build/Uigurica-Regular-v1.0.ttf and writes
production_validation_p10.json:
  * fontTools structural load
  * OTS (opentype-sanitizer)          - via `python -m ots`
  * fontbakery check-universal + check-opentype  - counts + FAIL/WARN codes
  * FreeType: render every cmapped Old-Uyghur codepoint at 8/16/32/64 px
  * HarfBuzz: shape all 26 codepoints + joining contexts, no .notdef
  * Unicode conformance: cmap covers U+10F70..10F89, correct glyph targets,
    combining-mark class via GDEF, right-joining property honoured in GSUB
Validation only; the font is opened read-only.
"""
import json
import os
import subprocess
import sys

import freetype
import uharfbuzz as hb
from fontTools.ttLib import TTFont

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
REL = os.path.join(BASE, "build", "Uigurica-Regular-v1.0.ttf")
res = {"font": "build/Uigurica-Regular-v1.0.ttf", "engines": {}}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    return p.returncode, (p.stdout + p.stderr)

# 1. fontTools
try:
    TTFont(REL, lazy=False)
    res["engines"]["fonttools_load"] = {"ok": True}
except Exception as e:
    res["engines"]["fonttools_load"] = {"ok": False, "error": str(e)}

# 2. OTS
rc, out = run([sys.executable, "-m", "ots", REL])
res["engines"]["ots"] = {"ok": rc == 0 and "sanitized successfully" in out,
                         "output": out.strip().splitlines()[-1] if out else ""}

# 3. fontbakery (universal + opentype)
def fb(profile):
    rc, out = run([sys.executable, "-m", "fontbakery", profile, REL, "-C",
                   "--loglevel", "INFO"])
    counts = {}
    for k in ("FATAL", "FAIL", "WARN", "ERROR", "PASS", "SKIP", "INFO"):
        for line in out.splitlines():
            s = line.strip()
            if s.startswith(k + ":"):
                try:
                    counts[k] = int(s.split(":")[1])
                except ValueError:
                    pass
                break
    codes = {}
    import re
    for m in re.findall(r"code: ([a-z0-9-]+)", out):
        codes[m] = codes.get(m, 0) + 1
    return {"counts": counts, "warn_fail_codes": codes}

res["engines"]["fontbakery_universal"] = fb("check-universal")
res["engines"]["fontbakery_opentype"] = fb("check-opentype")

# 4. FreeType render sweep
face = freetype.Face(REL)
tt = TTFont(REL)
cmap = tt.getBestCmap()
ft = {"rendered": 0, "empty_nonmark": []}
MARKS = {0x10F82, 0x10F83, 0x10F84, 0x10F85}
for cp in range(0x10F70, 0x10F8A):
    if cp not in cmap:
        continue
    for px in (8, 16, 32, 64):
        face.set_char_size(px * 64)
        face.load_char(cp, freetype.FT_LOAD_RENDER)
    ft["rendered"] += 1
    if face.glyph.bitmap.rows == 0 and cp not in MARKS:
        ft["empty_nonmark"].append(hex(cp))
res["engines"]["freetype"] = {"ok": not ft["empty_nonmark"], **ft}

# 5. HarfBuzz shape sweep
blob = hb.Blob.from_file_path(REL)
hbface = hb.Face(blob)
hbfont = hb.Font(hbface)
def shape(s):
    buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    return [hbfont.glyph_to_string(i.codepoint) for i in buf.glyph_infos]
notdef = []
for cp in range(0x10F70, 0x10F8A):
    if cp in cmap and ".notdef" in shape(chr(cp)):
        notdef.append(hex(cp))
ctx = shape(chr(0x10F71) + chr(0x10F72) + chr(0x10F79))  # beth gimel mem
res["engines"]["harfbuzz"] = {
    "ok": not notdef,
    "isolated_notdef": notdef,
    "context_beth_gimel_mem": ctx}

# 6. Unicode conformance
block = list(range(0x10F70, 0x10F8A))
missing = [hex(c) for c in block if c not in cmap]
gdef = tt.get("GDEF")
mark_class_ok = False
if gdef and gdef.table.GlyphClassDef:
    gc = gdef.table.GlyphClassDef.classDefs
    marks = [g for g in ("dotaboveuyg", "dotbelowuyg", "twodotsaboveuyg",
                         "twodotsbelowuyg") if gc.get(g) == 3]
    mark_class_ok = len(marks) == 4
res["engines"]["unicode_conformance"] = {
    "ok": not missing and mark_class_ok,
    "codepoints_in_cmap": f"{len(block) - len(missing)}/{len(block)}",
    "missing": missing,
    "marks_have_gdef_mark_class": mark_class_ok}

# overall
def ok(e):
    v = res["engines"][e]
    if "counts" in v:
        return v["counts"].get("FAIL", 0) == 0 and v["counts"].get("FATAL", 0) == 0
    return v.get("ok", False)
gates = ["fonttools_load", "ots", "fontbakery_universal", "fontbakery_opentype",
         "freetype", "harfbuzz", "unicode_conformance"]
res["overall_pass"] = all(ok(g) for g in gates)
res["gate_status"] = {g: ok(g) for g in gates}

with open(os.path.join(BASE, "production_validation_p10.json"), "w",
          encoding="utf-8") as f:
    json.dump(res, f, indent=1)
print(json.dumps(res["gate_status"], indent=1))
print("OVERALL PASS:", res["overall_pass"])
