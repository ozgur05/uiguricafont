"""Phase 7.3: resolve confirmed_ambiguous clusters by word context.

Evidence used (facts first, judgment last):
  1. POSITION: every decomposed piece knows where it sat in its parent word
     (RTL: rightmost = initial, leftmost = final, interior = medial,
     unsplit = isolated).  A candidate glyph whose contextual form is
     incompatible with where the members actually occur is ELIMINATED.
     support(g) = fraction of members whose position matches g's form.
  2. JOINING MODEL (L2/20-191): right-joining letters (ZAYIN, FINAL HETH)
     cannot supply initial/medial identities; their isolated forms cannot
     appear where members demonstrably join on both sides.
  3. VISUAL RANK: among survivors, Phase 5 adjusted similarity (recorded in
     mapping_table.json top_candidates) orders the shortlist; it never
     eliminates on its own (Noto closeness is not a gate).

Statuses
  resolved   exactly one survivor        -> proposed final_glyph
  narrowed   fewer survivors than group  -> shortlist for human
  unchanged  no eliminations possible

Output: ambiguity_resolution.json, ambiguity_review.html (radio sheet,
exports ambiguity_decisions.json), applied later by apply_ambiguity.py.
Read-only otherwise; font untouched.
"""
import base64
import io
import json
import os

from PIL import Image

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
SUPPORT_MIN = 0.25

validated = json.load(open(os.path.join(BASE, "mapping_table_validated.json"), encoding="utf-8"))
machine = json.load(open(os.path.join(BASE, "mapping_table.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
ginfo = validated["glyph_info"]

piece_meta = {p["filename"]: p for p in decomp["pieces"]}
RIGHT_JOINING = {"zayinuyg", "finalHethuyg"}


def position_of(fn):
    p = piece_meta.get(fn)
    if not p:
        return "isolated"
    n, i = p["n_pieces_in_parent"], p["piece_index"]
    return ("isolated" if n == 1 else "initial" if i == n - 1
            else "final" if i == 0 else "medial")


FORM_OK = {"initial": {"initial"}, "medial": {"medial"},
           "final": {"final", "final-variant"}, "isolated": {"isolated"}}

ambiguous = {c: v for c, v in validated["mappings"].items()
             if v["validation"] == "confirmed_ambiguous"}
print(f"{len(ambiguous)} confirmed_ambiguous clusters")

results = {}
for cname, v in sorted(ambiguous.items()):
    c = upd["clusters"][cname]
    members = c["members"]
    N = len(members)
    pos_count = {}
    for m in members:
        p = position_of(m)
        pos_count[p] = pos_count.get(p, 0) + 1
    pos_frac = {k: n / N for k, n in pos_count.items()}

    sim = {t["glyph"]: t["adjusted"]
           for t in machine["mappings"][cname]["top_candidates"]}
    group = v.get("final_group") or []
    survivors, eliminated = [], []
    for g in group:
        gi = ginfo[g]
        form = gi["form"]
        base = gi["letters"][0]
        support = sum(pos_frac.get(p, 0.0) for p, forms in
                      [(p, FORM_OK.get(p, set())) for p in pos_frac]
                      if form in FORM_OK.get(p, set()) or
                      (p in FORM_OK and form in FORM_OK[p]))
        # simpler: support = fraction of members at positions matching form
        support = sum(f for p, f in pos_frac.items()
                      if form in FORM_OK.get(p, {p}))
        reasons = []
        if base in RIGHT_JOINING and form in ("initial", "medial"):
            reasons.append("right-joining letter cannot be initial/medial")
        if support < SUPPORT_MIN:
            dom = max(pos_frac, key=pos_frac.get)
            reasons.append(f"form '{form}' matches only {support:.0%} of member "
                           f"positions (members are {dom} in {pos_frac[dom]:.0%})")
        entry = {"glyph": g, "form": form, "codepoint": gi["codepoint"],
                 "position_support": round(support, 3),
                 "visual_rank_adjusted": sim.get(g)}
        if reasons:
            entry["eliminated_because"] = reasons
            eliminated.append(entry)
        else:
            survivors.append(entry)
    survivors.sort(key=lambda e: (-(e["visual_rank_adjusted"] or 0),
                                  -e["position_support"]))
    status = ("resolved" if len(survivors) == 1 else
              "narrowed" if len(survivors) < len(group) else "unchanged")
    results[cname] = {
        "cluster_size": N,
        "position_distribution": {k: round(f, 3) for k, f in pos_frac.items()},
        "original_group": group,
        "survivors": survivors,
        "eliminated": eliminated,
        "status": status,
        "proposed_glyph": survivors[0]["glyph"] if status == "resolved" else None,
        "note": ("single survivor by position+joining logic; visual rank not "
                 "needed" if status == "resolved" else
                 "human pick required among survivors" if survivors else
                 "ALL candidates eliminated - group or positions inconsistent, "
                 "needs re-examination"),
    }
    print(f"{cname}: {len(group)} -> {len(survivors)} [{status}]"
          + (f" = {results[cname]['proposed_glyph']}" if status == "resolved" else ""))

n_res = sum(1 for r in results.values() if r["status"] == "resolved")
n_nar = sum(1 for r in results.values() if r["status"] == "narrowed")
with open(os.path.join(BASE, "ambiguity_resolution.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": {
        "method": "position-form compatibility + L2/20-191 joining model; "
                  "visual similarity orders but never eliminates",
        "support_min": SUPPORT_MIN,
        "resolved": n_res, "narrowed": n_nar,
        "unchanged": len(results) - n_res - n_nar},
        "clusters": results}, f, indent=1)


# ---------------- review sheet ----------------
# Every card gets a COMPLETE control set regardless of resolver outcome:
#   - all survivors as radios (normal)
#   - all eliminated candidates as radios too, marked "override" (the
#     resolver's position logic can be wrong for mis-cut pieces; a human
#     must be able to overrule it)
#   - always-present escape options: none-of-these(unmapped) / junk / defer
# Prefills any decisions already present in ambiguity_decisions.json.
prior = {}
prior_path = os.path.join(BASE, "ambiguity_decisions.json")
if os.path.exists(prior_path):
    prior = json.load(open(prior_path, encoding="utf-8"))


def b64_file(path, size=110):
    im = Image.open(path)
    if im.mode == "RGBA":
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg.convert("L")
    else:
        im = im.convert("L")
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


cards = []
for cname, r in results.items():
    c = upd["clusters"][cname]
    rep = c["representative"]
    if c["representative_dir"] == "decomposed_segments":
        rp = os.path.join(BASE, "decomposed_normalized", "128",
                          rep.replace("sub", "dnorm"))
    else:
        rp = os.path.join(BASE, "normalized", "128", rep.replace("glyph", "norm"))
    pre = prior.get(cname, {}).get("glyph")

    def radio(glyph, checked):
        return (f'<input type="radio" name="{cname}" value="{glyph}"'
                + (" checked" if checked else "") + ">")

    srow = ""
    for s in r["survivors"]:
        srow += (f'<label class="cd"><img src="'
                 f'{b64_file(os.path.join(BASE, "font_glyphs", s["glyph"] + ".png"))}">'
                 f'<div>{s["glyph"]}<br>{s["codepoint"] or ""} '
                 f'sup={s["position_support"]}</div>'
                 f'{radio(s["glyph"], pre == s["glyph"])}</label>')
    # eliminated candidates remain selectable as explicit overrides
    for e in r["eliminated"]:
        srow += (f'<label class="cd ovr"><img src="'
                 f'{b64_file(os.path.join(BASE, "font_glyphs", e["glyph"] + ".png"))}">'
                 f'<div>{e["glyph"]}<br>{e["codepoint"] or ""}</div>'
                 f'<div class="why">{"; ".join(e["eliminated_because"])}</div>'
                 f'{radio(e["glyph"], pre == e["glyph"])} override</label>')
    # escape options - present on EVERY card
    esc = (f'<label class="esc">{radio("__unmapped__", pre == "__unmapped__")}'
           ' none of these</label>'
           f'<label class="esc">{radio("__junk__", pre == "__junk__")}'
           ' junk cluster</label>'
           f'<label class="esc">{radio("__defer__", pre == "__defer__")}'
           ' defer</label>')
    auto = (f'<div class="auto">auto-resolved: {r["proposed_glyph"]}</div>'
            if r["status"] == "resolved" else "")
    cards.append(
        f'<div class="card"><h3>{cname} <small>n={r["cluster_size"]} '
        f'status={r["status"]} positions={r["position_distribution"]}</small></h3>'
        f'{auto}<div class="row"><div><img src="{b64_file(rp, 140)}">'
        f'<div class="lb">cluster medoid</div></div>'
        f'<div class="cands">{srow}</div></div>'
        f'<div class="escrow">{esc}</div>'
        f'<label>notes <input type="text" name="n_{cname}" size="50"></label></div>')

html = ("""<!doctype html><html><head><meta charset="utf-8"><title>Uigurica ambiguity resolution</title>
<style>body{font-family:sans-serif;margin:16px}.card{border:1px solid #ccc;border-radius:8px;margin:12px 0;padding:8px 12px}
.row{display:flex;gap:16px;align-items:flex-start}.cands{display:flex;flex-wrap:wrap;gap:8px}
.cd{text-align:center;font-size:11px;border:1px solid #eee;padding:4px}.cd img{display:block;margin:0 auto}
.lb{font-size:11px;color:#777;text-align:center}
.ovr{background:#fff5f5;border-color:#e0b4b4}.why{max-width:130px;color:#b00;font-size:10px}
.escrow{margin-top:8px;font-size:13px}.esc{margin-right:16px}
.auto{color:#27823b;font-weight:bold;font-size:13px}
#bar{position:sticky;top:0;background:#2c3e50;color:#fff;padding:8px 12px;border-radius:6px}</style></head><body>
<div id="bar"><b>Phase 7.3 ambiguity review</b> - pick the correct identity among survivors
(hover red chips to see why others were eliminated) <button onclick="ex()">Export ambiguity_decisions.json</button></div>"""
        + "".join(cards) + """
<script>function ex(){const out={};document.querySelectorAll('input[type=radio]:checked').forEach(i=>{
out[i.name]={glyph:i.value};});document.querySelectorAll('input[type=text]').forEach(t=>{
const c=t.name.slice(2);if(t.value){(out[c]=out[c]||{}).notes=t.value;}});
const b=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='ambiguity_decisions.json';a.click();}
</script></body></html>""")
with open(os.path.join(BASE, "ambiguity_review.html"), "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nresolved={n_res} narrowed={n_nar} "
      f"unchanged={len(results) - n_res - n_nar}")
print("-> ambiguity_resolution.json, ambiguity_review.html")
