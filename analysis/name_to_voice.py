"""Name a student's voice from "professor says a name", then carry it across classes.

    python analysis/name_to_voice.py <section> <session_dir> [<session_dir> ...]

Per class (turns_v2.json + turn_voice_v2.npz from session_voice.py):
  - professor turns: voice close to the professor's print (built from the first session's
    biggest voice group; same professor every class)
  - anchor: the first student turn (3 s+) starting within 20 s after a professor turn that
    names exactly one section student by first name (roster spelling, unique first names)
Then:
  - leave-one-class-out: each student's print from their anchors in the OTHER classes;
    does it name their anchors in this class correctly?
  - coverage: share of all student talk (3 s+ turns) the prints can name at 0.5 / margin 0.05
Writes name_to_voice.json (FACE_CHECK=1, the default: the called student's face must be on camera during the reply)
or name_to_voice_noface.json (FACE_CHECK=0, the portal's rule) next to the first session, with every anchor
and every held-out test listed (names: private; the public build swaps them for anonymous ids).
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

import os

section = sys.argv[1]
sessions = [Path(p) for p in sys.argv[2:]]
FACE_CHECK = os.environ.get("FACE_CHECK", "1") == "1"
g = np.load(sessions[0] / "gallery.npz")
names = [str(n) for n in g["names"]]
sec = g["sections"]
firsts = defaultdict(list)
for i, n in enumerate(names):
    if sec[i] == section:
        firsts[n.split()[0].lower()].append(i)
unique_first = {f: v[0] for f, v in firsts.items() if len(v) == 1 and len(f) >= 3}

norm = lambda v: v / np.linalg.norm(v)


def load(sess):
    turns = json.loads((sess / "turns_v2.json").read_text())
    V = np.load(sess / "turn_voice_v2.npz")
    return turns, {int(k): norm(V[k]) for k in V.files}


# professor print from the first session's biggest voice group
t0, v0 = load(sessions[0])
ids = sorted(v0)
X = np.stack([v0[i] for i in ids])
lab = fcluster(linkage(X, "average", metric="cosine"), t=0.45, criterion="distance")
talk = Counter()
for i, l in zip(ids, lab):
    talk[l] += t0[i]["end"] - t0[i]["start"]
P = norm(X[lab == talk.most_common(1)[0][0]].mean(0))

per = {}
anchors = []      # (session, turn, student)
student_turns = {}  # session -> [(turn, dur)]
voices = {}
for sess in sessions:
    turns, V = load(sess)
    voices[sess.name] = V
    prof = {i for i, v in V.items() if float(v @ P) >= 0.5}
    st = [t for t in turns if t["i"] in V and t["i"] not in prof and t["end"] - t["start"] >= 3]
    student_turns[sess.name] = [(t["i"], t["end"] - t["start"]) for t in st]
    # Faces seen per second (0.45 with margin): a called name must also be on camera.
    fz = np.load(sess / "faces.npz")
    okf = (fz["best"] >= 0.45) & ((fz["best"] - fz["second"]) >= 0.05)
    face_at = defaultdict(set)
    for tt, p in zip(fz["t"][okf], fz["best_idx"][okf]):
        face_at[int(tt)].add(int(p))
    used = set()
    n_anchor = n_named = 0
    for t in turns:
        if t["i"] not in prof:
            continue
        tail = " ".join(t["text"].split()[-8:])  # a call comes at the end: "...Sam, go."
        hits = {unique_first[w.lower()] for w in re.findall(r"\b[A-Z][a-z]+\b", tail) if w.lower() in unique_first}
        if len(hits) != 1:
            continue
        n_named += 1
        stu = next(iter(hits))
        nxt = next((s for s in st if t["end"] - 1 <= s["start"] <= t["end"] + 20 and s["i"] not in used
                    and s["end"] - s["start"] >= 5), None)
        if nxt is None:
            continue
        window = range(int(t["end"]) - 5, int(nxt["end"]) + 3)
        if FACE_CHECK and not any(stu in face_at.get(x, ()) for x in window):
            continue
        used.add(nxt["i"])
        anchors.append((sess.name, nxt["i"], stu))
        n_anchor += 1
    per[sess.name] = {"turns": len(turns), "professor_turns": len(prof), "student_turns_3s": len(st),
                      "student_minutes": round(sum(d for _, d in student_turns[sess.name]) / 60, 1),
                      "names_called": n_named, "anchors": n_anchor}

# leave-one-class-out on anchors
tests = correct = accepted = acc_correct = 0
test_rows = []
for sname in voices:
    prints = defaultdict(list)
    for s2, ti, stu in anchors:
        if s2 != sname:
            prints[stu].append(voices[s2][ti])
    if len(prints) < 2:
        continue
    C = {k: norm(np.mean(v, 0)) for k, v in prints.items()}
    keys = list(C)
    M = np.stack([C[k] for k in keys])
    for s2, ti, stu in anchors:
        if s2 != sname or stu not in C:
            continue
        sims = M @ voices[sname][ti]
        o = np.argsort(-sims)[:2]
        tests += 1
        correct += keys[o[0]] == stu
        ok = bool(sims[o[0]] >= 0.5 and sims[o[0]] - sims[o[1]] >= 0.05)
        if ok:
            accepted += 1
            acc_correct += keys[o[0]] == stu
        test_rows.append({"class": sname[:10], "turn": ti, "student": stu, "top1": keys[o[0]], "similarity": round(float(sims[o[0]]), 3),
                          "lead": round(float(sims[o[0]] - sims[o[1]]), 3), "accepted": ok, "prints_from_other_classes": len(keys)})

# coverage with prints from all anchors
prints = defaultdict(list)
for s2, ti, stu in anchors:
    prints[stu].append(voices[s2][ti])
C = {k: norm(np.mean(v, 0)) for k, v in prints.items()}
keys = list(C)
cov = {}
if keys:
    M = np.stack([C[k] for k in keys])
    for sname, lst in student_turns.items():
        tot = sum(d for _, d in lst)
        named_d = 0
        who = set()
        for ti, d in lst:
            sims = M @ voices[sname][ti]
            o = np.argsort(-sims)[:2]
            if sims[o[0]] >= 0.5 and (len(o) < 2 or sims[o[0]] - sims[o[1]] >= 0.05):
                named_d += d
                who.add(keys[o[0]])
        cov[sname] = {"student_talk_named_share": round(named_d / tot, 2) if tot else 0, "students_named_by_voice": len(who)}

res = {"section": section, "classes": per, "anchors_total": len(anchors),
       "students_with_anchor": len(set(a[2] for a in anchors)),
       "students_anchored_in_2plus_classes": sum(
           1 for c in Counter(stu for _, stu in {(s, stu) for s, _, stu in anchors}).values() if c >= 2),
       "leave_one_class_out": {"tests": tests, "top1_correct": correct,
                               "accepted_at_0.5": accepted, "accepted_correct": acc_correct},
       "coverage": cov, "face_check": FACE_CHECK,
       "anchors": [{"class": s2[:10], "turn": ti, "start": next(t["start"] for t in json.loads((Path(next(x for x in map(str, sessions) if Path(x).name == s2)) / "turns_v2.json").read_text()) if t["i"] == ti),
                    "student": stu} for s2, ti, stu in anchors],
       "tests_detail": test_rows}
(sessions[0] / ("name_to_voice.json" if FACE_CHECK else "name_to_voice_noface.json")).write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
