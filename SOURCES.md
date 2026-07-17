# Uigurica — Authoritative Sources and Their Roles

## 1. Unicode Proposal L2/20-191 (Pandey, 2020-12-18) — defines WHAT
Local file: `C:\Users\KutadguBilim\Font\20191-old-uyghur.pdf`
Extracted text: `reference/L2-20-191-text.txt`

Authoritative for:
- Unicode code points (U+10F70–U+10F89, 26 characters)
- Character identities and names
- Joining behavior and positional forms
- Script properties (RTL horizontal default; vertical via layout)
- OpenType shaping model
- Unicode character model (variants NOT encoded: toothed aleph, terminal
  variants, space-filling terminal → font-level stylistic/glyphic variants)

Key normative facts (for quick recall; verify in the document when in doubt):
- 18 letters: ALEPH, BETH, GIMEL-HETH, WAW, ZAYIN, FINAL HETH, YODH, KAPH,
  LAMEDH, MEM, NUN, SAMEKH, PE, SADHE, RESH, SHIN, TAW, LESH (= 'hooked r').
- All letters dual-joining EXCEPT ZAYIN (right-joining) and FINAL HETH
  (right-joining): those two have only isolated + final forms (sec 6.8).
- 4 combining marks (Mn, NSM): DOT ABOVE (ccc 230), DOT BELOW (ccc 220),
  TWO DOTS ABOVE (230), TWO DOTS BELOW (220). Encoded AFTER the base letter.
- 4 punctuation (Po, R): BAR, TWO BARS, TWO DOTS, FOUR DOTS.
- Script extensions: U+0640 ARABIC TATWEEL (stem extension / kashida),
  U+10AF2 MANICHAEAN PUNCTUATION DOUBLE DOT WITHIN DOT.
- Terminal inter-word connections: stylistic; encode with ZWNJ (U+200C)
  in place of space when reproducing the calligraphic join (sec 8.4).
- Vowels as matres lectionis: aleph/waw/yodh digraphs & trigraphs (sec 8.1).
- Disambiguation combos (sec 8.2): gimel-heth+dot(s) above; zayin+dot(s)
  below; final-heth+dot(s) above; nun+dot above; shin+two dots below.
- Representative glyphs = 'square' style, validated against Mueller (1908).
- Isolated forms follow U 40 / Kashgari enumeration tradition (not final
  forms as in typical Unicode cursive-script practice).

Known internal inconsistency in L2/20-191 (resolved):
- Sec 9.4 draft ArabicShaping.txt line reads `10F74; OLD UYGHUR ZAYIN; D`,
  but the document history ("Confirmed the right-joining behavior for
  zayin"), sec 5.1.5, sec 6.6, and sec 6.8 all specify RIGHT-joining.
  Right-joining is the correct reading; released Unicode data (14.0) has R.

## 2. F. W. K. Mueller, Uigurica I (1908), pp. 36-45 — defines HOW
Scans: `scans/page36.png` … `page45.png` (1200 dpi, lossless)

Authoritative for:
- Historical glyph design, printed letterforms
- Stroke style, serif design, proportions
- Visual appearance of glyphs

Pages containing Old Uyghur metal type (glyph source material):
- p. 36 (T III 84, 13), p. 38 (T III 84, 42), p. 40, p. 42 (T III 84, 42),
  p. 44 — full Uyghur text blocks
- pp. 37, 39, 41, 43(?), 45(?) — transliteration + German only (no Uyghur type)
  (43/45 to be confirmed during Phase 3 detection)

The proposal itself validates its contextual forms against Mueller (1908)
and calls its complete repertoire a 'print standard' (sec 4.2: Mueller uses
HORIZONTAL orientation; sec 5.1.1: aleph/nun contrast maintained in all
positions in Mueller; sec 5.1.2: beth/yodh distinct; sec 5.1.9:
samekh/shin distinct finals).

## Rules
1. Never use Uigurica I to infer Unicode assignments or character identities.
2. Never use L2/20-191 as the primary source for glyph design.
3. On any apparent conflict between the two: STOP and report explicitly;
   do not guess.

## Cross-check: Noto Serif Old Uyghur vs L2/20-191 (done, Phase "study")
Script: `tools/check_against_proposal.py`
- cmap: all 26 proposal characters present; plus U+0640, U+10AF2, U+200C,
  U+25CC — exactly the auxiliary set the proposal calls for. NO CONFLICT.
- Dual-joining letters: font implements init/medi/fina for all 16. OK.
- ZAYIN & FINAL HETH: font's init/medi lookups contain only IDENTITY
  mappings (glyph -> itself); real substitution only in fina. Combined
  with Unicode joining type R (engine never applies init/medi to
  right-joiners), behavior matches the proposal. NO CONFLICT.
- Marks U+10F82..85: GDEF class 3 (mark), mark-to-base anchors in GPOS. OK.
- Punctuation U+10F86..89: non-joining. OK.

Verdict: no conflict between the Noto technical foundation and L2/20-191.

## Phase 8 (2026-07-17): Master integration into build/Uigurica-Regular.ttf

The font's glyph outlines are no longer Noto for the 39 glyphs with
production masters: their `glyf` entries now carry the Mueller-1908 /
Le Coq-1912 consensus outlines (provenance per glyph in
`integration_report_p8.json`). Vertical placement derives from word-context
connector-band statistics (`placement_stats_p8.json`); horizontal metrics
follow the font's RTL join convention anchored on band-row ink. Join-stub
prolongations (logged per glyph) restore the printed baseline connection
where crop cuts removed it - letterform ink is never altered.

- Phase 1 Noto original preserved: `build/Uigurica-Regular.phase1-noto.ttf`
- GSUB/GPOS/GDEF/cmap/name/post/OS2 + hinting tables byte-identical to it
- 4 draft codepoints (U+10F84/85/87/89) retain Noto outlines; draft masters
  referenced, not merged (see coverage_gaps_74b.md)
- QA: qa/phase8_before_after.pdf, qa/phase8_specimen.png, qa/phase8_zoom.png,
  qa/phase8_join_audit.json (399 join pairs, 0 broken); validation PASS

## Phase 10 (2026-07-17): Metrics refinement & v1.000 release package

Engineering-only refinements; no glyph outline changed. Connector-run
advance inflation corrected for bethuyg.medi / memuyg.medi / tawuyg.medi /
wawuyg.medi by re-anchoring joined sides on the letter body + 45-unit stub
(pure translation + advance; metrics_refinement_p10.json). The four
draft-only codepoints stay draft after review (draft_review_p10.md - human
validation gate; no additional approved attestations exist). Version bumped
to 1.000 (name IDs 3/5, head.fontRevision; legacy Mac name records removed).

Production validation: OTS clean, fontbakery check-opentype 0 FAIL/0 WARN,
check-universal 0 FAIL, FreeType + HarfBuzz + Unicode conformance all pass;
join audit re-run 399/0 after refinement.

Release package: dist/ (Uigurica-Regular-v1.0.ttf, specimen_v1.pdf,
CHANGELOG.md, RELEASE_NOTES.md, FONTLOG.txt, LICENSE.txt, LICENSE_SUMMARY.md,
PROVENANCE.md, release_checklist.md, final_production_report_p10.json).
Readiness 86.3/100 - releasable v1.0 with documented hybrid-coverage limits.
