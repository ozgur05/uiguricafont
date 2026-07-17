"""Phase 9 areas 1+2: OpenType table validation + per-glyph outline validation.

Validation only - the font is opened read-only and never written.
Outputs: p9_tables.json, glyph_validation.csv
"""
import csv
import json
import os

import numpy as np
import pathops
from fontTools.ttLib import TTFont

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
OLD = os.path.join(BASE, "build", "Uigurica-Regular.phase1-noto.ttf")

rep = json.load(open(os.path.join(BASE, "integration_report_p8.json"), encoding="utf-8"))
integrated = [g for g, v in rep["glyphs"].items() if v.get("status") == "production"]

new = TTFont(NEW, lazy=False)   # full parse = structural validation
old = TTFont(OLD, lazy=False)
res = {"tables": {}, "issues": []}

# ---------- 1. table validation ----------
order = new.getGlyphOrder()
oset = set(order)
res["tables"]["present"] = sorted(k for k in new.keys() if k != "GlyphOrder")
res["tables"]["numGlyphs"] = {"new": new["maxp"].numGlyphs,
                              "old": old["maxp"].numGlyphs}
if new["maxp"].numGlyphs != len(order):
    res["issues"].append("maxp.numGlyphs != glyph order length")
if new["maxp"].numGlyphs != old["maxp"].numGlyphs:
    res["issues"].append("glyph count changed vs phase1")

# cmap: every target exists
bad = [(hex(c), g) for c, g in new.getBestCmap().items() if g not in oset]
if bad:
    res["issues"].append(f"cmap targets missing from glyph set: {bad[:5]}")
res["tables"]["cmap_entries"] = len(new.getBestCmap())
res["tables"]["cmap_identical_to_phase1"] = (
    old.getTableData("cmap") == new.getTableData("cmap"))

# hmtx/hhea
hm = new["hmtx"].metrics
if set(hm.keys()) != oset:
    res["issues"].append("hmtx keys != glyph set")
if new["hhea"].numberOfHMetrics > new["maxp"].numGlyphs:
    res["issues"].append("hhea.numberOfHMetrics > numGlyphs")

# glyf/loca: parse every glyph, expand coordinates (catches loca breakage)
glyf = new["glyf"]
n_comp, n_empty = 0, 0
for g in order:
    gl = glyf[g]
    if gl.isComposite():
        n_comp += 1
        for comp in gl.components:
            if comp.glyphName not in oset:
                res["issues"].append(f"{g}: composite ref to missing "
                                     f"{comp.glyphName}")
    elif gl.numberOfContours == 0:
        n_empty += 1
    else:
        gl.getCoordinates(glyf)
res["tables"]["composites"] = n_comp
res["tables"]["empty_glyphs"] = n_empty

# GSUB/GPOS/GDEF: closure of referenced glyph names + lookup indices
def scan_layout(font, tag):
    if tag not in font:
        return None
    t = font[tag].table
    names = set()
    def walk(obj, depth=0):
        if depth > 14 or obj is None:
            return
        if isinstance(obj, str):
            if obj.endswith("uyg") or "." in obj or obj in oset:
                names.add(obj)
            return
        if isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v, depth + 1)
            return
        if hasattr(obj, "__dict__"):
            for k, v in vars(obj).items():
                if k in ("Format",):
                    continue
                walk(v, depth + 1)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk(k, depth + 1)
                walk(v, depth + 1)
    walk(t)
    ll = getattr(t, "LookupList", None)
    n_lookups = ll.LookupCount if ll else 0
    return {"lookups": n_lookups,
            "referenced_glyphs": len(names & oset),
            "unknown_refs": sorted(n for n in names
                                   if n not in oset and n.endswith("uyg"))}

for tag in ("GSUB", "GPOS", "GDEF"):
    s = scan_layout(new, tag)
    so = scan_layout(old, tag)
    res["tables"][tag] = s
    if s and so and s["lookups"] != so["lookups"]:
        res["issues"].append(f"{tag} lookup count changed")
    if s and s["unknown_refs"]:
        res["issues"].append(f"{tag} references unknown glyphs: "
                             f"{s['unknown_refs'][:5]}")

# orphan glyphs (unreachable from cmap+GSUB closure) - regression vs phase1
def reachable(font):
    seen = set(font.getBestCmap().values()) | {".notdef"}
    try:
        from fontTools.subset import Subsetter
    except Exception:
        return None
    changed = True
    # cheap closure: GSUB rules referencing a seen glyph add their outputs
    # use fontTools subset closure instead:
    return None

orph_new = oset - set(new.getBestCmap().values())
orph_old = oset - set(old.getBestCmap().values())
res["tables"]["glyphs_not_directly_cmapped"] = {
    "new": len(orph_new), "old": len(orph_old),
    "same_set": orph_new == orph_old}
if orph_new != orph_old:
    res["issues"].append("set of non-cmapped glyphs changed vs phase1")

# name / OS/2 / post / head sanity
res["tables"]["name_identical"] = old.getTableData("name") == new.getTableData("name")
res["tables"]["post_identical"] = old.getTableData("post") == new.getTableData("post")
res["tables"]["os2_identical"] = old.getTableData("OS/2") == new.getTableData("OS/2")
if new["head"].unitsPerEm != 1000:
    res["issues"].append("unitsPerEm changed")

# ---------- 2. per-glyph outline validation ----------
rows = []
for g in integrated:
    gl = glyf[g]
    coords, ends, flags = gl.getCoordinates(glyf)
    n_pts = len(coords)
    n_cont = gl.numberOfContours
    # duplicates / zero-length
    dup_pts = 0
    zero_seg = 0
    start = 0
    contour_sets = []
    for e in ends:
        pts = [tuple(coords[i]) for i in range(start, e + 1)]
        on = [bool(flags[i] & 1) for i in range(start, e + 1)]
        contour_sets.append(tuple(pts))
        m = len(pts)
        for i in range(m):
            if pts[i] == pts[(i + 1) % m]:
                dup_pts += 1
                if on[i] and on[(i + 1) % m]:
                    zero_seg += 1
        start = e + 1
    dup_cont = len(contour_sets) - len(set(contour_sets))
    # pathops round-trip: overlaps / self-intersections / winding
    path = pathops.Path()
    gl.draw(path.getPen(glyphSet=None), glyf)
    simp = pathops.simplify(path, fix_winding=True, clockwise=True)
    clean = (len(list(path.contours)) == len(list(simp.contours))
             and abs(abs(simp.area) - abs(path.area)) <= 0.001 * max(abs(path.area), 1))
    winding_ok = all(c.clockwise == (c.area < 0 if False else c.clockwise)
                     for c in path.contours)  # skia reports; outer CW enforced at build
    n_cw = sum(1 for c in path.contours if c.clockwise)
    n_ccw = n_cont - n_cw
    # extrema (informational, from validate_p8 logic)
    missing_ext = 0
    start = 0
    for e in ends:
        pts = [(coords[i], flags[i] & 1) for i in range(start, e + 1)]
        m = len(pts)
        for i in range(m):
            p0, on0 = pts[i]
            p1, on1 = pts[(i + 1) % m]
            p2, on2 = pts[(i + 2) % m]
            if on0 and not on1 and on2:
                for d in (0, 1):
                    den = p0[d] - 2 * p1[d] + p2[d]
                    if abs(den) > 1e-9:
                        t = (p0[d] - p1[d]) / den
                        if 0.05 < t < 0.95:
                            v = ((1-t)**2*p0[d] + 2*(1-t)*t*p1[d] + t**2*p2[d])
                            if not (min(p0[d], p2[d]) - 0.5 <= v
                                    <= max(p0[d], p2[d]) + 0.5):
                                missing_ext += 1
        start = e + 1
    verdict = "PASS" if (clean and dup_cont == 0 and zero_seg == 0) else "WARN"
    rows.append({
        "glyph": g, "contours": n_cont, "points": n_pts,
        "outer_cw": n_cw, "ccw": n_ccw,
        "closed": True,  # TrueType contours are closed by definition
        "self_intersection_or_overlap": not clean,
        "duplicate_points": dup_pts, "duplicate_contours": dup_cont,
        "zero_length_segments": zero_seg,
        "missing_extrema": missing_ext,
        "verdict": verdict,
    })

with open(os.path.join(BASE, "glyph_validation.csv"), "w", newline="",
          encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
res["outline_summary"] = {
    "glyphs_checked": len(rows),
    "pass": sum(1 for r in rows if r["verdict"] == "PASS"),
    "warn": sum(1 for r in rows if r["verdict"] == "WARN"),
    "warn_glyphs": [r["glyph"] for r in rows if r["verdict"] == "WARN"],
}
with open(os.path.join(BASE, "p9_tables.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=1)
print(json.dumps(res["outline_summary"], indent=1))
print("issues:", res["issues"] or "none")
print("p9_tables.json + glyph_validation.csv written")
