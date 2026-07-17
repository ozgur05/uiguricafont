"""Phase 5: map visual clusters to the original font's glyphs.

Input : updated_clusters.json (Phase 4.6), decomposition.json,
        decomposed_segments/, segments/, build/Uigurica-Regular.ttf
Output: font_glyphs/<glyph>.png            rendered font glyphs (ink alpha)
        mapping_table.json / mapping_table.csv
        mapping_report.pdf                 one page per cluster
        qa/font_render_check.png

Method
  - every Old Uyghur glyph (isolated/init/medi/fina, ligatures, marks,
    punctuation) rendered with FreeType at 200 ppem
  - font glyphs and up to 8 sampled members per cluster pushed through the
    SAME descriptor recipe (blurred 32x32 ink, Zernike<=8, Hu, contour,
    skeleton, log-aspect); z-scored JOINTLY so scan and font live in one
    feature space.  Absolute pixel size is EXCLUDED (scan px and font ppem
    are unrelated scales) but RELATIVE size is not: each item carries
    log(height / median letter height of its own domain), which separates
    dots/marks from letters on both sides of the comparison.
  - cluster vector = mean of member vectors; similarity = cosine
  - positional evidence: pieces know their x-position in the parent word;
    Old Uyghur here runs right-to-left, so last piece (rightmost) = initial,
    piece 0 (leftmost) = final, interior = medial, unsplit = isolated/word.
    A glyph form agreeing with the dominant member position earns +0.04,
    a contradicting form -0.04.
  - joining model (L2/20-191): zayin and final heth are right-joining; the
    font correctly has NO init/medi glyphs for them, so impossible forms
    cannot be assigned; the validation section re-checks this explicitly.
  - shape twins: dot above/below and two-dots above/below are IDENTICAL
    glyph shapes distinguished only by mark position, which an isolated
    image cannot see.  The verdict margin is therefore computed against the
    best candidate OUTSIDE the top glyph's twin group, and a twin note is
    added to the explanation.
  - verdicts: mapped (adj>=0.70 & outside-group margin>=0.05),
    review (adj>=0.55), unmapped otherwise.  Word-segment clusters are only
    eligible for ligature glyphs; otherwise reported as unmapped
    multi-letter.

No font tables are modified.  Mapping is a proposal with confidence, not
a final assignment.
"""
import csv
import json
import math
import os

import cv2
import freetype
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from skimage.morphology import skeletonize

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
FONT = os.path.join(BASE, "build", "Uigurica-Regular.ttf")
FG = os.path.join(BASE, "font_glyphs")
os.makedirs(FG, exist_ok=True)
PPEM = 200
MEMBER_SAMPLE = 8

LETTERS = {  # base name -> (codepoint, unicode name, joining)
    "alephuyg": (0x10F70, "ALEPH", "dual"), "bethuyg": (0x10F71, "BETH", "dual"),
    "gimelHethuyg": (0x10F72, "GIMEL-HETH", "dual"), "wawuyg": (0x10F73, "WAW", "dual"),
    "zayinuyg": (0x10F74, "ZAYIN", "right"), "finalHethuyg": (0x10F75, "FINAL HETH", "right"),
    "yodhuyg": (0x10F76, "YODH", "dual"), "kaphuyg": (0x10F77, "KAPH", "dual"),
    "lamedhuyg": (0x10F78, "LAMEDH", "dual"), "memuyg": (0x10F79, "MEM", "dual"),
    "nunuyg": (0x10F7A, "NUN", "dual"), "samekhuyg": (0x10F7B, "SAMEKH", "dual"),
    "peuyg": (0x10F7C, "PE", "dual"), "sadheuyg": (0x10F7D, "SADHE", "dual"),
    "reshuyg": (0x10F7E, "RESH", "dual"), "shinuyg": (0x10F7F, "SHIN", "dual"),
    "tawuyg": (0x10F80, "TAW", "dual"), "leshuyg": (0x10F81, "LESH", "dual"),
}
MARKS = {"dotaboveuyg": (0x10F82, "COMBINING DOT ABOVE"),
         "dotbelowuyg": (0x10F83, "COMBINING DOT BELOW"),
         "twodotsaboveuyg": (0x10F84, "COMBINING TWO DOTS ABOVE"),
         "twodotsbelowuyg": (0x10F85, "COMBINING TWO DOTS BELOW")}
PUNCT = {"PunctuationBar": (0x10F86, "PUNCTUATION BAR"),
         "PunctuationTwoBars": (0x10F87, "PUNCTUATION TWO BARS"),
         "PunctuationTwoDots": (0x10F88, "PUNCTUATION TWO DOTS"),
         "PunctuationFourDots": (0x10F89, "PUNCTUATION FOUR DOTS")}


def glyph_meta(name):
    """derive (base letters, form, category, unicode info) from glyph name"""
    if name in MARKS:
        return [name], "isolated", "mark", MARKS[name]
    if name in PUNCT:
        return [name], "isolated", "punctuation", PUNCT[name]
    if name == "uni0640":
        return [name], "medial", "tatweel", (0x0640, "ARABIC TATWEEL")
    if name == "u10AF2":
        return [name], "isolated", "other", (0x10AF2, "MANICHAEAN DOUBLE DOT WITHIN DOT")
    if name == "gimelHethtwodotsaboveuyg":
        return ["gimelHethuyg", "twodotsaboveuyg"], "isolated", "letter+mark", None
    if "_" in name:  # ligature
        parts = name.split("_")
        bases, forms = [], []
        for p in parts:
            b, _, f = p.partition(".")
            bases.append(b)
            forms.append(f or "isol")
        form = forms[-1] if forms[-1] in ("init", "medi", "fina") else "isolated"
        # ligature form = form of the sequence: first part's joining side
        f0, f1 = forms[0], forms[-1]
        form = {("isol", "isol"): "isolated", ("init", "medi"): "initial",
                ("init", "init"): "initial", ("init", "fina"): "isolated",
                ("medi", "medi"): "medial", ("medi", "fina"): "final",
                ("fina", "fina"): "final"}.get((f0, f1), "unknown")
        return bases, form, "ligature", None
    b, _, f = name.partition(".")
    form = {"init": "initial", "medi": "medial", "fina": "final",
            "alt": "final-variant", "": "isolated"}.get(f, f)
    if b in LETTERS:
        return [b], form, "letter", LETTERS[b]
    return [b], form, "other", None


# ---------------- render font glyphs ----------------
tt = TTFont(FONT)
order = tt.getGlyphOrder()
uyg = [n for n in order if "uyg" in n or "Punctuation" in n or n in ("u10AF2", "uni0640")]
face = freetype.Face(FONT)
face.set_pixel_sizes(0, PPEM)
glyph_imgs = {}
glyph_info = {}
for name in uyg:
    gid = tt.getGlyphID(name)
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.width == 0 or bm.rows == 0:
        continue
    ink = np.array(bm.buffer, np.float32).reshape(bm.rows, bm.pitch)[:, :bm.width] / 255.0
    glyph_imgs[name] = ink
    bases, form, cat, uni = glyph_meta(name)
    glyph_info[name] = {
        "glyph_id": gid, "letters": bases, "form": form, "category": cat,
        "codepoint": f"U+{uni[0]:04X}" if uni else None,
        "unicode_name": ("OLD UYGHUR LETTER " + uni[1] if cat == "letter"
                         else uni[1] if uni else None),
        "joining": (LETTERS[bases[0]][2] if bases[0] in LETTERS else None),
    }
    out = np.zeros((*ink.shape, 4), np.uint8)
    out[:, :, 3] = (ink * 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(os.path.join(FG, name + ".png"))
print(f"rendered {len(glyph_imgs)} font glyphs at {PPEM} ppem -> font_glyphs/")


# ---------------- shared descriptor ----------------
def zernike_magnitudes(img, order=8):
    h, w = img.shape
    ys, xs = np.mgrid[0:h, 0:w]
    x = (xs - (w - 1) / 2) / ((w - 1) / 2)
    y = (ys - (h - 1) / 2) / ((h - 1) / 2)
    rho = np.hypot(x, y)
    theta = np.arctan2(y, x)
    disk = rho <= 1.0
    wgt = img * disk
    mass = wgt.sum()
    out = []
    for n in range(order + 1):
        for m in range(n % 2, n + 1, 2):
            R = np.zeros_like(rho)
            for k in range((n - m) // 2 + 1):
                c = ((-1) ** k * math.factorial(n - k) /
                     (math.factorial(k) * math.factorial((n + m) // 2 - k) *
                      math.factorial((n - m) // 2 - k)))
                R += c * rho ** (n - 2 * k)
            V = R * np.exp(-1j * m * theta)
            out.append(abs((n + 1) / np.pi * (wgt * V)[disk].sum() / max(mass, 1e-9)))
    return np.array(out, np.float32)


KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def descriptor(ink):
    """ink: float 0..1, already trimmed"""
    h, w = ink.shape
    # canvases
    cans = {}
    for S in (64, 128):
        sc = S / max(w, h)
        nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
        s = np.asarray(Image.fromarray((ink * 255).astype(np.uint8), "L")
                       .resize((nw, nh), Image.LANCZOS), np.float32) / 255.0
        c = np.zeros((S, S), np.float32)
        c[(S - nh) // 2:(S - nh) // 2 + nh, (S - nw) // 2:(S - nw) // 2 + nw] = s
        cans[S] = c
    v = gaussian_filter(cans[64], 2.0)[::2, ::2].flatten()
    nv = np.linalg.norm(v)
    img32 = v / nv if nv > 0 else v
    zern = zernike_magnitudes(cans[128])
    mask = (ink > 0.5).astype(np.uint8)
    hu = cv2.HuMoments(cv2.moments(mask, binaryImage=True)).flatten()
    hu = np.array([-np.sign(x) * np.log10(abs(x)) if x != 0 else 0.0 for x in hu],
                  np.float32)
    cmask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, KERNEL)
    cnts, hier = cv2.findContours(cmask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    n_holes = perim = 0
    if hier is not None:
        for i, c in enumerate(cnts):
            perim += cv2.arcLength(c, True)
            n_holes += hier[0][i][3] != -1
    area = float(cmask.sum())
    compact = 4 * np.pi * area / perim ** 2 if perim > 0 else 0.0
    hullpts = np.column_stack(np.nonzero(cmask)[::-1])
    hull = cv2.convexHull(hullpts) if len(hullpts) >= 3 else None
    ha = float(cv2.contourArea(hull)) if hull is not None and len(hull) >= 3 else area
    sk = skeletonize(cmask > 0)
    nb = cv2.filter2D(sk.astype(np.uint8), -1,
                      np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], np.uint8),
                      borderType=cv2.BORDER_CONSTANT)
    cont = np.array([compact, area / ha if ha > 0 else 1.0, area / (w * h),
                     min(n_holes, 12), np.log1p(((nb == 1) & sk).sum()),
                     np.log1p(((nb >= 3) & sk).sum())], np.float32)
    geom = np.array([np.log(w / h)], np.float32)
    return img32, zern, hu, cont, geom, cans[128]


def load_ink(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    alpha = a[:, :, 3]
    ys, xs = np.nonzero(alpha > 0)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gray = a[:, :, :3].mean(axis=2)
    return (a[:, :, 3] / 255.0) * (1.0 - gray / 255.0)


# ---------------- gather items ----------------
upd = json.load(open(os.path.join(BASE, "updated_clusters.json"), encoding="utf-8"))
decomp = json.load(open(os.path.join(BASE, "decomposition.json"), encoding="utf-8"))
piece_pos = {}
for p in decomp["pieces"]:
    n = p["n_pieces_in_parent"]
    i = p["piece_index"]
    piece_pos[p["filename"]] = ("isolated" if n == 1 else
                                "initial" if i == n - 1 else
                                "final" if i == 0 else "medial")

rows = []       # (kind, key, ink)
for gname, ink in glyph_imgs.items():
    rows.append(("font", gname, ink))
cluster_members = {}
for cname, c in upd["clusters"].items():
    mem = c["members"]
    step = max(1, len(mem) // MEMBER_SAMPLE)
    sample = mem[::step][:MEMBER_SAMPLE]
    cluster_members[cname] = sample
    d = "decomposed_segments" if c["representative_dir"] == "decomposed_segments" else "segments"
    for fn in sample:
        rows.append((cname, fn, load_ink(os.path.join(BASE, d, fn))))

print(f"computing descriptors for {len(rows)} items "
      f"({len(glyph_imgs)} font + cluster samples)...")
descs = [descriptor(ink) for _, _, ink in rows]
img32 = np.stack([d[0] for d in descs])
zern = np.stack([d[1] for d in descs])
hu = np.clip(np.stack([d[2] for d in descs]), -12, 12)
cont = np.stack([d[3] for d in descs])
geom = np.stack([d[4] for d in descs])
can128 = {(rows[i][0], rows[i][1]): descs[i][5] for i in range(len(rows))}

# relative size: height / median letter height OF THE SAME DOMAIN
anchor_font = float(np.median([glyph_imgs[n].shape[0] for n in LETTERS
                               if n in glyph_imgs]))
anchor_scan = float(np.median([p["height"] for p in decomp["pieces"]]))
rel = np.array([np.log(rows[i][2].shape[0] /
                       (anchor_font if rows[i][0] == "font" else anchor_scan))
                for i in range(len(rows))], np.float32)
geom = np.hstack([geom, rel[:, None]])
print(f"size anchors: font={anchor_font:.0f}px, scan={anchor_scan:.0f}px")


def z(m):
    sd = m.std(axis=0)
    sd[sd == 0] = 1
    return (m - m.mean(axis=0)) / sd


X = np.hstack([3.0 * img32, 1.0 * z(zern) / np.sqrt(zern.shape[1]),
               0.5 * z(hu) / np.sqrt(7), 1.0 * z(cont) / np.sqrt(6),
               1.5 * z(geom) / np.sqrt(2)])
X = X / np.linalg.norm(X, axis=1, keepdims=True)

font_idx = {rows[i][1]: i for i in range(len(rows)) if rows[i][0] == "font"}
cvecs = {}
for cname in upd["clusters"]:
    idxs = [i for i in range(len(rows)) if rows[i][0] == cname]
    v = X[idxs].mean(axis=0)
    cvecs[cname] = v / np.linalg.norm(v)

fnames = list(font_idx)
F = np.stack([X[font_idx[n]] for n in fnames])

# ---------------- match ----------------
# ambiguity groups, COMPUTED from font-glyph mutual similarity: glyphs whose
# renders are >=0.93 cosine-similar are visually indistinguishable in an
# isolated segment (dot above vs below; the near-identical tooth letters).
# Margins are taken against the best candidate OUTSIDE the top glyph's group,
# and the whole group is reported with the mapping.
GG = F @ F.T
parent = list(range(len(fnames)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


for a in range(len(fnames)):
    for b in range(a + 1, len(fnames)):
        if GG[a, b] >= 0.93:
            parent[find(a)] = find(b)
GROUP = {}
for i, n in enumerate(fnames):
    GROUP.setdefault(find(i), []).append(n)
GROUP = {n: sorted(g) for r, g in GROUP.items() for n in g if len(g) > 1}
n_groups = len({tuple(v) for v in GROUP.values()})
print(f"ambiguity groups: {n_groups} groups covering {len(GROUP)} glyphs")
results = {}
for cname, c in upd["clusters"].items():
    sims = F @ cvecs[cname]
    # positional evidence
    pos_frac = {}
    if c["source"] == "decomposed pieces":
        ps = [piece_pos[m] for m in c["members"] if m in piece_pos]
        for p in ps:
            pos_frac[p] = pos_frac.get(p, 0) + 1 / len(ps)
    adj = sims.copy()
    for j, gn in enumerate(fnames):
        form = glyph_info[gn]["form"]
        if pos_frac:
            agree = pos_frac.get(form, 0.0)
            adj[j] += 0.04 * agree - 0.04 * (1 - agree - pos_frac.get("isolated", 0) * 0.5)
        # word segments may only map to ligatures
        if c["type"] == "word segment" and glyph_info[gn]["category"] != "ligature":
            adj[j] -= 1.0
    rank = np.argsort(-adj)
    top = [(fnames[j], round(float(sims[j]), 4), round(float(adj[j]), 4))
           for j in rank[:5]]
    s1 = top[0][2]
    grp = GROUP.get(top[0][0], [top[0][0]])
    # margin vs best candidate OUTSIDE the top glyph's ambiguity group
    s_out = next(float(adj[j]) for j in rank[1:] if fnames[j] not in grp)
    margin = s1 - s_out
    verdict = ("mapped" if s1 >= 0.70 and margin >= 0.05 else
               "review" if s1 >= 0.55 else "unmapped")
    if c["type"] == "word segment" and s1 < 0.55:
        verdict = "unmapped (multi-letter word segment)"
    gi = glyph_info[top[0][0]]
    # category guard: a tiny mark cluster cannot hard-map to a letter glyph
    # (nor a letter-sized cluster to a mark) - normalization makes a 40px dot
    # and a letter body look alike, so demand human review for such pairs
    size_mismatch = ((c["type"] in ("diacritic", "punctuation-like mark") and
                      gi["category"] in ("letter", "ligature", "tatweel")) or
                     (c["type"] in ("letter candidate", "word segment") and
                      gi["category"] in ("mark", "punctuation")))
    if size_mismatch and verdict == "mapped":
        verdict = "review"
    expl = []
    expl.append(f"visual similarity {top[0][1]:.3f} to {top[0][0]}"
                f" (margin {margin:.3f} outside ambiguity group)")
    if len(grp) > 1:
        expl.append("visually indistinguishable in isolation from: " +
                    ", ".join(g for g in grp if g != top[0][0]))
    if size_mismatch:
        expl.append(f"size-class mismatch: cluster is {c['type']} but glyph "
                    f"is {gi['category']} - demoted to review")
    if pos_frac:
        dom = max(pos_frac, key=pos_frac.get)
        expl.append(f"members occur {dom} in {pos_frac[dom] * 100:.0f}% of words"
                    f" (glyph form: {gi['form']})")
    if c["type"] == "word segment":
        expl.append("multi-letter segment: only ligature glyphs eligible")
    if gi["joining"] == "right":
        expl.append(f"{gi['letters'][0]} is right-joining per L2/20-191; "
                    "only isolated/final forms exist")
    if c["median_width"] / max(c["median_height"], 1) > 4:
        expl.append("extreme elongation: may be an undivided letter run")
    results[cname] = {
        "cluster_size": c["size"], "cluster_type": c["type"],
        "representative": c["representative"],
        "top_candidates": [{"glyph": g, "similarity": s, "adjusted": a,
                            "form": glyph_info[g]["form"],
                            "codepoint": glyph_info[g]["codepoint"],
                            "unicode_name": glyph_info[g]["unicode_name"]}
                           for g, s, a in top],
        "best_glyph": top[0][0],
        "ambiguity_group": grp if len(grp) > 1 else None,
        "confidence": round(float(np.clip((s1 - 0.5) / 0.4, 0, 1) *
                                  np.clip(0.5 + 5 * margin, 0, 1)), 3),
        "verdict": verdict,
        "position_distribution": {k: round(v, 3) for k, v in pos_frac.items()},
        "explanation": "; ".join(expl),
    }

# ---------------- joining-model validation ----------------
violations = []
for cname, r in results.items():
    if not r["verdict"].startswith("mapped"):
        continue
    gi = glyph_info[r["best_glyph"]]
    if gi["joining"] == "right" and gi["form"] in ("initial", "medial"):
        violations.append(f"{cname} -> {r['best_glyph']} ({gi['form']}) "
                          "IMPOSSIBLE for right-joining letter")

# duplicates / coverage
claimed = {}
for cname, r in results.items():
    if r["verdict"].startswith("mapped"):
        claimed.setdefault(r["best_glyph"], []).append(cname)
dups = {g: cs for g, cs in claimed.items() if len(cs) > 1}
unclaimed = [g for g in fnames if g not in claimed]

meta = {
    "font": "build/Uigurica-Regular.ttf (Phase 1; outlines identical to Noto)",
    "n_clusters": len(results),
    "mapped": sum(1 for r in results.values() if r["verdict"] == "mapped"),
    "review": sum(1 for r in results.values() if r["verdict"] == "review"),
    "unmapped": sum(1 for r in results.values() if r["verdict"].startswith("unmapped")),
    "joining_violations": violations,
    "duplicate_assignments": dups,
    "font_glyphs_unclaimed": unclaimed,
    "note": ("mapping is a scored proposal, not a final assignment; "
             "font not modified"),
}
with open(os.path.join(BASE, "mapping_table.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": meta, "glyph_info": glyph_info, "mappings": results},
              f, indent=1)
with open(os.path.join(BASE, "mapping_table.csv"), "w", newline="",
          encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["cluster", "size", "type", "verdict", "confidence",
                 "best_glyph", "form", "codepoint", "unicode_name",
                 "similarity", "second_glyph", "second_similarity",
                 "explanation"])
    for cname, r in results.items():
        t = r["top_candidates"]
        wr.writerow([cname, r["cluster_size"], r["cluster_type"], r["verdict"],
                     r["confidence"], t[0]["glyph"], t[0]["form"],
                     t[0]["codepoint"], t[0]["unicode_name"], t[0]["similarity"],
                     t[1]["glyph"], t[1]["similarity"], r["explanation"]])

print(f"mapped={meta['mapped']} review={meta['review']} "
      f"unmapped={meta['unmapped']} | dups={len(dups)} "
      f"unclaimed glyphs={len(unclaimed)} | violations={len(violations)}")

# ---------------- report PDF ----------------
pages = []
for cname, r in results.items():
    pg = Image.new("RGB", (900, 420), "white")
    dr = ImageDraw.Draw(pg)
    dr.text((10, 8), f"{cname}  size={r['cluster_size']} type={r['cluster_type']} "
            f"verdict={r['verdict']} conf={r['confidence']}", fill=(0, 0, 0))
    dr.text((10, 24), r["explanation"][:120], fill=(60, 60, 60))
    rep = can128[(cname, cluster_members[cname][0])]
    # cluster representative = medoid image
    repfile = r["representative"]
    if (cname, repfile) in can128:
        rep = can128[(cname, repfile)]
    im = Image.fromarray((255 - rep * 255).astype(np.uint8), "L").resize((256, 256))
    pg.paste(im.convert("RGB"), (20, 60))
    dr.text((20, 320), "cluster medoid (scan)", fill=(0, 0, 0))
    for k, cand in enumerate(r["top_candidates"][:3]):
        g = cand["glyph"]
        gm = can128[("font", g)]
        im = Image.fromarray((255 - gm * 255).astype(np.uint8), "L").resize((160, 160))
        x = 330 + k * 190
        pg.paste(im.convert("RGB"), (x, 60))
        dr.text((x, 226), g[:24], fill=(0, 0, 0))
        dr.text((x, 240), f"{cand['form']}  sim={cand['similarity']}", fill=(0, 0, 0))
        if cand["codepoint"]:
            dr.text((x, 254), f"{cand['codepoint']} {(cand['unicode_name'] or '')[:24]}",
                    fill=(0, 0, 0))
    pages.append(pg)
pages[0].save(os.path.join(BASE, "mapping_report.pdf"), save_all=True,
              append_images=pages[1:], resolution=96)
print(f"mapping_report.pdf ({len(pages)} pages), mapping_table.json/.csv written")
