"""Camera moves and preset positions, from a fast low-resolution pass over the video.

    python analysis/shots.py <session_dir>

ffmpeg decodes the whole video once at 4 frames a second and 160x90 grey (no seeking), which
is far faster than jumping around the file. A camera move shows as a burst of frame-to-frame
change; between moves the camera holds a "shot". Shots are grouped into presets by how alike
their middle frames look. Writes shots.json:
    {"moves": [t...], "shots": [{"start","end","preset","crowd"}], "presets": n, "decode_s": ...}
"""
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

sess = Path(sys.argv[1])
FPS, W, H = 4, 160, 90
t0 = time.time()
proc = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(sess / "camera.mp4"),
                       "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                      capture_output=True, check=True)
frames = np.frombuffer(proc.stdout, np.uint8).reshape(-1, H, W).astype(np.float32)
decode_s = time.time() - t0
n = len(frames)
diff = np.r_[0, np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))]
# A move: change well above the scene's normal flicker (people shifting in their seats).
thr = max(6.0, float(np.percentile(diff, 90)) * 2)
moving = diff > thr
# Merge moving frames into move events; a shot is a still stretch of 2 s or more.
shots, moves = [], []
start = None
i = 0
while i < n:
    if moving[i]:
        j = i
        while j + 1 < n and (moving[j + 1] or (j + 2 < n and moving[j + 2])):
            j += 1
        moves.append(round(i / FPS, 2))
        if start is not None and i - start >= 2 * FPS:
            shots.append([start, i])
        start = j + 1
        i = j + 1
    else:
        if start is None:
            start = i
        i += 1
if start is not None and n - start >= 2 * FPS:
    shots.append([start, n])

thumbs = np.stack([frames[(a + b) // 2].ravel() for a, b in shots])
thumbs = (thumbs - thumbs.mean(1, keepdims=True)) / (thumbs.std(1, keepdims=True) + 1e-6)
# A blank frame (black or one flat colour) has no variation, which correlation can't handle.
thumbs += np.random.default_rng(0).normal(0, 1e-3, thumbs.shape)
lab = fcluster(linkage(thumbs, "average", metric="correlation"), t=0.25, criterion="distance")

faces = np.load(sess / "faces.npz")
per_t = Counter(faces["t"].tolist())
out = []
for (a, b), p in zip(shots, lab):
    s, e = a / FPS, b / FPS
    secs = [t for t in range(int(s), int(e) + 1)]
    crowd = sum(1 for t in secs if per_t.get(float(t), 0) >= 3) / max(1, len(secs)) >= 0.5
    out.append({"start": round(s, 2), "end": round(e, 2), "preset": int(p), "crowd": bool(crowd)})
res = {"decode_s": round(decode_s, 1), "frames": n, "moves": moves, "shots": out,
       "presets": int(len(set(lab))), "crowd_presets": sorted({o["preset"] for o in out if o["crowd"]})}
(sess / "shots.json").write_text(json.dumps(res))
print(json.dumps({k: v for k, v in res.items() if k not in ("moves", "shots")} | {
    "moves": len(moves), "shots": len(out), "crowd_shots": sum(o["crowd"] for o in out)}, indent=2))
