# Connector-Removal Pilot — Verdict: Not Yet Clean/Reproducible Enough to Scale

## TL;DR

**Detection** of the baseline connector is clean and reproducible. **Removal + reconnection** is
not, yet — two different reconnection strategies each improved some letters and made others
worse, with no single method winning consistently. I'm not scaling to all 18 letters on this
basis. Below is the real data and a concrete path to actually get there.

## What I tested

**Detection:** morphological opening with a wide (71px) horizontal kernel, applied identically
(no per-word tuning) to all three source words (*tonga*, *ol*, *közünür*-tail).

| Word | Connector found at | Thickness | Width coverage |
|---|---|---|---|
| tonga | 63% down | 24px | 78% of word width |
| ol | 58% down | 20px | 49% of word width |
| közünür-tail | 63% down | 28px | 86% of word width |

Consistent position (±5 points) and thickness (±8px) across three independently-sourced words
using one unchanged kernel — this part is genuinely reproducible.

**Removal:** subtracting the detected connector mask fragments every letter (1–3 pieces →
11–18 pieces), because the connector's core crosses paths with each letter's own strokes at
multiple points near the baseline — expected, not a bug, but it means removal can't stop at
"subtract and done."

**Reconnection, attempt 1 (blanket morphological closing):** restores full connectivity (1–2
components) but adds a lot of ink that was never in the original — 47–62% more ink mass than the
letter-only image had, because closing dilates in every direction, not just where a bridge is
actually needed.

**Reconnection, attempt 2 (minimal skeletal bridging):** connects only the nearest points between
fragments with a thin line matched to the letter's own stem width. Cut synthetic ink addition to
10–19% — a real improvement in *how much* fake material gets added.

## The honest result: less synthetic ink didn't mean better letters

I measured stem-to-height ratio (the one metric from the first pilot I said I'd trust) for the
raw crop, both reconnection methods, and compared each to Noto:

| Letter | Raw (v1) | Blanket-close (v2) | Minimal-bridge (v3) | Noto | Closest to Noto |
|---|---|---|---|---|---|
| Taw | 0.150 | 0.165 | 0.150 | 0.191 | v2 |
| Aleph | 0.130 | 0.174 | 0.096 | 0.357 | v2 |
| Lesh | 0.079 | 0.237 | 0.079 | 0.148 | v3 |
| Zayin | 0.221 | 0.480 | 0.200 | 0.231 | **v1 (untouched!)** |
| Resh | 0.060 | 0.235 | 0.111 | 0.256 | v2 |

Blanket closing (the *more* synthetic-ink-heavy method) wins for 3 of 5 letters. Minimal bridging
— which I built specifically to fix the synthetic-ink problem — only wins for 1. And for Zayin,
**every processing method made things worse than doing nothing.** That's not a marginal result I'd
paper over; it means neither reconnection strategy is reliably modeling what actually happened to
the ink, and "less fake material added" doesn't reliably track "more accurate letter."

My working explanation: Zayin is right-joining (doesn't connect to the letter before it), so its
relationship to the baseline stroke is structurally different from Taw/Aleph/Lesh/Resh — treating
all five with the same connector model may be the wrong assumption for that letter specifically,
not just a tuning problem.

## Why I'm not scaling this to 18 letters

The original ask was conditional: scale it if results are clean and reproducible. They're half of
that — detection is; reconnection isn't. Scaling an unreliable reconnection step across 18 letters
× 4 positions would mean shipping ~70 outlines where I have no consistent way to know, letter by
letter, whether the processing helped or hurt. That's the same failure mode from two turns ago
(confident-looking numbers on data I don't actually trust), just moved one stage downstream.

I also want to flag a limitation in how I've been validating all of this: "closer to Noto" is a
convenient signal, but Noto and Müller's hand are legitimately different designs from different
eras — it's a weak, indirect proxy for "correctly extracted," not ground truth. Some of the
disagreement above could mean my extraction is wrong, or it could mean Müller's letter genuinely
looked less like Noto's than I assumed. I can't tell those apart from geometry alone.

## What I'd do next (haven't started this yet — proposing before building)

1. **Visual review is the actual bottleneck.** My image viewer has been unreliable all session
   (failed even on a trivial test square, intermittently, across multiple turns). Every measurement
   above was computed blind. If you can look at `word_stages/*_reconnected_v3.png` directly and
   tell me whether the bridges look plausible, that's more informative than another round of
   metric-chasing on my end.
2. **Handle Zayin (and other right-joining letters: Final Heth) as a separate case**, not a
   variant of the same connector model — the data says they don't behave the same way.
3. **Try the multi-attestation approach I proposed last turn but didn't build**: pull 3-4
   attestations of the same letter from different words, and keep only ink that's common across
   all of them. More expensive per letter, but it doesn't depend on a hand-tuned bridging
   heuristic at all, which is the part that's currently inconsistent.

I'd rather hand you this real, mixed result now than a clean-looking report that scaling would
later reveal was wrong across 70 glyphs.
