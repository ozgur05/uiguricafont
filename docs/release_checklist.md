# Uigurica Release Checklist — final, after Phase 10 (2026-07-17)

## Release build
- Font: `dist/Uigurica-Regular-v1.0.ttf` (version 1.000, name IDs 3/5 +
  head.fontRevision updated; Windows-platform name records only)
- Pristine baselines kept: `build/Uigurica-Regular.phase1-noto.ttf` (Noto),
  `build/Uigurica-Regular.phase9.ttf` (pre-metrics-refinement)

## Glyph counts
- Production Müller/LeCoq glyphs: **39**
- Draft codepoints retained on Noto outlines: **4** (U+10F84, U+10F85,
  U+10F87, U+10F89 — see draft_review_p10.md)
- Remaining Noto-outline Old Uyghur glyphs: **60** (incl. ligatures and
  contextual forms without production masters)
- Codepoint coverage: 22/26 production, 4 draft, 0 missing

## Validation — all gates PASS
- [x] fontTools structural load
- [x] OTS sanitizer: "File sanitized successfully!"
- [x] fontbakery check-opentype: 0 FATAL / 0 FAIL / 0 WARN (35 PASS)
- [x] fontbakery check-universal: 0 FATAL / 0 FAIL (82 PASS; 4 WARNs are
  inherited Noto-base Latin glyphs: contour-count uogonek, width-outliers
  minus, unreachable-glyphs — none touch Old Uyghur)
- [x] FreeType: every cmapped codepoint renders at 8/16/32/64 px
- [x] HarfBuzz: all codepoints shape without .notdef; init/medi/fina,
  right-joining, ligature, mark attachment verified (9/9 checks)
- [x] Unicode conformance: U+10F70–10F89 fully cmapped; marks carry GDEF
  class 3
- [x] Join audit: 399 adjacent-pair composites, 0 broken (re-run after
  metrics refinement)
- [x] Corpus fidelity vs print (27 human-validated words): median IoU 0.53
  vs 0.29 (Noto), ink coverage 0.81 vs 0.35

## Metrics refinement (Phase 10, outlines untouched)
- bethuyg.medi 326→287, memuyg.medi 428→398, tawuyg.medi 785→473,
  wawuyg.medi 552→331 (translation + advance only; metrics_report_p10.json)

## Known limitations (documented in RELEASE_NOTES.md)
1. Hybrid font — 60 Old Uyghur glyphs still Noto (weight seam in mixed text)
2. 4 draft codepoints on Noto outlines (attestation scarcity; human gate)
3. mem/pe final counters close below ~36 px (faithful to the metal type)

## Readiness score: 86.3 / 100
Release-ready as a public v1.0 with the limitations above documented.
Not yet a fully self-contained (100% Müller) typeface — that is the v1.x
roadmap (harvest remaining ligatures/contextual forms, close draft signs).
