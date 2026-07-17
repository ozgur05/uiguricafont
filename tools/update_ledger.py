"""Refresh the codepoint ledger after Phases 7.2-7.4.

Combines: outline_report.json (Phase 6 masters), outline_report_74.json
(harvest masters), ambiguity_resolution.json (7.3 logic pass).
Output: coverage_ledger.json / .txt - state of all 26 codepoints.
"""
import json
import os

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
o6 = json.load(open(os.path.join(BASE, "outline_report.json"), encoding="utf-8"))["outlines"]
o74 = json.load(open(os.path.join(BASE, "outline_report_74.json"), encoding="utf-8"))["outlines"]
amb = json.load(open(os.path.join(BASE, "ambiguity_resolution.json"), encoding="utf-8"))["clusters"]
ginfo = validated["glyph_info"]

NAMES = {0x10F70: "ALEPH", 0x10F71: "BETH", 0x10F72: "GIMEL-HETH",
         0x10F73: "WAW", 0x10F74: "ZAYIN", 0x10F75: "FINAL HETH",
         0x10F76: "YODH", 0x10F77: "KAPH", 0x10F78: "LAMEDH",
         0x10F79: "MEM", 0x10F7A: "NUN", 0x10F7B: "SAMEKH", 0x10F7C: "PE",
         0x10F7D: "SADHE", 0x10F7E: "RESH", 0x10F7F: "SHIN", 0x10F80: "TAW",
         0x10F81: "LESH", 0x10F82: "DOT ABOVE", 0x10F83: "DOT BELOW",
         0x10F84: "TWO DOTS ABOVE", 0x10F85: "TWO DOTS BELOW",
         0x10F86: "BAR", 0x10F87: "TWO BARS", 0x10F88: "TWO DOTS",
         0x10F89: "FOUR DOTS"}

masters = {}  # glyph -> (status, source, quality)


def offer(glyph, status, source, quality):
    prev = masters.get(glyph)
    if prev is None or (prev[0] == "draft" and status == "production") \
       or (prev[0] == status and quality > prev[2]):
        masters[glyph] = (status, source, quality)


for o in o6:
    if o["glyph_name"]:
        offer(o["glyph_name"],
              "production" if o["source_image_count"] >= 3 else "draft",
              "phase6", o["outline_quality_score"])
for o in o74:
    offer(o["glyph"], o["status"], "phase7.4", o["outline_quality_score"])

# ambiguity outcomes per codepoint
amb_hits = {}
for cname, r in amb.items():
    if r["status"] == "resolved":
        g = r["proposed_glyph"]
        amb_hits.setdefault(ginfo[g]["codepoint"], []).append(
            f"{cname} resolved -> {g}")
    else:
        for s in r["survivors"]:
            amb_hits.setdefault(s["codepoint"], []).append(
                f"{cname} shortlist ({r['status']})")

rows = []
for cp, nm in NAMES.items():
    cps = f"U+{cp:04X}"
    forms = {g: st for g, st in masters.items()
             if ginfo.get(g, {}).get("codepoint") == cps}
    prod = [g for g, st in forms.items() if st[0] == "production"]
    draft = [g for g, st in forms.items() if st[0] == "draft"]
    if prod:
        state = "covered"
    elif draft:
        state = "draft-only"
    elif cps in amb_hits:
        state = "ambiguous-pending"
    else:
        state = "missing"
    rows.append({"codepoint": cps, "name": nm, "state": state,
                 "production_forms": sorted(prod),
                 "draft_forms": sorted(draft),
                 "ambiguity_evidence": amb_hits.get(cps, [])})

counts = {}
for r in rows:
    counts[r["state"]] = counts.get(r["state"], 0) + 1
with open(os.path.join(BASE, "coverage_ledger.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": counts, "codepoints": rows}, f, indent=1)
with open(os.path.join(BASE, "coverage_ledger.txt"), "w", encoding="utf-8") as f:
    f.write(f"Coverage ledger after 7.2-7.4: {counts}\n\n")
    for r in rows:
        f.write(f"{r['codepoint']} {r['name']:16} {r['state']:18} "
                f"prod={len(r['production_forms'])} draft={len(r['draft_forms'])}"
                + (f"  {r['ambiguity_evidence'][0]}" if r["ambiguity_evidence"] else "")
                + "\n")
print(json.dumps(counts))
for r in rows:
    print(f" {r['codepoint']} {r['name']:16} {r['state']:18} "
          f"prod={r['production_forms']}")
