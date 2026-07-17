# Building Uigurica from this repository

A clean clone of this repository contains everything needed to rebuild the
released font. The pipeline is Python-only.

## Requirements

- Python 3.12+ with: `fonttools skia-pathops opencv-python numpy pillow
  freetype-py uharfbuzz pymupdf fontbakery opentype-sanitizer`
- Windows paths are hard-coded as `C:\Users\...\Font\Uigurica` in
  `tools/*.py` (`BASE` constant at the top of each script) — adjust `BASE`
  to your clone location.

## What is committed vs regenerable

Committed (sufficient to rebuild):
- `build/Uigurica-Regular.phase1-noto.ttf` — the Phase 1 technical base
  (Noto Serif Old Uyghur 1.004 with Uigurica naming); starting point of the
  build.
- `masters/` — validated consensus outlines (SVG + GLIF) with overlays.
- All human decision files: `mapping_table_validated.json`,
  `harvest_decisions.json`, `harvest_decisions_lecoq.json`.
- All pipeline metadata: `segments.json`, `decomposition.json`,
  `updated_clusters.json`, `harvest_report.json`,
  `harvest_lecoq_report.json`, `outline_report*.json`, `placement_stats_p8.json`.
- Harvested crops: `harvest/`, `harvest_lecoq/`, `harvest_lecoq_filtered/`,
  `glyphs/`, `segments/` (the scan's own ink — the design source).
- `scans/` — Müller 1908 page scans.

NOT committed (`.gitignore`), regenerable:
- `lecoq_scans/` (5.4 GB of 1200-dpi page renders): regenerated from the
  Le Coq 1912 PDF (see `SOURCES.md` for the public-domain source) by
  `tools/harvest_lecoq.py` (its render step). Only needed to re-run the
  Le Coq harvest from scratch; the committed crops already carry its results.

## Rebuild sequence (from the committed state)

```
python tools/regenerate_masters_74b.py   # masters from crops + decisions
python tools/placement_stats_p8.py       # word-context band statistics
python tools/integrate_masters_p8.py     # merge masters into the font
python tools/p10_metrics.py              # metrics refinement
python tools/p10_version.py              # version + name table -> v1.0 ttf
```

Validation (read-only):

```
python tools/validate_p8.py
python tools/qa_phase8_joins.py
python tools/p9_tables_outlines.py
python tools/p9_shaping.py
python tools/p9_metrics_render.py
python tools/p9_corpus.py
python tools/p10_production_validation.py
```

Packaging:

```
python tools/p10_specimen.py
python tools/p10_package.py
```

The result is `dist/Uigurica-Regular-v1.0.ttf` plus the documentation
package. Checksums for the released files are recorded in
`final_production_report_p10.json`.
