# Changelog

## v1.0.0 - 2026-07-17  (font-internal version 1.000)
First public release.

### Added
- 39 production glyph outlines redrawn from the printed metal type of
  Mueller, *Uigurica I* (1908) and Le Coq, *Tuerkische Manichaica I* (1912),
  replacing the Noto Serif Old Uyghur base outlines for those glyphs.
- Full contextual coverage (isolated/initial/medial/final) for BETH,
  GIMEL-HETH, KAPH and SHIN.
- 22 of 26 Old Uyghur codepoints production-covered.

### Changed
- Metrics refinement (v1.000): re-anchored joining advances for
  bethuyg.medi, memuyg.medi, tawuyg.medi and wawuyg.medi to remove
  connector-run inflation (translation + advance only; no outline change).
- Version 0.100 -> 1.000; name IDs 3/5 and head.fontRevision updated.

### Retained as draft (Noto outline kept)
- U+10F84 TWO DOTS ABOVE, U+10F85 TWO DOTS BELOW, U+10F87 TWO BARS,
  U+10F89 FOUR DOTS - insufficient validated attestations (<3).

### Unchanged
- All OpenType layout (GSUB/GPOS/GDEF), cmap, and hinting tables are
  byte-identical to the Noto Serif Old Uyghur technical base.
