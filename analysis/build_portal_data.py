"""Gather every analysis into one JSON file for the professor portal.

    python analysis/build_portal_data.py <repo_root> <section> <session_dir> [<session_dir> ...]

Writes data/portal/portal.json (never committed). Images are served by the portal from
data/media/<session>/class_view and the repo's photos/2028.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

repo, section = Path(sys.argv[1]), sys.argv[2]
sessions = [Path(p) for p in sys.argv[3:]]
pilot = Path(__file__).resolve().parents[1]
out_dir = pilot / "data" / "portal"
out_dir.mkdir(parents=True, exist_ok=True)
slug = lambda n: re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
norm = lambda v: v / np.linalg.norm(v)
fmt = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"

g = np.load(sessions[0] / "gallery.npz")
names, sec = [str(n) for n in g["names"]], g["sections"]
cohorts = json.loads((repo / "build/data/cohorts.json").read_text())
teams = {}
tp = repo / "build/data/teams.json"
if tp.exists():
    teams = {k: str(v) for k, v in json.loads(tp.read_text()).get("FT|2028", {}).items()}
roster = [{"id": slug(n), "name": n, "photo": f"/photos/2028/{slug(n)}.jpg", "team": teams.get(n)}
          for i, n in enumerate(names) if sec[i] == section]
roster.sort(key=lambda r: r["name"])
idx_of = {n: i for i, n in enumerate(names)}

# ---- professor voiceprint (same professor every class), from the first session
def load_voice(sess):
    turns = json.loads((sess / "turns_v2.json").read_text())
    V = np.load(sess / "turn_voice_v2.npz")
    return turns, {int(k): norm(V[k]) for k in V.files}


t0, v0 = load_voice(sessions[0])
ids = sorted(v0)
X = np.stack([v0[i] for i in ids])
lab = fcluster(linkage(X, "average", metric="cosine"), t=0.45, criterion="distance")
talk = Counter()
for i, l in zip(ids, lab):
    talk[l] += t0[i]["end"] - t0[i]["start"]
P = norm(X[lab == talk.most_common(1)[0][0]].mean(0))

firsts = defaultdict(list)
for i, n in enumerate(names):
    if sec[i] == section:
        firsts[n.split()[0].lower()].append(i)
unique_first = {f: v[0] for f, v in firsts.items() if len(v) == 1 and len(f) >= 3}

# ---- per session: voices, calls, anchors
S = {}
anchors = []
for sess in sessions:
    turns, V = load_voice(sess)
    prof = {i for i, v in V.items() if float(v @ P) >= 0.5}
    calls = []
    for t in turns:
        if t["i"] not in prof:
            continue
        tail = " ".join(t["text"].split()[-8:])
        hits = {unique_first[w.lower()] for w in re.findall(r"\b[A-Z][a-z]+\b", tail) if w.lower() in unique_first}
        if len(hits) == 1:
            calls.append({"t": t["end"], "student": names[next(iter(hits))], "text": tail})
    st = [t for t in turns if t["i"] in V and t["i"] not in prof and t["end"] - t["start"] >= 3]
    used = set()
    for c in calls:
        nxt = next((s for s in st if c["t"] - 1 <= s["start"] <= c["t"] + 20 and s["i"] not in used
                    and s["end"] - s["start"] >= 5), None)
        if nxt:
            used.add(nxt["i"])
            anchors.append((sess.name, nxt["i"], c["student"]))
    S[sess.name] = {"turns": turns, "V": V, "prof": prof, "calls": calls, "st": st}

# Labels the professor (or pilot team) gave in the portal. A student label is a confirmed anchor
# and overrides anything automatic; "not a student" / "professor" removes the turn from student talk.
lp = out_dir / "labels.json"
manual = json.loads(lp.read_text()) if lp.exists() else []
excluded = set()
manual_keys = set()
by_date = {sess.name[:10]: sess.name for sess in sessions}
for lab_ in manual:
    sname = by_date.get(lab_["date"])
    if not sname:
        continue
    t = min(S[sname]["turns"], key=lambda x: abs(x["start"] - lab_["start"]))
    if abs(t["start"] - lab_["start"]) > 0.5:
        continue
    anchors = [a for a in anchors if not (a[0] == sname and a[1] == t["i"])]
    if lab_["kind"] == "student" and lab_.get("student") and t["i"] in S[sname]["V"]:
        anchors.append((sname, t["i"], lab_["student"]))
        manual_keys.add((sname, t["i"]))
    elif lab_["kind"] in ("not_student", "professor"):
        excluded.add((sname, t["i"]))
        if lab_["kind"] == "professor":
            S[sname]["prof"].add(t["i"])
for sname in S:
    S[sname]["st"] = [t for t in S[sname]["st"] if (sname, t["i"]) not in excluded and t["i"] not in S[sname]["prof"]]

prints = defaultdict(list)
for sname, ti, stu in anchors:
    prints[stu].append(S[sname]["V"][ti])
C = {k: norm(np.mean(v, 0)) for k, v in prints.items()}
ckeys = list(C)
CM = np.stack([C[k] for k in ckeys]) if ckeys else None
anchor_set = {(a, b): c for a, b, c in anchors}

# ---- Oct 8 AI scores (two passes, transcript v1 turn ids) mapped by time
scores_by_time = []
s8 = next((s for s in sessions if s.name.startswith("2026-10-08")), None)
if s8 and (s8 / "scoring_B.json").exists() and (s8 / "turns.json").exists():
    v1 = json.loads((s8 / "turns.json").read_text())
    for r in json.loads((s8 / "scoring_B.json").read_text()):
        if r["r"] > 0:
            t = v1[r["turn"]]
            scores_by_time.append((t["start"], t["end"], {"relevance": r["r"], "evidence": r["e"],
                                                          "builds_on_others": r["b"], "insight": r["i"],
                                                          "mean": round((r["r"] + r["e"] + r["b"] + r["i"]) / 4, 2)}))

SESSION_START = {}
# ---- assemble sessions
sessions_out, attendance, comments, transcripts = [], defaultdict(dict), [], {}
for sess in sessions:
    d = S[sess.name]
    date = sess.name[:10]
    cv = json.loads((sess / "class_view" / "class.json").read_text()) if (sess / "class_view" / "class.json").exists() else {}
    for s in cv.get("students", []):
        attendance[s["slug"]][date] = {
            "seconds": s["seen_seconds"], "present": s["seen_seconds"] >= 3, "first": s.get("first_seen"),
            "last": s.get("last_seen"), "score": s.get("best_score"),
            "tile": f"/media/{sess.name}/class_view/{s['tile']}" if s.get("seen") else None}
    rows = []
    # (SESSION_START is filled below for the voice pool)
    # Pre-class music and chatter: class starts after the last quiet stretch (30 s with no
    # speech of 5 s or more) before the professor's first long stretch of speech.
    first_long = next((t["start"] for t in d["turns"] if t["i"] in d["prof"] and t["end"] - t["start"] >= 20), 0)
    start_t, last_long_end = 0, None
    for t in d["turns"]:
        if t["start"] > first_long:
            break
        dur = t["end"] - t["start"]
        if dur >= 5:
            if last_long_end is not None and t["start"] - last_long_end >= 30:
                start_t = t["start"]
            last_long_end = t["end"]
    SESSION_START[sess.name] = start_t
    for t in d["turns"]:
        if t["end"] <= start_t:
            if not rows or rows[-1]["role"] != "preclass":
                rows.append({"start": t["start"], "end": t["end"], "at": fmt(t["start"]), "role": "preclass",
                             "text": "(before class: music and chatter, not transcribed here)", "speaker": None,
                             "how": None, "confidence": None, "score": None})
            else:
                rows[-1]["end"] = t["end"]
            continue
        role = "professor" if t["i"] in d["prof"] else ("student" if t["i"] in d["V"] else "short")
        if (sess.name, t["i"]) in excluded and role == "student":
            role = "short"
        who, how, conf = None, None, None
        if (sess.name, t["i"]) in anchor_set:
            who = anchor_set[(sess.name, t["i"])]
            how = "you labelled" if (sess.name, t["i"]) in manual_keys else "called by name"
        elif role == "student" and CM is not None and t["end"] - t["start"] >= 3:
            sims = CM @ d["V"][t["i"]]
            o = np.argsort(-sims)[:2]
            if sims[o[0]] >= 0.5 and (len(o) < 2 or sims[o[0]] - sims[o[1]] >= 0.05):
                who, how, conf = ckeys[o[0]], "voice match", round(float(sims[o[0]]), 2)
        sc = None
        if date == "2026-10-08" and role == "student":
            best = max(((min(t["end"], e) - max(t["start"], s), v) for s, e, v in scores_by_time), default=(0, None), key=lambda x: x[0])
            if best[0] > 2:
                sc = best[1]
        rows.append({"start": t["start"], "end": t["end"], "at": fmt(t["start"]), "role": role, "text": t["text"],
                     "speaker": who, "how": how, "confidence": conf, "score": sc})
        if who and role == "student":
            seen_day = attendance.get(slug(who), {}).get(date, {}).get("seconds", 0) > 0
            comments.append({"date": date, "at": fmt(t["start"]), "start": t["start"], "end": t["end"], "seconds": round(t["end"] - t["start"], 1),
                             "student": who, "student_id": slug(who), "how": how, "confidence": conf, "text": t["text"], "score": sc,
                             "seen_that_day": seen_day})
    transcripts[date] = rows
    prof_s = sum(t["end"] - t["start"] for t in d["turns"] if t["i"] in d["prof"] and t["end"] > start_t)
    stud_s = sum(t["end"] - t["start"] for t in d["st"] if t["end"] > start_t)
    ac = json.loads((sessions[0] / "across_sessions.json").read_text())["sessions"].get(sess.name, {})
    sessions_out.append({
        "date": date, "id": sess.name, "resolution": ac.get("resolution"), "median_face_px": ac.get("median_face_px"),
        "seconds_students_on_screen": ac.get("seconds_students_on_screen"),
        "named_any": ac.get("students_named"), "wrong_section_people": ac.get("wrong_section_people"),
        "present_3s": sum(1 for s in cv.get("students", []) if s["seen_seconds"] >= 3),
        "professor_minutes": round(prof_s / 60, 1), "student_minutes": round(stud_s / 60, 1),
        "duration": round(max((t["end"] for t in d["turns"]), default=0), 1),
        "class_start": round(SESSION_START.get(sess.name, 0), 1),
        "camera": [[s_["start"], s_["end"]] for s_ in (json.loads((sess / "shots.json").read_text())["shots"] if (sess / "shots.json").exists() else []) if s_["crowd"]],
        "calls": [{"t": round(c["t"], 1), "at": fmt(c["t"]), "student": c["student"], "student_id": slug(c["student"]), "text": c["text"]} for c in d["calls"]],
        "rooms": [{"preset": r["preset"], "faces": r["faces"], "at": r["time"], "in_panorama": r.get("in_panorama", False),
                   "image": f"/media/{sess.name}/class_view/{r['image']}"} for r in cv.get("rooms", [])],
        "panorama": f"/media/{sess.name}/class_view/{cv['panorama']}" if cv.get("panorama") else None,
    })

sessions_out.sort(key=lambda s: s["date"])
for r in roster:
    a = attendance.get(r["id"], {})
    r["attendance"] = a
    r["sessions_present"] = sum(1 for v in a.values() if v["present"])
    r["seconds_total"] = sum(v["seconds"] for v in a.values())
    mine = [c for c in comments if c["student_id"] == r["id"]]
    r["comments"] = len(mine)
    r["comments_to_check"] = sum(1 for c in mine if c["how"] == "voice match" and not c["seen_that_day"])
    r["talk_seconds"] = round(sum(c["seconds"] for c in mine), 1)
    r["called"] = sum(1 for s in sessions_out for c in s["calls"] if c["student_id"] == r["id"])
    r["voiceprint"] = r["name"] in C
    sc = [c["score"]["mean"] for c in mine if c["score"]]
    r["avg_score"] = round(sum(sc) / len(sc), 2) if sc else None

# ---- voices: learned (one per student with anchors) and unknown groups of unnamed student voice
learned = []
for stu, vs in prints.items():
    mine_a = [(s_, ti) for s_, ti, st_ in anchors if st_ == stu]
    samples = []
    for s_, ti in mine_a[:3]:
        t = S[s_]["turns"][ti]
        samples.append({"date": s_[:10], "start": t["start"], "end": t["end"], "text": t["text"][:160]})
    learned.append({"student": stu, "student_id": slug(stu), "anchors": len(mine_a),
                    "manual": sum(1 for k in mine_a if k in manual_keys),
                    "matches": sum(1 for c in comments if c["student"] == stu and c["how"] == "voice match"),
                    "samples": samples})
learned.sort(key=lambda x: -(x["anchors"] + x["matches"]))

named_keys = {(c["date"], round(c["start"], 2)) for c in comments}
pool = []
for sname, d in S.items():
    for t in d["st"]:
        if (sname[:10], round(t["start"], 2)) in named_keys or (sname, t["i"]) in excluded:
            continue
        if t["start"] < SESSION_START.get(sname, 0):
            continue
        pool.append((sname, t))
groups = []
if len(pool) >= 2:
    PX = np.stack([S[s_]["V"][t["i"]] for s_, t in pool])
    gl = fcluster(linkage(PX, "average", metric="cosine"), t=0.5, criterion="distance")
    for gid in np.unique(gl):
        idx = np.where(gl == gid)[0]
        tot = sum(pool[i][1]["end"] - pool[i][1]["start"] for i in idx)
        if len(idx) < 2 and tot < 15:
            continue
        cen = norm(PX[idx].mean(0))
        sug = None
        if CM is not None:
            sims = CM @ cen
            o = int(np.argmax(sims))
            if sims[o] >= 0.35:
                sug = {"student": ckeys[o], "student_id": slug(ckeys[o]), "similarity": round(float(sims[o]), 2)}
        items = sorted(idx, key=lambda i: -(pool[i][1]["end"] - pool[i][1]["start"]))[:6]
        groups.append({"id": int(gid), "turns": len(idx), "seconds": round(tot, 1),
                       "spans": [{"date": pool[i][0][:10], "start": pool[i][1]["start"], "end": pool[i][1]["end"]} for i in idx],
                       "classes": len({pool[i][0] for i in idx}), "suggestion": sug,
                       "clips": [{"date": pool[i][0][:10], "start": pool[i][1]["start"], "end": pool[i][1]["end"],
                                  "at": fmt(pool[i][1]["start"]), "text": pool[i][1]["text"][:200]} for i in items]})
groups.sort(key=lambda g: -g["seconds"])

portal = {"section": section, "course": "Core MBA course: leading people", "professor": "the instructor",
          "generated": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
          "roster": roster, "sessions": sessions_out, "voices": {"learned": learned, "unknown": groups[:40],
          "unknown_total": len(groups), "labels": len(manual)}, "comments": sorted(comments, key=lambda c: (c["date"], c["start"])),
          "transcripts": transcripts}
(out_dir / "portal.json").write_text(json.dumps(portal))
print(f"roster {len(roster)}, sessions {len(sessions_out)}, comments {len(comments)}, "
      f"voiceprints {len(C)}, anchors {len(anchors)}; wrote {out_dir / 'portal.json'}")
