"""Phase 9 area 3: shaping validation via HarfBuzz.

Old Uyghur (U+10F70-10F89) has Arabic-style joining (all dual-joining except
ZAYIN U+10F74 and FINAL HETH U+10F75 which are right-joining). HarfBuzz
selects .init/.medi/.fina via GSUB from joining context. Checks:
  - every codepoint shapes isolated to its base glyph, no .notdef
  - 3-letter words select init/medi/fina correctly (dual-joining)
  - right-joining letters take .fina after a joining letter and force the
    next letter into a non-joined (isolated/init) form
  - ligature sequences produce the expected ligature glyphs
  - marks (dots) attach with GPOS offsets, not as spacing .notdef
  - NEW font shapes identically to the phase1 backup (same GSUB/GPOS -> any
    difference would mean table corruption)
Validation only.
"""
import json
import os

import uharfbuzz as hb

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
NEW = os.path.join(BASE, "build", "Uigurica-Regular-v1.0.ttf")
OLD = os.path.join(BASE, "build", "Uigurica-Regular.phase1-noto.ttf")

CP = {
    "aleph": 0x10F70, "beth": 0x10F71, "gimel": 0x10F72, "waw": 0x10F73,
    "zayin": 0x10F74, "fheth": 0x10F75, "yodh": 0x10F76, "kaph": 0x10F77,
    "lamedh": 0x10F78, "mem": 0x10F79, "nun": 0x10F7A, "samekh": 0x10F7B,
    "pe": 0x10F7C, "sadhe": 0x10F7D, "resh": 0x10F7E, "shin": 0x10F7F,
    "taw": 0x10F80, "lesh": 0x10F81, "dotabove": 0x10F82, "dotbelow": 0x10F83,
    "twodotsabove": 0x10F84, "twodotsbelow": 0x10F85, "bar": 0x10F86,
    "twobars": 0x10F87, "twodots": 0x10F88, "fourdots": 0x10F89,
}


def shaper(path):
    blob = hb.Blob.from_file_path(path)
    face = hb.Face(blob)
    font = hb.Font(face)
    names = {}
    def shape(text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        out = []
        for i, p in zip(buf.glyph_infos, buf.glyph_positions):
            gname = font.glyph_to_string(i.codepoint)
            out.append({"g": gname, "cluster": i.cluster,
                        "adv": p.x_advance, "dx": p.x_offset, "dy": p.y_offset})
        return out
    return shape


shape_new = shaper(NEW)
shape_old = shaper(OLD)
res = {"checks": [], "issues": []}


def check(name, ok, detail=""):
    res["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        res["issues"].append(f"{name}: {detail}")
    print(("PASS " if ok else "FAIL ") + name + ("  | " + detail if detail and not ok else ""))


C = lambda k: chr(CP[k])

# 1. isolated forms (orphan combining marks legitimately get a dotted
#    circle uni25CC base inserted by the shaper)
COMBINING = {"dotabove", "dotbelow", "twodotsabove", "twodotsbelow"}
bad = []
for k, cp in CP.items():
    out = shape_new(C(k))
    gs = [o["g"] for o in out]
    if ".notdef" in gs or not gs:
        bad.append((k, gs))
    elif k in COMBINING:
        if not any("uyg" in g for g in gs):
            bad.append((k, gs))
    elif len(out) != 1:
        bad.append((k, gs))
check("isolated: every codepoint maps to a real glyph", not bad, str(bad[:4]))

# 2. dual-joining 3-letter word -> init/medi/fina
out = shape_new(C("beth") + C("gimel") + C("mem"))
got = [o["g"] for o in out]
exp_parts = {"bethuyg.init", "gimelHethuyg.medi", "memuyg.fina"}
check("dual join beth+gimel+mem -> init/medi/fina",
      set(got) == exp_parts, f"got {got}")

# 3. right-joining zayin: after beth it takes fina; following taw restarts
out = shape_new(C("beth") + C("zayin") + C("taw"))
got = [o["g"] for o in out]
ok = ("zayinuyg.fina" in got and "bethuyg.init" in got
      and any(x in got for x in ("tawuyg", "tawuyg.init")))
check("right-joining zayin breaks following join", ok, f"got {got}")

out = shape_new(C("beth") + C("fheth") + C("taw"))
got = [o["g"] for o in out]
ok = ("finalHethuyg.fina" in got and "bethuyg.init" in got
      and any(x in got for x in ("tawuyg", "tawuyg.init")))
check("right-joining final-heth breaks following join", ok, f"got {got}")

# 4. ligature kaph+waw (word-internal medial context)
out = shape_new(C("beth") + C("kaph") + C("waw") + C("mem"))
got = [o["g"] for o in out]
lig = [g for g in got if "kaphuyg" in g and "wawuyg" in g]
check("kaph+waw ligature fires in medial context", bool(lig), f"got {got}")

# 5. marks attach with GPOS offsets
out = shape_new(C("beth") + C("dotabove") + C("gimel") + C("mem"))
got = [o["g"] for o in out]
mark = [o for o in out if "dot" in o["g"]]
ok = bool(mark) and all(o["adv"] == 0 for o in mark) and ".notdef" not in got
check("dot-above mark: zero-advance attach, no .notdef", ok,
      f"got {[(o['g'], o['adv'], o['dx'], o['dy']) for o in out]}")

# also composed gimel+twodotsabove (precomposed glyph exists in font)
out = shape_new(C("gimel") + C("twodotsabove"))
got = [o["g"] for o in out]
check("gimel+twodotsabove shapes (mark or precomposed)",
      ".notdef" not in got and got, f"got {got}")

# 6. RTL direction
buf_probe = shape_new(C("beth") + C("mem"))
check("RTL: last letter (mem.fina) output first",
      "memuyg.fina" in buf_probe[0]["g"], f"got {[o['g'] for o in buf_probe]}")

# 7. new font shapes byte-identically to phase1 backup
seqs = [
    C("beth") + C("gimel") + C("mem"),
    C("aleph") + C("shin") + C("kaph"),
    C("beth") + C("zayin") + C("taw"),
    C("lamedh") + C("samekh") + C("beth"),
    C("nun") + C("beth") + C("resh"),
    C("sadhe") + C("gimel") + C("fheth"),
    C("beth") + C("kaph") + C("waw") + C("mem"),
    C("beth") + C("dotabove") + C("gimel"),
    "".join(C(k) for k in CP),
]
mismatch = []
for s in seqs:
    a = [(o["g"],) for o in shape_new(s)]
    b = [(o["g"],) for o in shape_old(s)]
    if a != b:
        mismatch.append({"text": [hex(ord(c)) for c in s],
                         "new": a, "old": b})
check("glyph selection identical to phase1 backup (GSUB unchanged)",
      not mismatch, f"{len(mismatch)} mismatches")

# summarize per-codepoint contextual coverage actually reachable via shaping
forms = {}
for k in ["aleph", "beth", "gimel", "waw", "zayin", "fheth", "yodh", "kaph",
          "lamedh", "mem", "nun", "samekh", "pe", "sadhe", "resh", "shin",
          "taw", "lesh"]:
    row = {}
    row["isol"] = shape_new(C(k))[0]["g"]
    o = shape_new(C(k) + C("beth"))          # letter first -> init
    row["init"] = o[-1]["g"]                  # RTL: first letter comes last
    o = shape_new(C("beth") + C(k) + C("beth"))
    row["medi"] = o[1]["g"] if len(o) == 3 else "?"
    o = shape_new(C("beth") + C(k))
    row["fina"] = o[0]["g"]
    forms[k] = row
res["contextual_forms_shaped"] = forms

with open(os.path.join(BASE, "p9_shaping.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=1)
n_ok = sum(1 for c in res["checks"] if c["ok"])
print(f"\n{n_ok}/{len(res['checks'])} shaping checks pass; p9_shaping.json written")
