"""Probe skia-pathops union/simplify/op signatures."""
import pathops

p1 = pathops.Path()
pen = p1.getPen()
pen.moveTo((0, 0)); pen.lineTo((100, 0)); pen.lineTo((100, 100)); pen.lineTo((0, 100)); pen.closePath()
p2 = pathops.Path()
pen = p2.getPen()
pen.moveTo((80, 40)); pen.lineTo((180, 40)); pen.lineTo((180, 60)); pen.lineTo((80, 60)); pen.closePath()

r = pathops.op(p1, p2, pathops.PathOp.UNION, fix_winding=True)
print("op result type:", type(r), "bounds:", r.bounds)
try:
    r2 = pathops.simplify(p1, fix_winding=True, clockwise=True)
    print("simplify ok:", type(r2), r2.bounds, "clockwise contours:",
          [c.clockwise for c in r2.contours])
except Exception as e:
    print("simplify err:", e)
try:
    print("union sig test:", pathops.union.__doc__)
except Exception as e:
    print(e)
print("contains:", r.contains((50.0, 50.0)), r.contains((300.0, 300.0)))
