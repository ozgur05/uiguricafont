"""Phase 8 exploration: pathops API surface + GLIF parse sanity."""
import pathops
from fontTools.ufoLib.glifLib import readGlyphFromString
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.pointPen import SegmentToPointPen

print("pathops members:", [m for m in dir(pathops) if not m.startswith("_")])
p = pathops.Path()
print("Path members:", [m for m in dir(p) if not m.startswith("_")])

class GObj:
    pass

g = GObj()
src = open(r"C:\Users\KutadguBilim\Font\Uigurica\masters\glif\harvest_bethuyg_medi.glif", encoding="utf-8").read()
pen = RecordingPen()
readGlyphFromString(src, g, SegmentToPointPen(pen))
print("advance:", getattr(g, "width", None))
ops = [v[0] for v in pen.value]
print("n ops:", len(pen.value), "op kinds:", sorted(set(ops)))
xs = [pt[0] for op, args in pen.value for seg in args for pt in ([seg] if isinstance(seg[0], (int, float)) else seg)] if False else None
# bbox via flattening
from fontTools.pens.boundsPen import BoundsPen
bp = BoundsPen(None)
pen.replay(bp)
print("bounds:", bp.bounds)
