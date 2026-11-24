"""Who was seen: named, seen but not named, never seen. Aggregate numbers only.

    python analysis/presence.py <session_dir> <section>

Every face is grouped with faces that look alike (average-linkage clustering on SFace
similarity), so a person seen 50 times at different angles counts once. A group is a
named student when its frames were confidently matched (>= 0.50 with margin) mostly to
one person. Unnamed groups are matched again on their average face, which is steadier
than any single frame. What remains is people the system saw but can't name; the
biggest such group in front-of-room shots is the instructor.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

sess, section = Path(sys.argv[1]), sys.argv[2]
g = np.load(sess / "gallery.npz")
f = np.load(sess / "faces.npz")
names, sections, G = g["names"], g["sections"], g["emb"]
t, box, E, bi, bs, ss = f["t"], f["box"], f["emb"], f["best_idx"], f["best"], f["second"]
in_sec = sections == section
n_sec = int(in_sec.sum())

TH, MARGIN = 0.50, 0.05
named = (bs >= TH) & ((bs - ss) >= MARGIN)
frame_named = {int(i) for i in bi[named]}
frame_named_sec = {i for i in frame_named if in_sec[i]}
frame_named_out = {i for i in frame_named if not in_sec[i]}

# Faces per frame: lets us tell student shots (3+ faces) from front-of-room shots.
per_t = Counter(t.tolist())
crowd = np.array([per_t[x] >= 3 for x in t.tolist()])

Z = linkage(E, method="average", metric="cosine")
lab = fcluster(Z, t=1 - 0.45, criterion="distance")  # join groups above 0.45 similarity

groups = []
for c in np.unique(lab):
    m = lab == c
    n = int(m.sum())
    nm = Counter(int(i) for i in bi[m & named])
    cen = E[m].mean(0); cen /= np.linalg.norm(cen)
    sims = G @ cen
    o = np.argsort(-sims)[:2]
    groups.append({"n": n, "named_votes": nm, "cen_best": int(o[0]), "cen_s": float(sims[o[0]]),
                   "cen_margin": float(sims[o[0]] - sims[o[1]]), "crowd_share": float(crowd[m].mean()),
                   "seconds": len(set(t[m].tolist()))})

sure, via_avg, unknown = set(), set(), []
conflicts = 0
for gr in groups:
    if gr["named_votes"]:
        top, k = gr["named_votes"].most_common(1)[0]
        if k >= 0.8 * sum(gr["named_votes"].values()):
            sure.add(top)
        else:
            conflicts += 1
        continue
    if gr["cen_s"] >= 0.45 and gr["cen_margin"] >= 0.05 and gr["seconds"] >= 3:
        via_avg.add(gr["cen_best"])
    elif gr["seconds"] >= 3:
        unknown.append(gr)

via_avg -= sure
found_sec = {i for i in sure | via_avg if in_sec[i]}
found_out = {i for i in sure | via_avg if not in_sec[i]}
instr = max((u for u in unknown if u["crowd_share"] < 0.5), key=lambda u: u["seconds"], default=None)
unknown_students = [u for u in unknown if u is not instr and u["crowd_share"] >= 0.5]

res = {
    "section": section, "enrolled_in_section": n_sec,
    "faces_indexed": int(len(t)), "seconds_with_any_face": len(per_t),
    "seconds_with_students_on_screen": int(sum(1 for v in per_t.values() if v >= 3)),
    "named_from_single_frames": len(frame_named_sec),
    "named_from_single_frames_wrong_section": len(frame_named_out),
    "named_after_grouping_faces": len(found_sec),
    "named_after_grouping_wrong_section": len(found_out),
    "added_by_grouping": len({i for i in via_avg if in_sec[i]}),
    "groups_with_conflicting_names": conflicts,
    "seen_but_not_named_people_est": len(unknown_students),
    "instructor_group_found": instr is not None,
    "never_seen_upper_bound": n_sec - len(found_sec) - len(unknown_students),
    "never_seen_if_no_unnamed": n_sec - len(found_sec),
}
(sess / "presence.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
