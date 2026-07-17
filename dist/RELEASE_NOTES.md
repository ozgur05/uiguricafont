# Uigurica v1.0.0 - Release Notes

Release tag: v1.0.0 (Semantic Versioning). Font-internal version: 1.000
(OpenType head.fontRevision / name ID 5).

Uigurica is a Unicode Old Uyghur typeface whose letterforms are reconstructed
from early-20th-century printed metal type rather than digitised from a modern
design. Version 1.000 ships 39 glyphs on consensus outlines measured
from multiple attestations in Mueller (1908) and Le Coq (1912).

## Fidelity
Against the original print scans, on 27 fully human-validated words, Uigurica
reaches median IoU 0.555 and ink coverage
0.805, versus 0.285
/ 0.347 for the Noto base - roughly twice as
close to the source, and closer on 22 of 27
words.

## Production validation - ALL GATES PASS
- OpenType Sanitizer (OTS): File sanitized successfully!
- fontbakery check-universal: 0 FAIL, 0 FATAL (82 PASS)
- fontbakery check-opentype: 0 FAIL (35 PASS)
- FreeType: all cmapped codepoints render at 8-64 px
- HarfBuzz: all 26 codepoints shape, no .notdef; contextual/right-joining/
  ligature/mark behaviour intact
- Unicode: U+10F70-10F89 fully mapped; combining marks carry GDEF mark class

## Known limitations
- Hybrid font: 60 Old-Uyghur glyphs (incl. 20
  ligatures and contextual forms without production masters) still use Noto
  outlines - a slight weight difference is visible in mixed text.
- 4 draft codepoints keep Noto outlines (see above).
- memuyg.fina / peuyg.fina counters close below ~36 px (faithful to the tight
  metal-type counters).

## Provenance & licence
Glyph designs: public-domain print sources (1908, 1912). Technical base and
this release: SIL Open Font License 1.1. See PROVENANCE.md and LICENSE.
