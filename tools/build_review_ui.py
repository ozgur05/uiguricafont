"""Phase 5.5a: build the human-validation UI for the Phase 5 mapping.

Input : mapping_table.json, updated_clusters.json, normalized/128,
        decomposed_normalized/128, font_glyphs/
Output: review_mapping.html   self-contained (images embedded base64):
          - one card per cluster, ordered review -> unmapped -> mapped
          - cluster medoid + up to 10 member thumbnails
          - top-5 font candidates with codepoint/form/similarity
          - decision controls: accept #1 / pick #2-5 / any glyph from a
            dropdown / correct-but-ambiguous / unmapped / junk + notes
          - autosaves to localStorage, Export button downloads
            mapping_decisions.json
        decisions_template.json  (same schema, for hand editing)

Phase 5.5b (tools/apply_validation.py) merges the exported decisions into
mapping_table_validated.json.  Nothing here modifies the font.
"""
import base64
import io
import json
import os

from PIL import Image

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
mapping = json.load(open(os.path.join(BASE, "mapping_table.json"), encoding="utf-8"))
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
ginfo = mapping["glyph_info"]


def b64(img, size):
    img = img.convert("L").resize((size, size))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def cluster_thumb(cname, fn, size=96):
    c = upd["clusters"][cname]
    if c["representative_dir"] == "decomposed_segments":
        p = os.path.join(BASE, "decomposed_normalized", "128",
                         fn.replace("sub", "dnorm"))
    else:
        p = os.path.join(BASE, "normalized", "128", fn.replace("glyph", "norm"))
    return b64(Image.open(p), size)


def glyph_thumb(gname, size=112):
    im = Image.open(os.path.join(BASE, "font_glyphs", gname + ".png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    # pad to square
    s = max(im.size)
    sq = Image.new("RGB", (s, s), "white")
    sq.paste(bg.convert("RGB"), ((s - im.width) // 2, (s - im.height) // 2))
    return b64(sq, size)


order = {"review": 0, "unmapped": 1, "unmapped (multi-letter word segment)": 1,
         "mapped": 2}
items = sorted(mapping["mappings"].items(),
               key=lambda kv: (order.get(kv[1]["verdict"], 1),
                               -kv[1]["cluster_size"]))

glyph_options = "".join(
    f'<option value="{g}">{g} {ginfo[g]["codepoint"] or ""} '
    f'({ginfo[g]["form"]})</option>'
    for g in sorted(ginfo))

cards = []
for cname, r in items:
    c = upd["clusters"][cname]
    members = c["members"]
    step = max(1, len(members) // 10)
    thumbs = "".join(
        f'<img src="{cluster_thumb(cname, fn)}" title="{fn}">'
        for fn in members[::step][:10])
    cands = ""
    for k, cand in enumerate(r["top_candidates"]):
        g = cand["glyph"]
        cands += (
            f'<div class="cand"><img src="{glyph_thumb(g)}">'
            f'<div class="cn">#{k + 1} {g}</div>'
            f'<div class="cm">{cand["codepoint"] or "&mdash;"} {cand["form"]}'
            f'<br>sim {cand["similarity"]:.3f}</div>'
            f'<label><input type="radio" name="d_{cname}" value="candidate:{g}">'
            f' use</label></div>')
    amb = (f'<div class="amb">ambiguity group: {", ".join(r["ambiguity_group"])}'
           '</div>' if r.get("ambiguity_group") else "")
    cards.append(f"""
<div class="card" id="{cname}" data-verdict="{r['verdict']}">
 <h3>{cname} <span class="tag {('t' + r['verdict'].split(' ')[0])}">{r['verdict']}</span>
     <span class="meta">n={r['cluster_size']} &middot; {r['cluster_type']} &middot;
     machine confidence {r['confidence']}</span></h3>
 <div class="expl">{r['explanation']}</div>{amb}
 <div class="row">
  <div class="members"><div class="lbl">cluster members (scan)</div>{thumbs}</div>
  <div class="cands"><div class="lbl">font candidates</div>{cands}</div>
 </div>
 <div class="decide">
  <label><input type="radio" name="d_{cname}" value="accept"> accept #1</label>
  <label><input type="radio" name="d_{cname}" value="ambiguous"> correct but ambiguous (keep group)</label>
  <label><input type="radio" name="d_{cname}" value="unmapped"> unmapped</label>
  <label><input type="radio" name="d_{cname}" value="junk"> junk/noise</label>
  <label>other glyph: <select name="g_{cname}"><option value=""></option>{glyph_options}</select></label>
  <label class="notes">notes: <input type="text" name="n_{cname}" size="40"></label>
 </div>
</div>""")

html = """<!doctype html><html><head><meta charset="utf-8">
<title>Uigurica - Phase 5.5 mapping validation</title><style>
body{font-family:Segoe UI,Arial,sans-serif;margin:16px;background:#fafafa}
.card{background:#fff;border:1px solid #ccc;border-radius:8px;padding:10px 14px;margin:14px 0}
h3{margin:2px 0 6px}
.tag{font-size:12px;padding:2px 8px;border-radius:10px;color:#fff}
.treview{background:#e69500}.tunmapped{background:#c0392b}.tmapped{background:#27823b}
.meta{font-size:12px;color:#666;font-weight:normal}
.expl{font-size:12px;color:#444;margin-bottom:6px}
.amb{font-size:12px;color:#8a2be2;margin-bottom:6px}
.row{display:flex;gap:18px;flex-wrap:wrap}
.members img{height:72px;border:1px solid #ddd;margin:2px;background:#fff}
.cands{display:flex;gap:10px;flex-wrap:wrap}
.cand{text-align:center;border:1px solid #eee;border-radius:6px;padding:4px;font-size:11px}
.cand img{height:84px;display:block;margin:0 auto}
.cn{font-weight:bold;max-width:120px;overflow-wrap:anywhere}
.cm{color:#555}
.lbl{font-size:11px;color:#888;margin-bottom:2px;width:100%}
.decide{margin-top:8px;font-size:13px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
#bar{position:sticky;top:0;background:#2c3e50;color:#fff;padding:10px 14px;border-radius:8px;z-index:9}
#bar button{margin-left:10px}
.done{outline:3px solid #27823b}
</style></head><body>
<div id="bar"><b>Uigurica mapping validation</b>
 <span id="prog"></span>
 <button onclick="exportJSON()">Export decisions JSON</button>
 <button onclick="if(confirm('Clear all decisions?')){localStorage.removeItem(KEY);location.reload()}">Reset</button>
 <span style="font-size:12px">decisions autosave in this browser; export when finished</span>
</div>
""" + "".join(cards) + """
<script>
const KEY='uigurica_map_decisions_v1';
const state=JSON.parse(localStorage.getItem(KEY)||'{}');
function collect(){
 document.querySelectorAll('.card').forEach(card=>{
  const id=card.id;
  const r=card.querySelector('input[type=radio]:checked');
  const g=card.querySelector('select').value;
  const n=card.querySelector('input[type=text]').value;
  const d=g?('glyph:'+g):(r?r.value:null);
  if(d||n)state[id]={decision:d,notes:n};else delete state[id];
  card.classList.toggle('done',!!d);
 });
 localStorage.setItem(KEY,JSON.stringify(state));
 const t=document.querySelectorAll('.card').length;
 document.getElementById('prog').textContent=
   ' '+Object.values(state).filter(s=>s.decision).length+' / '+t+' decided';
}
document.addEventListener('change',collect);
document.addEventListener('input',e=>{if(e.target.type==='text')collect()});
// restore
for(const[id,s]of Object.entries(state)){
 const card=document.getElementById(id);if(!card)continue;
 if(s.decision&&s.decision.startsWith('glyph:'))card.querySelector('select').value=s.decision.slice(6);
 else if(s.decision){const r=card.querySelector('input[value="'+s.decision+'"]');if(r)r.checked=true;}
 if(s.notes)card.querySelector('input[type=text]').value=s.notes;
}
collect();
function exportJSON(){
 collect();
 const blob=new Blob([JSON.stringify(state,null,1)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);
 a.download='mapping_decisions.json';a.click();
}
</script></body></html>"""

out = os.path.join(BASE, "review_mapping.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
tmpl = {cname: {"decision": None, "notes": ""} for cname, _ in items}
with open(os.path.join(BASE, "decisions_template.json"), "w", encoding="utf-8") as f:
    json.dump({"_schema": "decision: accept | candidate:<glyph> | glyph:<glyph>"
                          " | ambiguous | unmapped | junk",
               "decisions": tmpl}, f, indent=1)
print(f"review_mapping.html written ({os.path.getsize(out) / 1e6:.1f} MB), "
      f"{len(items)} cards; decisions_template.json written")
