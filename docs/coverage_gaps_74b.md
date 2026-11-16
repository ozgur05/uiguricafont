# Coverage gaps after Phase 7.4b (2026-07-17)

Status per `coverage_ledger.json`: **22 of 26 codepoints production-covered**
(>= 3 attestations), 0 missing, 0 ambiguous-pending. The 4 remaining are
draft-only, each with a master built from human-approved scan ink but fewer
than the 3 attestations required for production status:

| Codepoint | Name | Approved attestations | Why short |
|---|---|---|---|
| U+10F84 | TWO DOTS ABOVE | 1 (Le Coq) | 40 machine candidates offered; reviewer confirmed only 1 as a genuine two-dot-above mark — most were letter-teeth fragments |
| U+10F85 | TWO DOTS BELOW | 2 (Le Coq) | same: 40 offered, 2 genuine |
| U+10F87 | TWO BARS | 2 (Le Coq) | 12 offered after hi-res gate; the transliteration column produced most matches (Latin "gr/qr" shapes), 2 genuine |
| U+10F89 | FOUR DOTS | 1 (Le Coq) | 25 offered; four-dot section marks are rare in both printings |

Both sources are exhausted at the current thresholds: Müller pp. 36–45
(Phase 7.2, NCC 0.52) and Le Coq pp. 4–21 + 46–57 (Phase 7.2b, hi-res
re-scored) have been swept and human-reviewed. These four signs are simply
rare in the printed corpus.

Paths to close (in preference order):
1. Re-review: `harvest_review_lecoq.html` still lists every gated candidate
   for these targets; approving 1–2 more genuine instances per sign flips it
   to production (drop the new picks into `harvest_decisions_lecoq.json` and
   rerun `tools/regenerate_masters_74b.py` + `tools/update_ledger.py`).
2. Sweep the unrendered Le Coq text pages 22–37 (referenced by the index but
   not yet rasterized) for punctuation only.
3. Accept the draft masters for Phase 8 with a documented single/double-
   attestation caveat — they are real scan ink, just thinly attested. The
   dot-based signs are geometrically simple, so the risk of a wrong
   letterform is low.

Known cosmetic issue for Phase 8: `harvest_bethuyg_init` carries two small
stray contours (neighboring-letter ink) at its right edge; visible in
`masters/overlays_harvest.pdf`. Fix by rejecting the offending crop(s) in
review or by dropping the stray contours during font integration — never by
editing the consensus bitmap.
