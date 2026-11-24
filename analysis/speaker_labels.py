"""Put names on student speech using the camera, then measure voice accuracy from it.

    python analysis/speaker_labels.py <session_dir> <section>

For each stretch of student speech (voice not in the instructor's voice group):
  - camera frames inside it (4 a second) are face-matched against the class gallery;
  - three independent signals each nominate a speaker:
      centre  the named face the camera is centred on
      lips    the named face whose mouth moves most relative to the rest of the face
      name    a first name the instructor said in the 20 s before
  - the stretch gets a name only when two signals agree.
Those labels then give ground truth for voice: build each student's voiceprint from their
other labelled turns and check whether a held-out turn is matched back to them.

Writes speaker_labels.json (aggregates) and labels_internal.json (per-turn labels, for later
analyses; stays in the session folder).
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402

sess, section = Path(sys.argv[1]), sys.argv[2]
turns = json.loads((sess / "turns.json").read_text())
V = np.load(sess / "turn_voice.npz")
g = np.load(sess / "gallery.npz")
names, sections, G = g["names"], g["sections"], g["emb"]
in_sec = sections == section
backend = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=24)
TH, MARGIN = 0.50, 0.05

# ---- 1. Instructor by voice: the voice group with the most talk time.
ids = sorted(int(k) for k in V.files)
X = np.stack([V[str(i)] / np.linalg.norm(V[str(i)]) for i in ids])
lab = fcluster(linkage(X, "average", metric="cosine"), t=1 - 0.55, criterion="distance")
talk = defaultdict(float)
for i, l in zip(ids, lab):
    talk[l] += turns[i]["end"] - turns[i]["start"]
instr_l = max(talk, key=talk.get)
instr_c = X[lab == instr_l].mean(0); instr_c /= np.linalg.norm(instr_c)
voice = {i: X[k] for k, i in enumerate(ids)}
is_instr = {i: float(voice[i] @ instr_c) >= 0.55 for i in ids}
student_turns = [turns[i] for i in ids if not is_instr[i] and turns[i]["end"] - turns[i]["start"] >= 2.0]
print(f"{len(ids)} voiced turns, {sum(is_instr.values())} instructor, {len(student_turns)} student turns >= 2 s", flush=True)

# ---- 2. First names said by the instructor.
STOP = {"will", "grace", "hope", "faith", "joy", "may", "june", "summer", "rose", "mark", "max", "chase",
        "hunter", "dean", "rich", "art", "ray", "young", "sky", "april", "august", "bill", "frank", "sage",
        "page", "lane", "drew", "rob", "pat", "don", "kyra"}
first = defaultdict(list)
for k, n in enumerate(names):
    if in_sec[k]:
        first[n.split()[0].lower()].append(k)
unique_first = {fn: ks[0] for fn, ks in first.items() if len(ks) == 1 and fn not in STOP and len(fn) >= 3}


def named_in(text):
    hits = set()
    for tok in re.findall(r"\b[A-Z][a-z]+\b", text):
        k = unique_first.get(tok.lower())
        if k is not None:
            hits.add(k)
    return hits


# ---- 3. Camera signals inside each student turn.
cap = cv2.VideoCapture(str(sess / "camera.mp4"))
W = cap.get(cv2.CAP_PROP_FRAME_WIDTH); H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)


def region(gray, b, y0, y1, x0=0.2, x1=0.8):
    x, y, w, h = b
    r = gray[max(0, int(y + y0 * h)):max(0, int(y + y1 * h)), max(0, int(x + x0 * w)):max(0, int(x + x1 * w))]
    return cv2.resize(r, (32, 16)).astype(np.float32) if r.size else None


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i) if i else 0.0


rows = []
for tr in student_turns:
    s, e = tr["start"], tr["end"]
    n_frames = min(48, max(4, int((e - s) * 4)))
    tracks = []  # {box, votes Counter, mouth[], upper[], prev_m, prev_u, centre[]}
    for t in np.linspace(s, e, n_frames):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        for f in backend.faces(img):
            q = f.embedding / np.linalg.norm(f.embedding)
            sims = G @ q
            o = np.argsort(-sims)[:2]
            who = int(o[0]) if sims[o[0]] >= TH and sims[o[0]] - sims[o[1]] >= MARGIN else None
            m, u = region(gray, f.box, 0.62, 0.95), region(gray, f.box, 0.2, 0.5)
            best = max(tracks, key=lambda tk: iou(tk["box"], f.box), default=None)
            if best is None or iou(best["box"], f.box) < 0.4:
                best = {"votes": Counter(), "mouth": [], "upper": [], "pm": None, "pu": None, "centre": []}
                tracks.append(best)
            best["box"] = f.box
            if who is not None:
                best["votes"][who] += 1
            cx, cy = f.box[0] + f.box[2] / 2, f.box[1] + f.box[3] / 2
            best["centre"].append(np.hypot((cx - W / 2) / W, (cy - H / 2) / H))
            if m is not None and u is not None and best["pm"] is not None:
                best["mouth"].append(float(np.abs(m - best["pm"]).mean()))
                best["upper"].append(float(np.abs(u - best["pu"]).mean()))
            best["pm"], best["pu"] = m, u
    named_tracks = []
    for tk in tracks:
        if tk["votes"]:
            who, k = tk["votes"].most_common(1)[0]
            if k >= 2:
                named_tracks.append((who, tk))
    sig = {}
    if named_tracks:
        sig["centre"] = min(named_tracks, key=lambda wt: np.median(wt[1]["centre"]))[0]
        lips = [(w, np.mean(tk["mouth"]) / (np.mean(tk["upper"]) + 1.0)) for w, tk in named_tracks if len(tk["mouth"]) >= 3]
        lips.sort(key=lambda x: -x[1])
        if lips and (len(lips) == 1 or lips[0][1] >= 1.3 * lips[1][1]):
            sig["lips"] = lips[0][0]
    before = " ".join(t2["text"] for t2 in turns if t2["end"] <= s + 0.5 and t2["end"] >= s - 20
                      and t2["i"] in is_instr and is_instr[t2["i"]])
    nm = named_in(before)
    if len(nm) == 1:
        sig["name"] = next(iter(nm))
    votes = Counter(sig.values())
    label = None
    if votes:
        who, k = votes.most_common(1)[0]
        if k >= 2:
            label = who
    rows.append({"i": tr["i"], "dur": round(e - s, 1), "signals": sig, "label": label,
                 "faces_named_in_view": len(named_tracks)})
cap.release()

# ---- 4. Signal agreement (each pair, where both fired).
agree = {}
for a, b in [("centre", "lips"), ("centre", "name"), ("lips", "name")]:
    both = [r for r in rows if a in r["signals"] and b in r["signals"]]
    agree[f"{a}+{b}"] = {"both_fired": len(both), "agreed": sum(r["signals"][a] == r["signals"][b] for r in both)}

labelled = [r for r in rows if r["label"] is not None]
lab_sec = [r for r in labelled if in_sec[r["label"]]]

# ---- 5. Voice accuracy from the labels.
by_student = defaultdict(list)
for r in lab_sec:
    by_student[r["label"]].append(r["i"])
loo_total = loo_correct = 0
gen, imp = [], []
for st, tis in by_student.items():
    for ti in tis:
        others = [x for x in tis if x != ti]
        if not others:
            continue
        cents = {}
        for s2, t2s in by_student.items():
            use = [x for x in t2s if x != ti]
            if use:
                c = np.mean([voice[x] for x in use], 0); cents[s2] = c / np.linalg.norm(c)
        pred = max(cents, key=lambda k: float(voice[ti] @ cents[k]))
        loo_total += 1
        loo_correct += pred == st
for a in range(len(lab_sec)):
    for b in range(a + 1, len(lab_sec)):
        s = float(voice[lab_sec[a]["i"]] @ voice[lab_sec[b]["i"]])
        (gen if lab_sec[a]["label"] == lab_sec[b]["label"] else imp).append(s)
gen, imp = np.array(gen), np.array(imp)
ver = []
for th in (0.3, 0.4, 0.5, 0.6):
    ver.append({"threshold": th,
                "same_student_matched": round(float((gen >= th).mean()), 3) if len(gen) else None,
                "different_students_matched": round(float((imp >= th).mean()), 3) if len(imp) else None})

res = {
    "student_turns_2s_plus": len(rows),
    "student_speech_minutes": round(sum(r["dur"] for r in rows) / 60, 1),
    "turns_with_a_named_face_in_view": sum(1 for r in rows if r["faces_named_in_view"] > 0),
    "signals_fired": {k: sum(1 for r in rows if k in r["signals"]) for k in ("centre", "lips", "name")},
    "signal_agreement": agree,
    "turns_labelled_(2_signals_agree)": len(labelled),
    "labelled_to_wrong_section": len(labelled) - len(lab_sec),
    "labelled_minutes": round(sum(r["dur"] for r in lab_sec) / 60, 1),
    "distinct_students_labelled": len(by_student),
    "students_with_2plus_labelled_turns": sum(1 for v in by_student.values() if len(v) >= 2),
    "voice_leave_one_out": {"tests": loo_total, "correct": loo_correct},
    "voice_pairs": {"same_student": int(len(gen)), "different_students": int(len(imp)),
                    "same_median": round(float(np.median(gen)), 3) if len(gen) else None,
                    "different_median": round(float(np.median(imp)), 3) if len(imp) else None,
                    "by_threshold": ver},
}
(sess / "speaker_labels.json").write_text(json.dumps(res, indent=2))
(sess / "labels_internal.json").write_text(json.dumps(
    [{**r, "label": (str(names[r["label"]]) if r["label"] is not None else None),
      "signals": {k: str(names[v]) for k, v in r["signals"].items()}} for r in rows], indent=1))
print(json.dumps(res, indent=2))
