"""Attendance in about a minute: look once per camera shot, not once per second.

    python analysis/fast_attendance.py <session_dir> <section> [frames_per_shot]

1. One low-resolution pass (1 frame/s, 160x90 grey) finds camera moves -> shots.
2. One frame from the middle of each shot, at 640 px, counts faces -> which shots show the class.
3. In each class shot, the `frames_per_shot` frames spread through it are read at full
   resolution and every face is matched to the gallery (0.50 with margin).
Prints timings for each step and the students named; compare with faces.npz's full result.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402

sess, section = Path(sys.argv[1]), sys.argv[2]
per_shot = int(sys.argv[3]) if len(sys.argv) > 3 else 3
video = str(sess / "camera.mp4")
g = np.load(sess / "gallery.npz")
G, sec = g["emb"], g["sections"]
T = {}

t0 = time.time()
raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", video, "-vf", "fps=1,scale=160:90,format=gray",
                      "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.int16)
frac = np.r_[1.0, (np.abs(np.diff(fr, axis=0)) > 18).mean(axis=(1, 2))]
cuts = [0] + [i for i in range(1, len(fr)) if frac[i] > 0.3] + [len(fr)]
shots = [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b - a >= 2]
T["find_shots_s"] = round(time.time() - t0, 1)

t1 = time.time()
fast = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=12)
full = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=24)
cap = cv2.VideoCapture(video)


def read(sec_):
    cap.set(cv2.CAP_PROP_POS_MSEC, sec_ * 1000)
    ok, img = cap.read()
    return img if ok else None


class_shots = []
for a, b in shots:
    img = read((a + b) / 2)
    if img is None:
        continue
    small = cv2.resize(img, (640, int(640 * img.shape[0] / img.shape[1])))
    if len(fast.faces(small)) >= 3:
        class_shots.append((a, b))
T["pick_class_shots_s"] = round(time.time() - t1, 1)

t2 = time.time()
named = set()
wrong = set()
frames = 0
for a, b in class_shots:
    for x in np.linspace(a, b, per_shot + 2)[1:-1]:
        img = read(float(x))
        if img is None:
            continue
        frames += 1
        for f in full.faces(img):
            s = G @ (f.embedding / np.linalg.norm(f.embedding))
            o = np.argsort(-s)[:2]
            if s[o[0]] >= 0.50 and s[o[0]] - s[o[1]] >= 0.05:
                (named if sec[o[0]] == section else wrong).add(int(o[0]))
T["match_faces_s"] = round(time.time() - t2, 1)
cap.release()

ref = np.load(sess / "faces.npz")
ok = (ref["best"] >= 0.50) & ((ref["best"] - ref["second"]) >= 0.05)
ref_named = {int(i) for i in ref["best_idx"][ok] if sec[int(i)] == section}
res = {"shots": len(shots), "class_shots": len(class_shots), "frames_matched": frames, **T,
       "total_s": round(sum(T.values()), 1), "students_named": len(named), "wrong_section": len(wrong),
       "full_1fps_named": len(ref_named), "found_by_both": len(named & ref_named),
       "only_fast": len(named - ref_named), "missed_vs_full": len(ref_named - named)}
print(json.dumps(res, indent=2))
