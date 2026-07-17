# Uigurica

A professional Unicode Old Uyghur font project based on the printed forms used by
F. W. K. Müller in *Uigurica I* (1908).

## Phase 1 — Technical foundation (current)

The font is a re-identified build of **Noto Serif Old Uyghur** (v1.004, "fixed" build,
SIL OFL 1.1). In this phase **no glyph outlines were changed** and **all OpenType
shaping behavior is preserved verbatim**. Only the font identity (name table,
fontRevision) differs from the source.

- Source font: `..\NotoSerifOldUyghur-fixed.ttf`
- Built font:  `build\Uigurica-Regular.ttf`
- Reference scans: `..\Uigurica.pdf` (Müller, *Uigurica I*)

### Preserved from the source (verified binary-identical)

| Table | Contents |
|---|---|
| `cmap` | 352 codepoints, incl. 26 Old Uyghur (U+10F70–U+10F89), U+0640 tatweel, U+200C ZWNJ, U+25CC, U+10AF2 |
| `GSUB` | scripts DFLT/cyrl/grek/latn/**ougr**; features aalt, ccmp, dlig, **init/medi/fina**, locl, ordn, rclt, rlig, salt; 18 lookups |
| `GPOS` | abvm, blwm, dist, kern, mark, mkmk; 10 lookups |
| `GDEF` | glyph classes (258 base / 1 lig / 18 mark), ligature carets |
| `glyf`/`loca`/`hmtx` | 428 glyphs, outlines and metrics untouched |
| `cvt/fpgm/prep/gasp` | ttfautohint hinting untouched |

## Layout

```
Uigurica/
├── build/
│   └── Uigurica-Regular.ttf      # output font
├── extracted/                     # TTX dumps of the source font
│   ├── cmap.ttx  GSUB.ttx  GPOS.ttx  GDEF.ttx  GlyphOrder.ttx
│   ├── NotoSerifOldUyghur-fixed.full.ttx
│   ├── cmap_summary.txt           # U+XXXX -> glyph name
│   └── glyph_order.txt            # index -> glyph name
└── tools/
    ├── analyze.py                 # inspect source font structure
    ├── extract_tables.py          # dump tables to extracted/
    ├── build.py                   # build Uigurica-Regular.ttf
    └── verify.py                  # verify build against source (exit 1 on any diff)
```

## Rebuild

```
python tools/extract_tables.py
python tools/build.py
python tools/verify.py
```

Requires Python with `fonttools` (tested with 4.63.0).

## Next phases (planned)

- Phase 2: redesign glyph outlines to match Müller's printed forms in *Uigurica I*.

## License

Derived from Noto Serif Old Uyghur, © 2022 The Noto Project Authors
(https://github.com/notofonts/old-uyghur), SIL Open Font License 1.1.
Derivative works must not use the reserved font name "Noto" — hence "Uigurica".
