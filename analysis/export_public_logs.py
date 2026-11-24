"""Logs behind the paper's speed and voice claims, with students as anonymous ids (S01..S58).

    python analysis/export_public_logs.py   ->  paper/data/{timings,voice_anchors,voice_heldout_tests,voice_matches}.csv

timings.csv              measured seconds per class and step (shot finding, transcription, one-minute attendance)
voice_anchors.csv        every name-call anchor under both rules (face check on = evaluation; off = portal)
voice_heldout_tests.csv  every leave-one-class-out test under both rules: who it was, who the print said, similarity, lead
voice_matches.csv        every comment the portal names: how, similarity, and whether the camera recognised that
                         student in that class
Run analysis/name_to_voice.py with FACE_CHECK=1 and FACE_CHECK=0 first.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from pseudonyms import load  # noqa: E402

P, sid, _ = load()
MEDIA = ROOT / "data" / "media"
OUT = ROOT / "paper" / "data"
S8 = MEDIA / "2026-10-08-core-section-a"
rd = lambda p: json.loads(Path(p).read_text())
# name_to_voice.py records students by their position in the four-section gallery.
GALLERY = [str(n) for n in __import__("numpy").load(S8 / "gallery.npz")["names"]]
who = lambda x: sid[GALLERY[x]] if isinstance(x, int) else sid[x]


def write(name, header, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {name}: {len(rows)} rows")


rows = []
for s in P["sessions"]:
    d = MEDIA / s["id"]
    sh, tm = rd(d / "shots.json"), rd(d / "timing_mlx.json")
    rows.append([s["date"], "find camera shots (160x90, 4 fps)", sh["decode_s"], f"{len(sh['shots'])} shots, {sh['frames']} frames", "shots.json"])
    rows.append([s["date"], "transcribe 2 h (whisper-large-v3-turbo, mlx, Mac GPU)", tm["transcribe_s"],
                 f"{tm['audio_minutes']} min audio, {tm['x_realtime']}x real time, {tm['count']} section first names", "timing_mlx.json"])
    fa = d / "fast_attendance.json"
    if fa.exists():
        f = rd(fa)
        for step in ("find_shots_s", "pick_class_shots_s", "match_faces_s", "total_s"):
            rows.append([s["date"], f"one-minute attendance: {step[:-2].replace('_', ' ')}", f[step],
                         f"{f['students_named']} of {f['full_1fps_named']} named by the full scan; {f['wrong_section']} certain errors" if step == "total_s" else "",
                         "fast_attendance.json"])
write("timings.csv", ["class", "step", "seconds", "detail", "source"], rows)

anchors, tests = [], []
for rule, fname in (("face check (evaluation)", "name_to_voice.json"), ("no face check (portal)", "name_to_voice_noface.json")):
    r = rd(S8 / fname)
    anchors += [[rule, a["class"], round(a["start"], 2), who(a["student"])] for a in r["anchors"]]
    tests += [[rule, t["class"], who(t["student"]), who(t["top1"]), t["top1"] == t["student"], t["similarity"], t["lead"], t["accepted"],
               t["prints_from_other_classes"]] for t in r["tests_detail"]]
write("voice_anchors.csv", ["rule", "class", "reply_start_s", "student"], anchors)
write("voice_heldout_tests.csv", ["rule", "held_out_class", "student", "print_said", "correct", "similarity", "lead_over_next",
                                  "accepted_at_0.50_with_0.05_lead", "prints_from_other_classes"], tests)

write("voice_matches.csv", ["class", "start_s", "end_s", "seconds", "student", "how", "similarity", "camera_recognised_student_that_class"],
      [[c["date"], round(c["start"], 2), round(c["end"], 2), c["seconds"], sid[c["student"]], c["how"], c["confidence"], c["seen_that_day"]]
       for c in sorted(P["comments"], key=lambda c: (c["date"], c["start"]))])
