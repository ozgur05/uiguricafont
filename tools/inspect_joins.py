"""Phase 8 exploration: joining-edge geometry and cmap of the Noto base."""
from fontTools.ttLib import TTFont

tt = TTFont(r"C:\Users\KutadguBilim\Font\Uigurica\build\Uigurica-Regular.ttf")
glyf = tt["glyf"]
for name in ["bethuyg.medi", "wawuyg.medi", "shinuyg.medi", "bethuyg.init",
             "kaphuyg.fina", "zayinuyg.fina"]:
    g = glyf[name]
    coords, ends, flags = g.getCoordinates(glyf)
    mx = max(x for x, y in coords)
    print(name)
    print("  left :", sorted(c for c in coords if c[0] < 12)[:8])
    print("  right:", sorted(c for c in coords if c[0] > mx - 15)[:8])
cmap = tt.getBestCmap()
for k in range(0x10F70, 0x10F8A):
    if k in cmap:
        print(hex(k), cmap[k])
