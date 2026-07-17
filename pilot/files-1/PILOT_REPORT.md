# Pilot Batch Report — 5 Letters, End-to-End (Extract → Vectorize → Compare)

**Letters:** Taw, Aleph, Lesh, Zayin, Resh — chosen for: Taw & Resh (Unicode proposal cites
Müller p.44 for these exact letters, giving independent scholarly grounding), Aleph & Lesh
(paired via the short word *"ol"*, giving one guaranteed-clean word-final boundary each),
Zayin (the rarer right-joining letter type, testing whether that joining rule produces a
detectable pixel gap).

**Source attestations:** *tonga* (p.36 line 1) → Taw · *ol* (p.36 line 14) → Aleph, Lesh ·
*közünür* (p.36 line 6) → Zayin, Resh

**Important limitation up front:** my image viewer was unreliable for most of this session
(intermittent — worked a few times, failed most others, including on a trivial 200×200 test
square). Everything below was produced and checked **programmatically** rather than by eye. The
actual crop/context PNGs are included in the output folder specifically so you can visually
check my boundary calls yourself — please do, especially before trusting the "estimated" edges
described below.

## Step 1: Extraction method

Old Uyghur letters share ink with their neighbors (established last turn), so no boundary is
100% clean. For each letter I used whichever side of the target word is genuinely
whitespace-bounded, and estimated the other side two independent ways:

1. **Proportional prior** — Noto's own advance-widths for the letters in that word, scaled to
   the word's actual pixel width.
2. **Stroke-width pinch-point** — a distance-transform profile along the word, taking local
   minima in ink thickness as candidate letter-junctions.

The two methods agreed within 10–70px in all five cases (out of letters roughly 100–350px
wide) — real corroboration, not just one heuristic asserting itself. Final boundaries used the
pinch-point nearest the proportional estimate. Confidence by letter:

| Letter | Clean edge (real gap) | Estimated edge | Agreement between the two methods |
|---|---|---|---|
| Taw | left | right | 33px apart — good |
| Aleph | left | right | 22px apart — good |
| Lesh | right | left | 67px apart — moderate |
| Zayin | left | right | 6px apart — very good |
| Resh | right | left | 11px apart — good |

## Step 2: A problem the pilot was specifically supposed to catch — and did

Measuring the extracted crops turned up something I hadn't accounted for: **every crop contains
a slice of the continuous baseline connector stroke**, not just the target letter. Evidence: in
three separate crops (from two different lines), there's a single row sitting at a near-identical
relative height (58–61% down) where ink spans 75–87% of the *entire crop width* — far wider than
any one letter's own body. That row is the "washing-line" stroke that ties the whole printed
line together. Its band is 36–72px thick, i.e. **3–6× thicker than the letters' own ~12–14px
stems** — so it's not a thin ligature thread I can filter out by weight, it's a genuine
ink-convergence zone where letters' lower strokes bunch at the baseline.

Practical effect: **width/aspect-ratio and whole-shape angle measurements below are contaminated
and I don't trust them.** Stem-width-at-the-thickest-point is less affected (it samples the
letter's own densest stroke, which the thin connector band mostly doesn't dominate), so I'm
reporting that metric with more confidence than the others.

This means the crop pipeline is not yet ready to scale to all 18 letters as-is — it needs an
explicit connector-stroke removal step first (candidates: skeleton-based pruning of the
near-horizontal baseline branch, or a comparative approach using multiple attestations of the
same letter to isolate what's invariant vs. what's shared baseline). I'd build that before
doing the full alphabet, not after.

## Step 3: Vectorization (potrace — real Bézier tracing, not a placeholder)

| Letter | Contours | Bézier curve segments | Note |
|---|---|---|---|
| Taw | 3 | 84 | multiple contours = likely real sub-stroke gaps in this letter, unverified |
| Aleph | 1 | 91 | |
| Lesh | 1 | 280 | complex trace; would benefit from more aggressive simplification before production use |
| Zayin | 1 | 37 | cleanest trace of the five |
| Resh | 1 | 158 | |

Outputs: `svg/*.svg` (clean potrace vector curves) and `ufo_glyphs/*.glif` (valid UFO2 glyph
XML — advance width, Unicode mapping, cubic curve points with smooth-tangent flags). Both are
tagged `.muller` and explicitly noted as draft/unmerged so they can't be confused with production
glyphs if dropped into a UFO project directly.

## Step 4: Comparison to Noto

Rendered the corresponding Noto glyph for each letter via FreeType at a matched scale and ran
the *identical* measurement code on both, so the comparison is apples-to-apples methodologically
— though see the Step 2 caveat on which numbers to trust:

| Letter | Metric | Müller | Noto | Delta | Trust this number? |
|---|---|---|---|---|---|
| Taw | aspect ratio (w/h) | 1.29 | 0.81 | +0.48 | Low — connector-contaminated |
| Taw | stem/height ratio | 0.150 | 0.191 | −0.041 | **Moderate** |
| Aleph | aspect ratio | 1.91 | 0.86 | +1.05 | Low |
| Aleph | stem/height ratio | 0.130 | 0.357 | −0.227 | **Moderate** |
| Lesh | aspect ratio | 2.26 | 0.52 | +1.75 | Low |
| Lesh | stem/height ratio | 0.079 | 0.148 | −0.069 | **Moderate** |
| Zayin | aspect ratio | 1.75 | 0.73 | +1.03 | Low |
| Zayin | stem/height ratio | 0.221 | 0.231 | −0.010 | **Moderate** |
| Resh | aspect ratio | 1.10 | 1.54 | −0.44 | Low |
| Resh | stem/height ratio | 0.060 | 0.256 | **−0.196** | **Moderate** |

Slant angle is dropped from this table entirely: my first metric (whole-shape PCA) turned out to
mostly re-measure aspect ratio, not true stroke angle, and a second attempt (RANSAC longest
straight run) mostly found the contaminating baseline connector instead of any letter stem. I
don't have a slant number I'd stand behind yet.

**What the one metric I do trust (stem/height ratio) says, consistently across all five letters:**
Müller's printed strokes are thinner relative to letter height than Noto's — by a wide margin for
Aleph and Resh (Noto ~2.7–4× thicker), narrower gap for the others. That's a real, directional,
repeated finding, not noise from one outlier letter. It's consistent with what you'd expect
comparing a fine-lined 1908 scholarly facsimile against a modern text-optimized book face
designed to hold up at small sizes.

## Bottom line

- Real extraction, real potrace vectorization, real UFO output, real Noto comparison — all done,
  all in the output folder.
- One trustworthy, consistent finding: Müller's strokes are proportionally thinner than Noto's.
- One methodological problem surfaced and diagnosed, not papered over: crops are contaminated by
  the shared baseline connector, which invalidates width/aspect/angle measurements until that's
  specifically handled.
- I did not attempt to "fix" this by quietly adjusting numbers — the report above shows exactly
  which measurements survive the problem and which don't.

## Recommendation before scaling to all 18 letters

Build the connector-stroke separation step first. Two candidate approaches, roughly in order of
effort: (1) skeleton-prune the near-horizontal baseline branch out of each crop before measuring
— cheap, but risks cutting into letters that genuinely have a horizontal element; (2) pull 3-4
attestations of the same letter from different words and keep only the ink that's common to all
of them — more robust, more work. Happy to pilot either on these same 5 letters before committing
to all 18 × 4 positions.
