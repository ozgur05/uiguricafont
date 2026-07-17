"""Phase 8 exploration: metadata schemas needed for placement measurement."""
import json

h = json.load(open("harvest_report.json", encoding="utf-8"))
t = h["targets"][0]
print("muller target keys:", list(t.keys()))
print("muller cand sample:", json.dumps(t["candidates"][0], indent=1)[:500])
d = json.load(open("decomposition.json", encoding="utf-8"))
print("\ndecomp piece sample:", json.dumps(d["pieces"][0], indent=1)[:500])
s = json.load(open("segments.json", encoding="utf-8"))
print("\nsegment sample:", json.dumps(s[0], indent=1)[:500])
