"""Phase 5.6: apply human validation decisions to the Phase 5 mapping.

Input : mapping_decisions.json  (exported from review_mapping.html, or a
        hand-edited decisions_template.json - both shapes accepted)
        mapping_table.json
Output: mapping_table_validated.json   the single source of truth onward
        validation_report.txt          totals + Unicode/glyph coverage
        final_mapping.json / final_mapping.csv
        mapping_changes.log            machine verdict -> human decision

Decision vocabulary (from the review UI)
  accept            confirm the machine's #1 candidate      -> confirmed
  candidate:<g>     pick another of the machine's top-5     -> corrected
  glyph:<g>         assign any font glyph                   -> corrected
  ambiguous         correct shape, keep whole group         -> confirmed_ambiguous
  unmapped          no font glyph corresponds               -> human_unmapped
  junk              scan noise, exclude entirely            -> junk
  (none)                                                    -> pending

Human choices are preserved exactly; automatic scores are never allowed to
override them.  Nothing here modifies the font.
"""
import csv
import json
import os
import sys

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
DEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "mapping_decisions.json")

mapping = json.load(open(os.path.join(BASE, "mapping_table.json"), encoding="utf-8"))
raw = json.load(open(DEC, encoding="utf-8"))
decisions = raw.get("decisions", raw)          # template or browser export
ginfo = mapping["glyph_info"]

validated = {}
counts = {"confirmed": 0, "corrected": 0, "confirmed_ambiguous": 0,
          "human_unmapped": 0, "junk": 0, "pending": 0}
log = []
for cname, r in mapping["mappings"].items():
    d = decisions.get(cname) or {}
    dec = (d.get("decision") or "").strip()
    notes = d.get("notes", "")
    out = dict(r)
    out["human_notes"] = notes
    out["human_decision"] = dec or None
    if dec == "accept":
        status, final = "confirmed", r["best_glyph"]
    elif dec.startswith(("candidate:", "glyph:")):
        g = dec.split(":", 1)[1]
        if g not in ginfo:
            print(f"WARNING {cname}: unknown glyph '{g}' -> pending")
            status, final = "pending", None
        else:
            status, final = "corrected", g
    elif dec == "ambiguous":
        status, final = "confirmed_ambiguous", None
        out["final_group"] = r.get("ambiguity_group") or [r["best_glyph"]]
    elif dec == "unmapped":
        status, final = "human_unmapped", None
    elif dec == "junk":
        status, final = "junk", None
    else:
        status, final = "pending", None
    out["validation"] = status
    out["final_glyph"] = final
    if final:
        gi = ginfo[final]
        out["final_codepoint"] = gi["codepoint"]
        out["final_unicode_name"] = gi["unicode_name"]
        out["final_form"] = gi["form"]
    counts[status] += 1
    validated[cname] = out
    log.append(f"{cname}: machine={r['verdict']} (best={r['best_glyph']}, "
               f"conf={r['confidence']}) -> human={status}"
               + (f" [{final}]" if final else "")
               + (f"  // {notes}" if notes else ""))

# ---- coverage ----
assigned = {}
for cname, v in validated.items():
    if v.get("final_glyph"):
        assigned.setdefault(v["final_glyph"], []).append(cname)
amb_groups = {cname: v["final_group"] for cname, v in validated.items()
              if v["validation"] == "confirmed_ambiguous"}
dups = {g: c for g, c in assigned.items() if len(c) > 1}

# Unicode coverage over the 26 Old Uyghur codepoints
def cps_of(gname):
    gi = ginfo[gname]
    out = set()
    for b in gi["letters"]:
        for src in (gname, b):
            if src in ginfo and ginfo[src]["codepoint"]:
                out.add(ginfo[src]["codepoint"])
                break
    return out

direct_cps = set()
for g in assigned:
    direct_cps |= cps_of(g)
amb_cps = set()
for grp in amb_groups.values():
    for g in grp:
        amb_cps |= cps_of(g)
amb_cps -= direct_cps
ALL_CPS = {f"U+{cp:04X}" for cp in range(0x10F70, 0x10F8A)}
missing_cps = sorted(ALL_CPS - direct_cps - amb_cps)

core = [g for g in ginfo if ginfo[g]["category"] in ("letter", "mark", "punctuation")]
amb_glyphs = {g for grp in amb_groups.values() for g in grp}
missing_glyphs = sorted(g for g in core if g not in assigned and g not in amb_glyphs)

meta = {"decisions_file": os.path.basename(DEC), "counts": counts,
        "duplicate_final_assignments": dups,
        "unicode_coverage": {
            "direct": sorted(c for c in direct_cps if c in ALL_CPS),
            "via_ambiguous_group_only": sorted(c for c in amb_cps if c in ALL_CPS),
            "missing": missing_cps},
        "glyph_coverage": {
            "with_validated_source": sorted(assigned),
            "in_ambiguous_groups": sorted(amb_glyphs),
            "missing_letter_mark_punct": missing_glyphs},
        "note": "single source of truth for subsequent phases; font unmodified"}
with open(os.path.join(BASE, "mapping_table_validated.json"), "w",
          encoding="utf-8") as f:
    json.dump({"meta": meta, "glyph_info": ginfo, "mappings": validated},
              f, indent=1)

# final_mapping: only clusters that ended with a glyph or a group
final_map = {c: {k: v.get(k) for k in
                 ("cluster_size", "cluster_type", "representative",
                  "validation", "final_glyph", "final_codepoint",
                  "final_unicode_name", "final_form", "final_group",
                  "human_notes")}
             for c, v in validated.items()
             if v["validation"] in ("confirmed", "corrected",
                                    "confirmed_ambiguous")}
with open(os.path.join(BASE, "final_mapping.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {"source": "mapping_table_validated.json"},
               "mappings": final_map}, f, indent=1)
with open(os.path.join(BASE, "final_mapping.csv"), "w", newline="",
          encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["cluster", "size", "type", "validation", "final_glyph",
                 "codepoint", "unicode_name", "contextual_form",
                 "ambiguity_group", "notes"])
    for c, v in final_map.items():
        wr.writerow([c, v["cluster_size"], v["cluster_type"], v["validation"],
                     v["final_glyph"] or "", v["final_codepoint"] or "",
                     v["final_unicode_name"] or "", v["final_form"] or "",
                     ";".join(v.get("final_group") or []), v["human_notes"]])
with open(os.path.join(BASE, "mapping_changes.log"), "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n")

with open(os.path.join(BASE, "validation_report.txt"), "w", encoding="utf-8") as f:
    f.write("Phase 5.6 - human validation applied\n\n")
    f.write("CLUSTER TOTALS\n")
    for k, v in counts.items():
        f.write(f"  {k:20} {v}\n")
    seg = {k: sum(r["cluster_size"] for r in validated.values()
                  if r["validation"] == k) for k in counts}
    f.write("\nSEGMENT TOTALS (members)\n")
    for k, v in seg.items():
        f.write(f"  {k:20} {v}\n")
    f.write("\nUNICODE COVERAGE (26 Old Uyghur codepoints)\n")
    f.write(f"  direct: {len(meta['unicode_coverage']['direct'])} "
            f"{meta['unicode_coverage']['direct']}\n")
    f.write(f"  via ambiguous group only: "
            f"{len(meta['unicode_coverage']['via_ambiguous_group_only'])} "
            f"{meta['unicode_coverage']['via_ambiguous_group_only']}\n")
    f.write(f"  missing: {len(missing_cps)} {missing_cps}\n")
    f.write("\nGLYPH COVERAGE\n")
    f.write(f"  validated source: {len(assigned)} glyphs: {sorted(assigned)}\n")
    f.write(f"  in confirmed-ambiguous groups: {len(amb_glyphs)}\n")
    f.write(f"  letter/mark/punct glyphs with NO source: {len(missing_glyphs)}\n")
    for g in missing_glyphs:
        f.write(f"    {g}\n")
    if dups:
        f.write("\nDUPLICATE FINAL ASSIGNMENTS\n")
        for g, cs in dups.items():
            f.write(f"  {g}: {', '.join(cs)}\n")
    f.write("\nCHANGES\n  " + "\n  ".join(log) + "\n")

print(json.dumps(counts))
print(f"unicode: {len(meta['unicode_coverage']['direct'])} direct, "
      f"{len(meta['unicode_coverage']['via_ambiguous_group_only'])} ambiguous-only, "
      f"{len(missing_cps)} missing | glyphs assigned: {len(assigned)} "
      f"(+{len(amb_glyphs)} ambiguous) | missing glyphs: {len(missing_glyphs)}")
print("-> mapping_table_validated.json, validation_report.txt, "
      "final_mapping.json/.csv, mapping_changes.log")
