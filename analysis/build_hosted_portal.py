"""Assemble the read-only hosted portal in data/portal/hosted/ (private; deploy as a preview only).

    sh analysis/encode_hosted_media.sh            # audio/ and video/ (slow, once)
    cd portal-ui && VITE_HOSTED=1 npx vite build --outDir ../data/portal/hosted --emptyOutDir false
    python analysis/build_hosted_portal.py <site_repo_root>
    cd data/portal/hosted && vercel deploy --yes   # never --prod
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent
OUT = ROOT / "data" / "portal" / "hosted"
OUT.mkdir(parents=True, exist_ok=True)

data = (ROOT / "data" / "portal" / "portal.json").read_text()
(OUT / "portal.json").write_text(data)
n = 0
for url in sorted(set(re.findall(r'"(/(?:media|photos)/[^"]+)"', data))):
    src = ROOT / "data" / url[1:] if url.startswith("/media/") else SITE / url[1:]
    if src.exists():
        dst = OUT / url[1:]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
        n += 1
    else:
        print("missing", url)
shutil.copy(ROOT / "paper-latex" / "figures" / "tagged_2026-10-08.jpg", OUT / "tagged-2026-10-08.jpg")
(OUT / "vercel.json").write_text("""{
  "headers": [{ "source": "/(.*)", "headers": [
    { "key": "X-Robots-Tag", "value": "noindex, nofollow" },
    { "key": "Cache-Control", "value": "private, max-age=3600" }
  ]}]
}
""")
(OUT / ".vercelignore").write_text(".vercel/\n")
print(f"hosted portal: {n} images, portal.json, vercel.json")
