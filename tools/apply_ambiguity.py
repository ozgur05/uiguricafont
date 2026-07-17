"""Apply ambiguity decisions to mapping_table_validated.json.

Usage: python tools/apply_ambiguity.py [decisions.json]
       (default: ambiguity_decisions.json)

For each decided cluster: validation confirmed_ambiguous -> corrected,
final_glyph set, final_group dropped (kept as resolution provenance).
Escape values: __unmapped__ -> human_unmapped, __junk__ -> junk,
__defer__ -> left as confirmed_ambiguous.
Re-decisions are honored: clusters previously corrected BY AN AMBIGUITY
ROUND (human_decision starts with "ambiguity:") may be revised; clusters
corrected in Phase 5.6 are never touched.
"""
import json
import os
import sys

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
vpath = os.path.join(BASE, "mapping_table_validated.json")
data = json.load(open(vpath, encoding="utf-8"))
dpath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "ambiguity_decisions.json")
dec = json.load(open(dpath, encoding="utf-8"))
ginfo = data["glyph_info"]

applied = []
for cname, d in dec.items():
    g = d.get("glyph")
    v = data["mappings"].get(cname)
    if not v or not g:
        continue
    revisable = (v["validation"] == "confirmed_ambiguous" or
                 (v.get("human_decision") or "").startswith("ambiguity:"))
    if not revisable:
        continue
    if v.get("human_decision") == f"ambiguity:{g}":
        continue  # unchanged re-submission
    if g == "__defer__":
        continue
    if g in ("__unmapped__", "__junk__"):
        v["validation"] = "human_unmapped" if g == "__unmapped__" else "junk"
        v["final_glyph"] = None
        v["human_decision"] = f"ambiguity:{g}"
    else:
        if g not in ginfo:
            print(f"WARNING {cname}: unknown glyph {g}")
            continue
        v["validation"] = "corrected"
        v["final_glyph"] = g
        v["final_codepoint"] = ginfo[g]["codepoint"]
        v["final_unicode_name"] = ginfo[g]["unicode_name"]
        v["final_form"] = ginfo[g]["form"]
        v["ambiguity_resolved_from"] = v.pop("final_group", None)
        v["human_decision"] = f"ambiguity:{g}"
    if d.get("notes"):
        v["human_notes"] = (v.get("human_notes") or "") + " | " + d["notes"]
    applied.append((cname, g))

json.dump(data, open(vpath, "w", encoding="utf-8"), indent=1)
for c, g in applied:
    print(f"applied {c} -> {g}")
print(f"{len(applied)} decisions applied; "
      f"remaining confirmed_ambiguous: "
      f"{sum(1 for v in data['mappings'].values() if v['validation'] == 'confirmed_ambiguous')}")
