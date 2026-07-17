# Phase 6.1 — Analysis of the Pilot Archives (files-1.zip, files-2.zip)

## What the two reports establish

**PILOT_REPORT.md (files-1)** — 5-letter end-to-end pilot (Taw, Aleph, Lesh,
Zayin, Resh from *tonga*, *ol*, *közünür*):

1. Boundary estimation by two independent methods (Noto advance-width prior +
   stroke pinch-points) corroborated within 6–67 px — the *detection* side of
   segmentation is workable.
2. **Every crop contains a slice of the shared baseline connector** ("washing
   line", 36–72 px band at 58–63% height, 3–6× thicker than the 12–14 px
   letter stems). This contaminates width, aspect-ratio, and angle metrics.
   Only stem/height ratio survived.
3. The one trusted, repeated finding: **Müller's strokes are proportionally
   thinner than Noto's** (Noto 2.7–4× thicker for Aleph/Resh). Confirms the
   standing rule: Müller is the design master; do not normalize toward Noto.

**VERDICT.md (files-2)** — connector-removal pilot:

1. Connector *detection* is clean and reproducible (71 px horizontal opening;
   consistent position ±5 pts, thickness ±8 px across three words).
2. Connector *removal + reconnection* is NOT reproducible:
   - subtraction fragments letters into 11–18 pieces;
   - blanket closing re-adds 47–62% synthetic ink;
   - minimal skeletal bridging adds only 10–19% but produced *worse* letters
     for 3 of 5 cases;
   - for Zayin **every** processing variant was worse than doing nothing.
3. Zayin misbehaves because it is right-joining — its relationship to the
   baseline stroke is structurally different. Right-joining letters (ZAYIN,
   FINAL HETH per L2/20-191) need a separate connector model.
4. "Closer to Noto" is a weak validation proxy — Noto and Müller are
   legitimately different designs; geometric closeness to Noto must not be
   used as an accept/reject gate.

Visual check of the included images (done here, the pilot's viewer was
broken): `ol_reconnected_v3.png` shows the baseline hollowed and broken
versus `aleph_CONTEXT_fullword.png` — the verdict's "not clean enough to
scale" call is correct.

## Consequences adopted for Phases 6/7 (the four directives)

1. **(truncated directive — read as: do not trust single-sample crops)**
   Single-attestation extraction with estimated boundaries is a draft-only
   path.
2. **No code manipulation (reconnection) on base glyphs.** The
   detect→subtract→re-bridge pipeline is BANNED for production outlines.
   Nothing synthetic may be drawn into a letter.
3. **Multi-attestation strategy.** Production outlines come from 3–4+
   aligned attestations per letter; the consensus (common-denominator ink,
   majority vote at the 0.5 level) is what removes the connector and the
   halftone noise *statistically* instead of surgically. The connector
   slice survives only where it overlaps in ≥50% of attestations after
   alignment — and since attestations come from different words, the
   connector's extent varies while the letter is invariant; the vote keeps
   the letter and trims the accidental.
4. **Config + code for the next phases** — delivered as
   `phase_architecture.json` (machine-readable contract) and
   `tools/attestation_inventory.py` (readiness audit driving Phase 7).

## How this maps onto the existing Phase 6 output

The Phase 6 master generator (tools/generate_masters.py) already implements
the multi-attestation consensus: aligned stacks, phase-correlation
refinement, 0.5 majority vote, no synthetic bridging. The pilot findings
*converge* with that architecture rather than contradict it. What changes:

- attestation minimums are now enforced and audited (masters built from 1–2
  members are demoted to "draft" status explicitly);
- right-joining letters get a dedicated flag; their masters must come from
  word-final/isolated attestations only, never from cut interiors;
- Noto-similarity is recorded as metadata but never used as a quality gate;
- the pilot's single-sample GLIF (zayinuyg.muller.glif) is kept as reference
  under pilot/ and explicitly NOT promoted to masters/.
