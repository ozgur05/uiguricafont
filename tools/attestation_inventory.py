"""Phase 6.1/7.1: attestation inventory against phase_architecture.json.

Audits, for every eligible cluster and every Old Uyghur codepoint:
  - attestation count vs production_min/target
  - distinct source words / pages (diversity requirement)
  - right-joining compliance (ZAYIN, FINAL HETH: attestations must be
    word-final or isolated pieces)
  - draft flags for existing Phase 6 masters

Output: attestation_inventory.json, attestation_inventory.txt
Read-only: touches no masters, no font.
"""
import json
import os

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
arch = json.load(open(os.path.join(BASE, "phase_architecture.json"), encoding="utf-8"))
validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
outline = json.load(open(os.path.join(BASE, "outline_report.json"), encoding="utf-8"))

REQ = arch["attestation_requirements"]
PMIN, PTGT = REQ["production_min"], REQ["production_target"]
RIGHT_JOINING = {"zayinuyg", "finalHethuyg"}

piece_meta = {p["filename"]: p for p in decomp["pieces"]}
seg_page = {}
for p in decomp["pieces"]:
    seg_page[p["filename"]] = p["page"]


def position_of(fn):
    p = piece_meta.get(fn)
    if not p:
        return "whole-segment"
    n, i = p["n_pieces_in_parent"], p["piece_index"]
    return ("isolated" if n == 1 else "initial" if i == n - 1
            else "final" if i == 0 else "medial")


eligible = {c: v for c, v in validated["mappings"].items()
            if v["validation"] in ("corrected", "confirmed_ambiguous")}
outline_by_cluster = {o["cluster"]: o for o in outline["outlines"]}

inv = []
for cname, v in sorted(eligible.items()):
    c = upd["clusters"][cname]
    members = c["members"]
    parents = {piece_meta[m]["parent"] for m in members if m in piece_meta}
    pages = sorted({piece_meta[m]["page"] for m in members if m in piece_meta})
    positions = {}
    for m in members:
        pos = position_of(m)
        positions[pos] = positions.get(pos, 0) + 1
    gname = v.get("final_glyph")
    base = (gname or "").split(".")[0] if gname else None
    rj = base in RIGHT_JOINING
    rj_valid = None
    if rj:
        ok = positions.get("final", 0) + positions.get("isolated", 0) \
             + positions.get("whole-segment", 0)
        rj_valid = ok == len(members)
    n = len(members)
    status = ("production" if n >= PMIN and (not rj or rj_valid)
              else "draft")
    reasons = []
    if n < PMIN:
        reasons.append(f"only {n} attestation(s), need >= {PMIN}")
    if len(parents) < 2 and n >= 2:
        reasons.append("all attestations from a single word "
                       f"({next(iter(parents), '?')})")
    if rj and not rj_valid:
        bad = {k: x for k, x in positions.items()
               if k in ("initial", "medial")}
        reasons.append(f"right-joining letter with interior attestations: {bad}")
        status = "invalid-attestations"
    o = outline_by_cluster.get(cname, {})
    inv.append({
        "cluster": cname,
        "glyph": gname,
        "ambiguity_group": v.get("final_group"),
        "validation": v["validation"],
        "attestations": n,
        "distinct_parent_words": len(parents),
        "pages": pages,
        "position_distribution": positions,
        "right_joining": rj,
        "status": status,
        "meets_target": n >= PTGT,
        "reasons": reasons,
        "existing_master": o.get("files", {}).get("glif"),
        "master_quality": o.get("outline_quality_score"),
    })

n_prod = sum(1 for r in inv if r["status"] == "production")
n_draft = sum(1 for r in inv if r["status"] == "draft")
n_inval = sum(1 for r in inv if r["status"] == "invalid-attestations")

# codepoint ledger
gaps = arch["unicode_mapping_policy"]["coverage_gaps_from_phase_5_6"]
ledger = []
for cp in [f"U+{x:04X}" for x in range(0x10F70, 0x10F8A)]:
    if cp in gaps["direct"]:
        cls = [r for r in inv if r["glyph"] and
               validated["glyph_info"].get(r["glyph"], {}).get("codepoint") == cp]
        best = max(cls, key=lambda r: r["attestations"], default=None)
        ledger.append({"codepoint": cp, "state": "direct",
                       "best_cluster": best["cluster"] if best else None,
                       "best_status": best["status"] if best else None,
                       "action": (None if best and best["status"] == "production"
                                  else "harvest more attestations (7.2)")})
    elif cp in gaps["ambiguous_only"]:
        ledger.append({"codepoint": cp, "state": "ambiguous_only",
                       "action": "resolve group via word context (7.3)"})
    else:
        ledger.append({"codepoint": cp, "state": "missing",
                       "action": "targeted re-harvest from word clusters (7.2)"})

out = {"meta": {"requirements": REQ,
                "clusters": {"production": n_prod, "draft": n_draft,
                             "invalid": n_inval}},
       "clusters": inv, "codepoint_ledger": ledger}
with open(os.path.join(BASE, "attestation_inventory.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=1)

with open(os.path.join(BASE, "attestation_inventory.txt"), "w",
          encoding="utf-8") as f:
    f.write(f"Attestation inventory - production {n_prod}, draft {n_draft}, "
            f"invalid {n_inval}\n\n")
    f.write(f"{'cluster':13} {'glyph/group':28} {'n':>3} {'words':>5} "
            f"{'status':22} reasons\n")
    for r in inv:
        g = r["glyph"] or f"[group of {len(r['ambiguity_group'] or [])}]"
        f.write(f"{r['cluster']:13} {g:28} {r['attestations']:>3} "
                f"{r['distinct_parent_words']:>5} {r['status']:22} "
                f"{'; '.join(r['reasons'])}\n")
    f.write("\nCODEPOINT LEDGER\n")
    for e in ledger:
        f.write(f"  {e['codepoint']} {e['state']:15} "
                f"{e.get('action') or 'OK'}\n")

print(f"production={n_prod} draft={n_draft} invalid={n_inval}")
for r in inv:
    if r["status"] == "invalid-attestations":
        print("INVALID:", r["cluster"], r["glyph"], r["reasons"])
print("-> attestation_inventory.json / .txt")
