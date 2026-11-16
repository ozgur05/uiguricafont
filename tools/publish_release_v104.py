import json
import mimetypes
import os
import subprocess
import sys
import urllib.request

REPO_DIR = r"D:\Font\geminifont\work\uiguricafont_remote"
OWNER, REPO, TAG = "ozgur05", "uiguricafont", "v1.0.4"

# Retrieve credential from git credential store
p = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True,
    text=True,
    cwd=REPO_DIR,
)
cred = dict(l.split("=", 1) for l in p.stdout.strip().splitlines() if "=" in l)
token = cred.get("password")
if not token:
    print("ERROR: No token found in git credential store.")
    sys.exit(1)

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def api_call(url, data=None, method=None, ctype="application/json"):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "UiguricaRelease/1.0.4")
    if data is not None:
        req.add_header("Content-Type", ctype)
    with opener.open(req) as r:
        return json.loads(r.read())

release_body = """## Uigurica v1.0.4 (ugurica-regular)

This release introduces the updated **ugurica-regular.ttf** production font build (Version 1.004) along with comprehensive **HarfBuzz OpenType shaping test reports** and repository architectural refactoring.

### Key Highlights of v1.0.4:
- **Production Font Build:** `ugurica-regular.ttf` (Version 1.004; ttfautohint v1.8.4.7).
- **HarfBuzz Conformance Test Report:** Full multi-page shaping audit proving complete cursive joining and glyph identity across the Old Uyghur Unicode repertoire (`ugurica-regular-HarfBuzz-Test-Report.pdf` and preview PNG).
- **OpenType Shaping:** Verified contextual form substitutions (`isol`, `init`, `medi`, `fina`), right-joining behavior for Zayin and Final Heth, and diacritical anchor attachments (`mark`, `mkmk`).
- **Repository Architecture:** Root workspace organized into designated directories (`docs/`, `reports/`, `review/`, `data/`, `masters/`, `scans/`, `dist/`).
- **Expanded Documentation:** Thorough reconstruction methodology documented in README.md detailing the 1200 DPI scan harvesting, consensus clustering (>=3 historical attestations), Bézier curve fitting, and metrological joining audits.

### Included Release Assets:
1. `ugurica-regular.ttf` — Primary TrueType font binary (v1.004).
2. `ugurica-regular-HarfBuzz-Test-Report.pdf` — Official HarfBuzz shaping test report.
3. `Pages-from-ugurica-regular-HarfBuzz-Test-Report.png` — High-resolution front-page test specimen preview.
4. `specimen_v1.pdf` — Full typographic specimen book.
5. `validation_report_phase9.pdf` — Technical validation report.
6. `Uigurica-Regular-v1.0.ttf` — Milestone v1.0 release build.
"""

payload = {
    "tag_name": TAG,
    "name": "Uigurica v1.0.4 — Production Font Build & HarfBuzz Conformance Suite",
    "body": release_body,
    "draft": False,
    "prerelease": False,
}

print(f"Creating GitHub Release for tag {TAG}...")
try:
    rel = api_call(f"https://api.github.com/repos/{OWNER}/{REPO}/releases", json.dumps(payload).encode("utf-8"))
    print(f"Release created successfully! URL: {rel.get('html_url')}")
    upload_url = rel["upload_url"].split("{")[0]
except urllib.error.HTTPError as e:
    err_msg = e.read().decode("utf-8", errors="ignore")
    print(f"Create failed: HTTP {e.code}: {err_msg[:300]}")
    # If release already exists, fetch it
    if e.code == 422:
        print("Checking if release already exists...")
        rel = api_call(f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}")
        upload_url = rel["upload_url"].split("{")[0]
        print(f"Found existing release at: {rel.get('html_url')}")
    else:
        sys.exit(1)

assets_to_upload = [
    (os.path.join(REPO_DIR, "ugurica-regular.ttf"), "ugurica-regular.ttf", "font/ttf"),
    (os.path.join(REPO_DIR, "reports", "ugurica-regular-HarfBuzz-Test-Report.pdf"), "ugurica-regular-HarfBuzz-Test-Report.pdf", "application/pdf"),
    (os.path.join(REPO_DIR, "Pages-from-ugurica-regular-HarfBuzz-Test-Report.png"), "Pages-from-ugurica-regular-HarfBuzz-Test-Report.png", "image/png"),
    (os.path.join(REPO_DIR, "dist", "Uigurica-Regular-v1.0.ttf"), "Uigurica-Regular-v1.0.ttf", "font/ttf"),
    (os.path.join(REPO_DIR, "reports", "specimen_v1.pdf"), "specimen_v1.pdf", "application/pdf"),
    (os.path.join(REPO_DIR, "reports", "validation_report_phase9.pdf"), "validation_report_phase9.pdf", "application/pdf"),
]

for file_path, asset_name, ctype in assets_to_upload:
    if not os.path.exists(file_path):
        print(f"Skipping (not found): {file_path}")
        continue
    size = os.path.getsize(file_path)
    print(f"Uploading {asset_name} ({size / 1024:.1f} KB)...")
    with open(file_path, "rb") as f:
        data = f.read()
    try:
        req = urllib.request.Request(f"{upload_url}?name={asset_name}", data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "UiguricaRelease/1.0.4")
        req.add_header("Content-Type", ctype)
        with opener.open(req) as r:
            res = json.loads(r.read())
            print(f"Uploaded: {asset_name} -> {res.get('browser_download_url')}")
    except urllib.error.HTTPError as e:
        print(f"Failed to upload {asset_name}: HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}")

print("\nAll assets processed!")
print(f"Release is live at: {rel.get('html_url')}")
