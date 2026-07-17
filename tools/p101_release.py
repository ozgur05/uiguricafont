"""Create the GitHub release for v1.0.0 and upload assets.

Token handling: obtained transiently from the git credential helper (the
same store the successful `git push` used). It is held in memory only,
never printed, never written to disk or any config/script.
"""
import json
import mimetypes
import os
import subprocess
import sys
import urllib.request

BASE = r"C:\Users\KutadguBilim\Font\Uigurica"
OWNER, REPO, TAG = "ozgur05", "uiguricafont", "v1.0.0"

out = subprocess.run(["git", "credential", "fill"],
                     input="protocol=https\nhost=github.com\n\n",
                     capture_output=True, text=True, cwd=BASE)
cred = dict(l.split("=", 1) for l in out.stdout.strip().splitlines() if "=" in l)
token = cred.get("password")
if not token:
    print("NO_TOKEN")
    sys.exit(1)

def api(url, data=None, method=None, ctype="application/json", raw=False):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read()) if not raw else r.read()

notes = open(os.path.join(BASE, "RELEASE_NOTES.md"), encoding="utf-8").read()
body = {
    "tag_name": TAG,
    "name": "Uigurica v1.0.0 — First production release",
    "body": notes + "\n\n---\nSHA-256 checksums: see attached SHA256SUMS.txt "
            "and final_production_report_p10.json.",
    "draft": False, "prerelease": False,
}
try:
    rel = api(f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
              json.dumps(body).encode())
except urllib.error.HTTPError as e:
    print("CREATE_FAIL", e.code, e.read()[:300])
    sys.exit(1)
print("release id", rel["id"], rel["html_url"])

ASSETS = ["Uigurica-Regular-v1.0.ttf", "specimen_v1.pdf", "CHANGELOG.md",
          "RELEASE_NOTES.md", "FONTLOG.txt", "LICENSE.txt", "PROVENANCE.md",
          "validation_report_phase9.pdf", "final_production_report_p10.json",
          "metrics_report_p10.json", "SHA256SUMS.txt"]
up = rel["upload_url"].split("{")[0]
for a in ASSETS:
    p = os.path.join(BASE, "dist", a)
    ct = mimetypes.guess_type(a)[0] or "application/octet-stream"
    if a.endswith(".ttf"):
        ct = "font/ttf"
    with open(p, "rb") as f:
        data = f.read()
    try:
        r = api(f"{up}?name={a}", data, ctype=ct)
        print("uploaded", a, f"({len(data)//1024} KB)")
    except urllib.error.HTTPError as e:
        print("UPLOAD_FAIL", a, e.code, e.read()[:200])
print("done:", rel["html_url"])
