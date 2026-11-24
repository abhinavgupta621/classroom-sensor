"""Who is seen across several sessions of the same section.

    python analysis/across_sessions.py <section> <session_dir> [<session_dir> ...]

Per session: students named at 0.50 (single frames plus faces followed through a shot),
wrong-section matches (certain errors), seconds with students on screen, video resolution.
Across sessions: how many sessions each student was seen in. A student seen in most
sessions but missing from one was probably absent that day; a student never seen in any
session is sitting where the camera doesn't look (or never attends).
Writes across_sessions.json next to the first session.
"""
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

section = sys.argv[1]
sessions = [Path(p) for p in sys.argv[2:]]


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i) if i else 0.0


def named_in(sess):
    g = np.load(sess / "gallery.npz"); f = np.load(sess / "faces.npz")
    G, sec, names = g["emb"], g["sections"], [str(n) for n in g["names"]]
    t, box, E = f["t"], f["box"], f["emb"]
    seen = defaultdict(set)
    for k in range(len(t)):
        s = G @ E[k]; o = np.argsort(-s)[:2]
        if s[o[0]] >= 0.50 and s[o[0]] - s[o[1]] >= 0.05:
            seen[int(o[0])].add(float(t[k]))
    by_t = defaultdict(list)
    for k in np.argsort(t, kind="stable"):
        by_t[float(t[k])].append(int(k))
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
    for tr in tracks:
        c = E[tr].mean(0); c /= np.linalg.norm(c)
        s = G @ c; o = np.argsort(-s)[:2]
        if s[o[0]] >= 0.50 and s[o[0]] - s[o[1]] >= 0.05:
            for k in tr:
                seen[int(o[0])].add(float(t[k]))
    per_t = Counter(t.tolist())
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(sess / "camera.mp4")], capture_output=True, text=True).stdout.strip()
    px = np.minimum(box[:, 2], box[:, 3])
    return names, sec, seen, {
        "resolution": res, "faces_indexed": int(len(t)), "median_face_px": float(np.median(px)) if len(px) else 0,
        "seconds_students_on_screen": int(sum(1 for v in per_t.values() if v >= 3)),
        "students_named": sum(1 for p in seen if sec[p] == section),
        "wrong_section_people": sum(1 for p in seen if sec[p] != section),
        "wrong_section_seconds": sum(len(v) for p, v in seen.items() if sec[p] != section),
    }


per = {}
count = Counter()
seconds = defaultdict(list)
for sess in sessions:
    names, sec, seen, info = named_in(sess)
    per[sess.name] = info
    for p, v in seen.items():
        if sec[p] == section:
            count[names[p]] += 1
            seconds[names[p]].append(len(v))
roster = [n for n, s in zip(names, sec) if s == section]
n = len(sessions)
dist = Counter(count.get(r, 0) for r in roster)
out = {
    "section": section, "sessions": per, "enrolled": len(roster),
    "seen_in_at_least_one": sum(1 for r in roster if count.get(r, 0) > 0),
    "seen_in_every_session": dist.get(n, 0),
    "never_seen": dist.get(0, 0),
    "students_by_sessions_seen": {str(k): dist.get(k, 0) for k in range(n + 1)},
    "median_seconds_on_camera_when_seen": float(np.median([s for v in seconds.values() for s in v])) if seconds else 0,
}
(sessions[0] / "across_sessions.json").write_text(json.dumps(out, indent=2))
(sessions[0] / "across_sessions_internal.json").write_text(json.dumps(
    {r: {"sessions_seen": count.get(r, 0), "seconds": seconds.get(r, [])} for r in roster}, indent=1))
print(json.dumps(out, indent=2))
