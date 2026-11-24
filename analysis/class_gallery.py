"""Whole-class views for the professor: one tile per enrolled student, plus the room.

    python analysis/class_gallery.py <session_dir> <section> <repo_root>

Per student: best in-class face crop (highest-confidence match), seconds on camera
(faces followed through each shot, matched at 0.50), first and last seen. Students never
seen get their roster photo, marked not seen. Room views: for each camera preset that shows
students, the frame with the most faces, and a stitched panorama when the views overlap.
Writes into <session_dir>/class_view/: tiles/*.jpg, rooms/*.jpg, panorama.jpg, class.json.
"""
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sess, section, repo = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
out = sess / "class_view"
(out / "tiles").mkdir(parents=True, exist_ok=True)
(out / "rooms").mkdir(parents=True, exist_ok=True)
slug = lambda n: re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

g = np.load(sess / "gallery.npz")
G, names, sec = g["emb"], [str(n) for n in g["names"]], g["sections"]
f = np.load(sess / "faces.npz")
t, box, E = f["t"], f["box"], f["emb"]

# Follow faces through shots (same seat, next second), match each track's average face.
by_t = defaultdict(list)
for k in np.argsort(t, kind="stable"):
    by_t[float(t[k])].append(int(k))


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i) if i else 0.0


tracks, prev = [], []
for T in sorted(by_t):
    cur = []
    for k in by_t[T]:
        best = max((tr for tr in prev if T - float(t[tr[-1]]) <= 1.01), key=lambda tr: iou(box[k], box[tr[-1]]), default=None)
        if best is not None and iou(box[k], box[best[-1]]) >= 0.4 and best not in cur:
            best.append(k); cur.append(best)
        else:
            tracks.append([k]); cur.append(tracks[-1])
    prev = cur

seen = defaultdict(set)          # student -> seconds on camera
best_face = {}                   # student -> (score, face index)
for tr in tracks:
    c = E[tr].mean(0); c /= np.linalg.norm(c)
    s = G @ c
    o = np.argsort(-s)[:2]
    if s[o[0]] < 0.50 or s[o[0]] - s[o[1]] < 0.05:
        continue
    p = int(o[0])
    for k in tr:
        seen[p].add(float(t[k]))
        sk = float(E[k] @ G[p])
        if sk > best_face.get(p, (-1, None))[0]:
            best_face[p] = (sk, k)

# Single confident frames count too: a student seen for one second in a shot is still seen.
for k in range(len(t)):
    s = G @ E[k]
    o = np.argsort(-s)[:2]
    if s[o[0]] >= 0.50 and s[o[0]] - s[o[1]] >= 0.05:
        p = int(o[0])
        seen[p].add(float(t[k]))
        if s[o[0]] > best_face.get(p, (-1, None))[0]:
            best_face[p] = (float(s[o[0]]), k)

cap = cv2.VideoCapture(str(sess / "camera.mp4"))
H, W = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))


def frame_at(T):
    cap.set(cv2.CAP_PROP_POS_MSEC, T * 1000)
    ok, img = cap.read()
    return img if ok else None


fmt = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
students = []
for p, n in sorted(((i, n) for i, n in enumerate(names) if sec[i] == section), key=lambda x: x[1]):
    rec = {"name": n, "slug": slug(n), "seen_seconds": len(seen.get(p, ())), "tile": f"tiles/{slug(n)}.jpg"}
    if p in best_face:
        sc, k = best_face[p]
        img = frame_at(float(t[k]))
        x, y, w, h = [int(v) for v in box[k]]
        pad = int(max(w, h) * 0.6)
        crop = img[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)]
        crop = cv2.resize(crop, (240, int(240 * crop.shape[0] / crop.shape[1])))
        cv2.imwrite(str(out / rec["tile"]), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        ts = sorted(seen[p])
        rec.update({"seen": True, "best_score": round(sc, 3), "first_seen": fmt(ts[0]), "last_seen": fmt(ts[-1])})
    else:
        shutil.copy(repo / "photos/2028" / f"{slug(n)}.jpg", out / rec["tile"])
        rec.update({"seen": False})
    students.append(rec)

# Room views: the busiest frame of each camera preset that shows students.
rooms = []
shots = json.loads((sess / "shots.json").read_text())["shots"]
per_t = Counter(t.tolist())
by_preset = defaultdict(list)
for s in shots:
    if s["crowd"]:
        by_preset[s["preset"]].append(s)
imgs = []
for pr, ss in sorted(by_preset.items()):
    cand = [(per_t.get(float(T), 0), T) for s in ss for T in range(int(s["start"]) + 1, int(s["end"]))]
    if not cand:
        continue
    n_faces, T = max(cand)
    if n_faces < 5:
        continue  # front-of-room shot (presenter, a few people at the screen), not the class
    img = frame_at(float(T))
    if img is None:
        continue
    name = f"rooms/preset-{pr}.jpg"
    cv2.imwrite(str(out / name), cv2.resize(img, (960, 540)), [cv2.IMWRITE_JPEG_QUALITY, 85])
    rooms.append({"preset": pr, "time": fmt(T), "faces": n_faces, "image": name})
    imgs.append(cv2.resize(img, (1280, 720)))
cap.release()

pano = None
if len(imgs) >= 2:
    # Only confident stitches: the camera shoots presets at different pan and zoom, and a
    # forced stitch comes out warped or upside down. Views it can't join stay in the grid.
    st = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
    status, pan = st.stitch(imgs)
    if status == cv2.Stitcher_OK and pan.shape[0] >= 300 and pan.shape[1] >= 1.5 * pan.shape[0]:
        cv2.imwrite(str(out / "panorama.jpg"), pan, [cv2.IMWRITE_JPEG_QUALITY, 85])
        pano = "panorama.jpg"
        res_used = [rooms[i]["preset"] for i in st.component()]
        for r in rooms:
            r["in_panorama"] = r["preset"] in res_used
    else:
        print("panorama: views don't overlap enough to stitch (status", status, ")")

res = {"section": section, "enrolled": len(students), "seen": sum(s["seen"] for s in students),
       "students": students, "rooms": rooms, "panorama": pano}
(out / "class.json").write_text(json.dumps(res, indent=1))
print(f"{res['seen']} of {res['enrolled']} seen; {len(rooms)} room views; panorama: {bool(pano)}")
