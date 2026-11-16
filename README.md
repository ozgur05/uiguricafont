# Uigurica (ugurica-regular)

![HarfBuzz Test Report](Pages-from-ugurica-regular-HarfBuzz-Test-Report.png)

A scholarly Unicode Old Uyghur font project reconstructing historical printed lead-type letterforms from primary philological editions into a modern, OpenType-compliant typeface.

---

## Overview

**Uigurica** is a digital typeface dedicated to the Old Uyghur script (*Unicode block `U+10F70`–`U+10F89`*). The letterform designs are reconstructed directly from the printed lead type cast and employed in Berlin for the seminal Turfan expedition publications:
- **F. W. K. Müller**, *Uigurica [I]* (Abhandlungen der Königlich Preussischen Akademie der Wissenschaften, Berlin, 1908).
- **Albert von Le Coq**, *Türkische Manichaica aus Chotscho I* (Abhandlungen der Kgl. Preuss. Akad. d. Wiss., Berlin, 1912).

The font couples historical typographic authenticity with full Unicode 14.0+ compliance and robust OpenType cursive shaping across modern operating systems, web browsers, and text-layout engines.

---

## Reconstruction Methodology

Unlike purely calligraphic or modernized interpretations, Uigurica adheres to a rigorous, multi-stage archaeological and metrological reconstruction pipeline:

```
[1200 DPI Scans] ──► [Component Detection] ──► [Sub-glyph Decomposition]
                                                        │
[Bézier Master Outlines] ◄── [Consensus Clustering] ◄───┘
          │                   (>=3 Attestations)
          ▼
[Connector Band Alignment] ──► [GSUB/GPOS Shaping] ──► [HarfBuzz & OTS Validation]
```

### 1. Primary Historical Evidence
- High-resolution, lossless 1200 DPI archival scans of original print plates from Müller (1908) and Le Coq (1912).
- The Berlin lead type represents the peak of European academic typographic punchcutting for Central Asian scripts, preserving authentic cursive ductus, ligature behaviors, and distinct letterform contrasts (such as *aleph* vs. *nun*, *beth* vs. *yodh*, and *samekh* vs. *shin*).

### 2. Unicode Standardization & Identity
- Script model is strictly aligned with the Unicode Standard and the formal encoding proposal **L2/20-191** (*Preliminary proposal for encoding Old Uyghur in Unicode* by Anshuman Pandey).
- Covers all 26 core script characters:
  - 18 Dual-joining and Right-joining letters (`U+10F70`–`U+10F81`).
  - 4 Combining diacritical marks (`U+10F82`–`U+10F85`).
  - 4 Punctuation signs (`U+10F86`–`U+10F89`).
  - Supplementary script controls: Arabic Tatweel (`U+0640`), Zero-Width Non-Joiner (`U+200C`), Dotted Circle (`U+25CC`), and Manichaean Double Dot (`U+10AF2`).

### 3. Computer Vision Harvesting & Quality Filtration
- Automated document layout analysis segments text lines and extracts connected ink components from the historical plates.
- Candidates undergo morphological filtering to exclude ink squashes, bleed-through, paper grain artifacts, and damaged metal punches.
- Sub-glyph decomposition isolates base stems, loops, terminals, and diacritics.

### 4. Consensus Clustering & Philological Validation
- Unsupervised feature clustering groups identical glyph occurrences across multiple pages.
- Every glyph candidate is verified through human-in-the-loop philological review interfaces (`review/*.html`).
- **Rule of Evidence:** No production outline is synthesized arbitrarily. Every master represents the median consensus of at least three independent, verified physical attestations.

### 5. Outline Reconstruction & Bézier Curve Fitting
- Multi-attestation sub-pixel alignment and edge averaging eliminate individual scan flaws while preserving the characteristic organic softness of ink on rag paper.
- Precise cubic Bézier curve fitting reproduces crisp vector contours.
- Join stubs cut by original punchcutters are normalized to ensure unbroken cursive continuity across words.

### 6. Cursive Joining & OpenType Shaping Model
- Full implementation of OpenType layout features:
  - `isol`: Isolated forms.
  - `init`: Initial positional forms.
  - `medi`: Medial positional forms.
  - `fina`: Final positional forms.
  - `rlig`: Required ligatures.
  - `mark` / `mkmk`: Accurate mark-to-base and mark-to-mark anchor positioning for diacritical dots.
- Right-joining behavior is strictly enforced for *Zayin* (`U+10F74`) and *Final Heth* (`U+10F75`), while all other letters participate in standard dual-joining connections.

### 7. Metrology & Quality Assurance
- **Connector Band Alignment:** Advances and sidebearings are mathematically normalized along the common horizontal ink axis to prevent baseline stepping.
- **Automated Join Audit:** Tested across 399 potential adjacent glyph pairs with 0 broken joins.
- **Sanitization & Conformance:** 
  - Verified clean with **OTS (OpenType Sanitizer)**.
  - 100% pass on **FontBakery** OpenType and Universal profile suites.
  - Full conformance testing against **HarfBuzz** and **FreeType**.

---

## Repository Structure

The repository is organized into dedicated functional directories:

```
uiguricafont/
├── ugurica-regular.ttf               # Production TrueType font (latest build)
├── Pages-from-ugurica-regular-HarfBuzz-Test-Report.png  # Test specimen preview
│
├── dist/                             # Release distribution packages
│   ├── ugurica-regular.ttf           # Distributable TTF binary
│   ├── ugurica-regular-HarfBuzz-Test-Report.pdf  # Comprehensive test report
│   ├── Uigurica-Regular-v1.0.ttf     # v1.0 milestone build
│   └── SHA256SUMS.txt                # Cryptographic checksums
│
├── docs/                             # Comprehensive project documentation
│   ├── BUILDING.md                   # Rebuild instructions and requirements
│   ├── CHANGELOG.md                  # Detailed version release notes
│   ├── FONTLOG.txt                   # Typographic change records
│   ├── PROVENANCE.md                 # Source scan provenance per glyph
│   ├── SOURCES.md                    # Historical source citations and rules
│   └── release_checklist.md          # Pre-flight quality gates
│
├── reports/                          # QA, validation & specimen reports
│   ├── ugurica-regular-HarfBuzz-Test-Report.pdf  # HarfBuzz rendering test report
│   ├── specimen_v1.pdf               # High-res typographic specimen book
│   ├── mapping_report.pdf            # Unicode-to-glyph mapping audit
│   ├── validation_report_phase9.pdf  # Phase 9 validation report
│   └── final_production_report_p10.json # Production metrics & pass counts
│
├── review/                           # Visual HTML review interfaces
│   ├── ambiguity_review.html         # Interactive ambiguity resolution tool
│   ├── harvest_review.html           # Müller crop inspection interface
│   ├── harvest_review_lecoq.html     # Le Coq crop inspection interface
│   └── review_mapping.html           # Glyph mapping verification table
│
├── data/                             # Pipeline datasets & metadata
│   ├── attestation/                  # Attestation counts & decision logs
│   ├── clusters/                     # Glyph clustering data & reports
│   ├── harvest/                      # Crop coordinates & harvest metadata
│   ├── mapping/                      # Canonical character-to-glyph mapping tables
│   └── pipeline/                     # Segment features & decomposition graphs
│
├── masters/                          # Verified consensus outlines (GLIF & SVG)
├── scans/                            # 1200 DPI source scans from Müller (1908)
├── tools/                            # Python pipeline & automation scripts
├── build/                            # Intermediate build artifacts
└── archive/                          # Historical archive bundles
```

---

## Usage

### Testing with HarfBuzz CLI

You can shape and render Old Uyghur text using `hb-view` and `hb-shape`:

```bash
# Render to PNG image:
hb-view ugurica-regular.ttf --text="𐰇𐽰𐽳𐽲𐽶𐽹𐽺𐽰𐽳" --font-size=48 --direction=rtl --script=ougr -o output.png

# Inspect OpenType glyph sequence and positions:
hb-shape ugurica-regular.ttf --text="𐰇𐽰𐽳𐽲𐽶𐽹𐽺𐽰𐽳" --direction=rtl --script=ougr
```

### Web Integration (CSS)

```css
@font-face {
  font-family: 'Uigurica';
  src: url('ugurica-regular.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
  font-display: swap;
}

.old-uyghur-text {
  font-family: 'Uigurica', serif;
  direction: rtl;
  font-size: 2rem;
  line-height: 1.6;
}
```

### Python Scripting

```python
import uharfbuzz as hb

with open("ugurica-regular.ttf", "rb") as font_file:
    font_data = font_file.read()

face = hb.Face(font_data)
font = hb.Font(face)
buffer = hb.Buffer()

buffer.add_str("𐽰𐽳𐽲𐽶𐽹")
buffer.guess_segment_properties()
hb.shape(font, buffer)

for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions):
    print(f"Glyph ID: {info.codepoint}, x_advance: {pos.x_advance}")
```

---

## Building from Source

To regenerate the font and run all validation suites:

```bash
# 1. Install prerequisites (Python 3.12+ recommended)
pip install fonttools skia-pathops opencv-python numpy pillow freetype-py uharfbuzz pymupdf fontbakery opentype-sanitizer

# 2. Rebuild masters and integrate into font
python tools/regenerate_masters_74b.py
python tools/placement_stats_p8.py
python tools/integrate_masters_p8.py
python tools/p10_metrics.py
python tools/p10_version.py

# 3. Execute quality assurance test suite
python tools/validate_p8.py
python tools/qa_phase8_joins.py
python tools/p10_production_validation.py
```

---

## License & Attribution

- **Letterform Design:** Reconstructed from original public-domain printed editions by F. W. K. Müller (1908) and Albert von Le Coq (1912).
- **Technical Base:** Derived from Noto Serif Old Uyghur (© 2022 The Noto Project Authors, licensed under the [SIL Open Font License, Version 1.1](https://scripts.sil.org/OFL)).
- In accordance with the OFL, this derivative project does not use the Reserved Font Name "Noto" — hence **Uigurica**.
