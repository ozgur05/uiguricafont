# Draft codepoint review — Phase 10 (2026-07-17)

Task 2 of Phase 10: determine whether additional **validated** attestations
already exist for the four draft-only codepoints, promote if ≥3, else retain
as draft with a documented reason.

## Finding: no additional validated attestations exist — all four stay DRAFT

| Codepoint | Glyph | Human-approved attestations | Machine candidates offered | Verdict |
|---|---|---|---|---|
| U+10F84 | twodotsaboveuyg | 1 | 40 | DRAFT (need ≥3) |
| U+10F85 | twodotsbelowuyg | 2 | 40 | DRAFT (need ≥3) |
| U+10F87 | PunctuationTwoBars | 2 | 12 | DRAFT (need ≥3) |
| U+10F89 | PunctuationFourDots | 1 | 25 | DRAFT (need ≥3) |

The Le Coq harvest already surfaced 12–40 machine candidates for each of
these targets (Phase 7.2b), and the human reviewer examined that sheet and
approved only the counts above. The gap between "offered" and "approved" is
not a coverage gap the pipeline can close by searching harder — it is the
reviewer's judgment that the remaining candidates are false positives
(letter-teeth fragments read as two-dot marks, Latin "gr/qr" from the
transliteration column read as two-bars, a Latin loop read as four-dots; see
qa/lecoq_qa4.png). Promoting on machine candidates alone would violate the
project's binding rule that **human validation is the sole promotion gate**
and would inject unverified ink into production masters.

No promotion is performed. The font retains the existing (Noto) outlines for
these four codepoints, exactly as after Phase 8, and the draft consensus
masters remain attached as references in outline_report_74.json /
integration_report_p8.json.

## Path to promotion (out of scope for this validation-only phase)
1. Re-open `harvest_review_lecoq.html`, approve ≥1–2 more genuine instances
   per sign → append to `harvest_decisions_lecoq.json` → rerun
   `regenerate_masters_74b.py` + `integrate_masters_p8.py`.
2. Or harvest Le Coq text pages 22–37 (referenced by the index, not yet
   rasterized) for punctuation only — these signs are rare in headword
   position but appear as line/section marks in running text.

These are genuinely rare marks in a 34-page corpus; scarcity — not pipeline
capability — is the limiter.
