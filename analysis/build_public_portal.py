"""Build the public, de-identified portal in data/portal/public/ (safe to publish).

    python analysis/build_public_portal.py <site_repo_root>
    cd portal-ui && VITE_HOSTED=1 VITE_PUBLIC=1 npx vite build --outDir ../data/portal/public --emptyOutDir false

Students get pseudonyms (with their paper id, e.g. "Maya Chen (S24)") and an initials badge instead of a headshot;
in-class faces, camera views and the panorama are blurred; transcript and comment text become placeholders with time and length; the course,
section and instructor are generalised; there is no audio or video. The build fails if any real name from the
four-section gallery, the instructor's name or the course code survives anywhere in the output.
"""
import json
import re
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402
from pseudonyms import load  # noqa: E402

SITE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "haas-2028-vercel"
OUT = ROOT / "data" / "portal" / "public"
# Start clean but keep the Vercel link (.vercel/), so a deploy never lands in a new, unintended project.
OUT.mkdir(parents=True, exist_ok=True)
for p in OUT.iterdir():
    if p.name not in (".vercel", ".env.local"):
        shutil.rmtree(p) if p.is_dir() else p.unlink()
(OUT / "img").mkdir()
P, sid, fake = load()
back = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=12)
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
pid = {n: slug(fake[n]) for n in fake}
show = {n: f"{fake[n]} ({sid[n]})" for n in fake}
SECTION, COURSE = "Section A", "Core MBA course: leading people"
dates = [s["date"] for s in P["sessions"]]
sess_key = {s["id"]: f"class-{i + 1}" for i, s in enumerate(P["sessions"])}


def soft_face(path, out, size=160):
    """A headshot or in-class face, blurred so it reads as a person but not as anyone in particular."""
    img = cv2.imread(str(path))
    if img is None:
        return None
    img = cv2.resize(img, (size, int(img.shape[0] * size / img.shape[1])))
    img = cv2.GaussianBlur(img, (0, 0), size / 10)
    cv2.imwrite(str(OUT / "img" / out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return f"/img/{out}"


def soft_scene(path, out, width=1280):
    """A classroom still: whole frame softened (no readable name cards), every detected face blurred hard."""
    img = cv2.imread(str(path))
    if img is None:
        return None
    faces = back.faces(img)
    img = cv2.GaussianBlur(img, (0, 0), max(1.6, img.shape[1] / 450))
    for f in faces:
        x, y, w, h = [max(0, int(v)) for v in f.box]
        pad = int(0.35 * max(w, h))
        y0, y1, x0, x1 = max(0, y - pad), y + h + pad, max(0, x - pad), x + w + pad
        img[y0:y1, x0:x1] = cv2.GaussianBlur(img[y0:y1, x0:x1], (0, 0), max(8, w / 3))
    img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])))
    cv2.imwrite(str(OUT / "img" / out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return f"/img/{out}"


def local(url):
    return (ROOT / "data" / url[1:]) if url.startswith("/media/") else (SITE / url[1:])


def who(name):
    return show.get(name, "Unknown student") if name else name


def secs(a, b):
    return f"{max(1, round(b - a))} s"


TINTS = ["#dfe9e2", "#f3e6c4", "#e3def5", "#f4dcd9", "#dde7f3", "#ece6dc"]


def badge(n):
    """Initials on a soft tint in place of a headshot: headshots are what classmates recognise first."""
    first, last = fake[n].split()[0], fake[n].split()[-1]
    tint = TINTS[int(sid[n][1:]) % len(TINTS)]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">'
           f'<rect width="160" height="160" fill="{tint}"/><text x="80" y="96" text-anchor="middle" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="52" font-weight="600" fill="#3a3a36">{first[0]}{last[0]}</text></svg>')
    (OUT / "img" / f"photo-{pid[n]}.svg").write_text(svg)
    return f"/img/photo-{pid[n]}.svg"


# Roster
roster = []
for r in P["roster"]:
    n = r["name"]
    att = {}
    for d, a in r["attendance"].items():
        a = dict(a)
        if a.get("tile"):
            a["tile"] = soft_face(local(a["tile"]), f"face-{pid[n]}-{d}.jpg", 120)
        att[d] = a
    roster.append({**r, "id": pid[n], "name": show[n], "team": None, "photo": badge(n), "attendance": att})

# Sessions: images blurred, calls without words
sessions = []
for s in P["sessions"]:
    k = sess_key[s["id"]]
    rooms = [{**rm, "image": soft_scene(local(rm["image"]), f"{k}-view-{rm['preset']}.jpg", 960)} for rm in s["rooms"]]
    calls = [{**c, "student": who(c["student"]), "student_id": pid.get(c["student"]), "text": "(instructor calls on this student)"} for c in s["calls"]]
    sessions.append({**s, "id": k, "rooms": rooms, "calls": calls, "panorama": soft_scene(local(s["panorama"]), f"{k}-panorama.jpg", 2000) if s.get("panorama") else None})

comments = [{**c, "student": who(c["student"]), "student_id": pid.get(c["student"]), "text": f"(student comment, {secs(c['start'], c['end'])}; text withheld in the public edition)"} for c in P["comments"]]


def turn_text(t):
    if t["role"] == "preclass":
        return "(before class)"
    if t["role"] == "short":
        return "…"
    return f"({'instructor' if t['role'] == 'professor' else 'student'} speaking, {secs(t['start'], t['end'])})"


transcripts = {d: [{**t, "speaker": who(t["speaker"]) if t["speaker"] else None, "text": turn_text(t)} for t in rows] for d, rows in P["transcripts"].items()}
placeholder = lambda c: {**c, "text": f"(clip, {secs(c['start'], c['end'])})"}
voices = {**P["voices"],
          "learned": [{**v, "student": who(v["student"]), "student_id": pid[v["student"]], "samples": [placeholder(x) for x in v["samples"]]} for v in P["voices"]["learned"]],
          "unknown": [{**u, "clips": [placeholder(x) for x in u.get("clips", [])],
                       "suggestion": ({**u["suggestion"], "student": who(u["suggestion"]["student"]), "student_id": pid[u["suggestion"]["student"]]} if u.get("suggestion") else None)}
                      for u in P["voices"]["unknown"]]}
pub = {**P, "section": SECTION, "course": COURSE, "professor": "Instructor", "roster": roster, "sessions": sessions,
       "comments": comments, "transcripts": transcripts, "voices": voices}
text = json.dumps(pub, ensure_ascii=False)

# Nothing identifying may survive: real names (all four sections), the instructor, the course code, original paths.
real = {str(x) for x in np.load(ROOT / "data" / "media" / "2026-10-08-core-section-a" / "gallery.npz")["names"]}
banned = {p for n in real for p in n.split() if len(p) > 2} | {"Instructor", "SectionA", "core", "the core course", "/photos/2028", "/media/"}
allowed = {p for v in fake.values() for p in v.split()}
leaks = sorted(b for b in banned - allowed if re.search(r"(?<![A-Za-z])" + re.escape(b) + r"(?![A-Za-z])", text))
if leaks:
    raise SystemExit(f"public portal would leak: {leaks[:20]}")
(OUT / "portal.json").write_text(text)
(OUT / "vercel.json").write_text(json.dumps({"headers": [{"source": "/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=600"}]}]}, indent=2))
(OUT / ".vercelignore").write_text(".vercel/\n.env.local\n")
print(f"public portal: {len(roster)} students, {len(list((OUT / 'img').iterdir()))} images, no leaks")
