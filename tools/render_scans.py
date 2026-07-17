"""Phase 2: render Uigurica I pages to lossless 1200-dpi PNGs.

The PDF has 10 pages corresponding to printed pages 36-45 of Mueller's
Uigurica I (verified: PDF page 9 carries the printed number 44).

Rendering is a plain rasterization of the page at 1200 dpi:
  - no sharpening, no filtering, no OCR, no enhancement
  - PNG output is lossless by definition
  - original page dimensions preserved (pixels = points/72 * 1200)
"""
import os

import fitz

PDF = r"C:\Users\KutadguBilim\Font\Uigurica.pdf"
OUT = r"C:\Users\KutadguBilim\Font\Uigurica\scans"
DPI = 1200
FIRST_PRINTED_PAGE = 36  # PDF page 1 == printed page 36

os.makedirs(OUT, exist_ok=True)
doc = fitz.open(PDF)
assert len(doc) == 10, f"expected 10 pages, got {len(doc)}"

for i, page in enumerate(doc):
    printed = FIRST_PRINTED_PAGE + i
    w_pt, h_pt = page.rect.width, page.rect.height
    pix = page.get_pixmap(dpi=DPI)  # direct raster, no post-processing
    path = os.path.join(OUT, f"page{printed}.png")
    pix.save(path)  # PyMuPDF writes PNG losslessly
    mb = os.path.getsize(path) / 1e6
    print(
        f"page{printed}.png  {pix.width}x{pix.height}px  "
        f"({w_pt:.1f}x{h_pt:.1f}pt = {w_pt/72:.2f}x{h_pt/72:.2f}in)  {mb:.1f} MB"
    )

print("OK")
