"""Index every face in a session's camera video against the class gallery, once.

    python analysis/index_faces.py <session_dir> <repo_root> [every_s]

Gallery: the site's seating-chart headshots (photos/2028), section from build/data/cohorts.json.
Writes into <session_dir> (under data/, never committed):
    gallery.npz   names, sections, emb (L2-normalised SFace)
    faces.npz     t, box[x,y,w,h], emb, best_idx, best, second   for every face >= 24 px
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classroom.attendance import sample_video  # noqa: E402
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402

sess, repo = Path(sys.argv[1]), Path(sys.argv[2])
every = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
backend = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=24)

slug = lambda n: re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
cohorts = json.loads((repo / "build/data/cohorts.json").read_text())
by_slug = {slug(n): (n, c) for n, c in cohorts.items()}
names, sections, gal = [], [], []
for f in sorted((repo / "photos/2028").glob("*.jpg")):
    if f.stem not in by_slug:
        continue
    img = cv2.copyMakeBorder(cv2.imread(str(f)), 40, 40, 40, 40, cv2.BORDER_REPLICATE)
    faces = backend.faces(img)
    if len(faces) != 1:
        continue
    n, c = by_slug[f.stem]
    names.append(n); sections.append(c)
    gal.append(faces[0].embedding / np.linalg.norm(faces[0].embedding))
G = np.stack(gal)
np.savez(sess / "gallery.npz", names=np.array(names), sections=np.array(sections), emb=G)
print(f"gallery {len(names)}", flush=True)

T, B, E, BI, BS, SS = [], [], [], [], [], []
for t, img in sample_video(str(sess / "camera.mp4"), every):
    for f in backend.faces(img):
        e = f.embedding / np.linalg.norm(f.embedding)
        sims = G @ e
        o = np.argsort(-sims)[:2]
        T.append(t); B.append(f.box); E.append(e); BI.append(o[0]); BS.append(sims[o[0]]); SS.append(sims[o[1]])
np.savez(sess / "faces.npz", t=np.array(T), box=np.array(B), emb=np.array(E, dtype=np.float32),
         best_idx=np.array(BI), best=np.array(BS), second=np.array(SS))
print(f"{len(T)} faces indexed", flush=True)
