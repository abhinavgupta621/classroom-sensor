"""Figures and an anonymised results file for the paper.

    python analysis/paper_figures.py

Reads the local pilot data (data/, never committed) and writes, for publication:
    paper/figures/*.png   figures (students as S01..S58; other students' faces blurred)
    paper/data/results.json  aggregate and anonymised per-student results
No names, face templates, voiceprints, transcripts or recordings leave data/.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "paper"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
(OUT / "data").mkdir(parents=True, exist_ok=True)
MEDIA = DATA / "media"
S8 = MEDIA / "2026-10-08-core-section-a"
portal = json.loads((DATA / "portal" / "portal.json").read_text())
R = DATA / "results"
load = lambda p: json.loads(Path(p).read_text())

INK, MUTED, OSKI, GOLD, BLUE, PURPLE, RED = "#1c1c1a", "#6b6b66", "#3f7d58", "#e0a100", "#1d5bbf", "#5b3fc4", "#b42318"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#bbbbb6", "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "figure.dpi": 160})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ---- anonymous ids: stable, not derived from name order
roster = portal["roster"]
order = sorted(roster, key=lambda r: hashlib.sha256(("SALT-NOT-PUBLISHED" + r["id"]).encode()).hexdigest())
anon = {r["name"]: f"S{i + 1:02d}" for i, r in enumerate(order)}
sessions = portal["sessions"]
dates = [s["date"] for s in sessions]
label = {d: __import__("datetime").date.fromisoformat(d).strftime("%b %-d") for d in dates}

# ---------------------------------------------------------------- F1 pipeline
fig, ax = plt.subplots(figsize=(10, 3.6))
ax.axis("off")
boxes = [
    (0.02, 0.62, "Panopto recording", "room camera feed\nroom audio\n(pick camera by content)"),
    (0.22, 0.80, "Camera shots", "low-res pass, 35 s\nwhen camera is on class"),
    (0.22, 0.40, "Transcript", "Whisper large-v3-turbo\nroster names as hints, 7 min"),
    (0.42, 0.80, "Faces", "YuNet detect, SFace match\n229-photo gallery, ≥0.50"),
    (0.42, 0.40, "Voices", "ECAPA voiceprint per turn\nprofessor print split"),
    (0.62, 0.80, "Attendance", "seen ≥3 s per class\nfast: 3 frames per shot"),
    (0.62, 0.40, "Who spoke", "name call → next voice\nvoiceprints across classes"),
    (0.82, 0.60, "Instructor portal", "timeline, people,\nvoice labelling, method"),
]
for x, y, t, sub in boxes:
    ax.add_patch(plt.Rectangle((x, y - 0.17), 0.16, 0.32, fc="#f7f7f6", ec="#bbbbb6", lw=1, transform=ax.transAxes))
    ax.text(x + 0.08, y + 0.07, t, ha="center", va="center", weight="bold", fontsize=9.5, transform=ax.transAxes)
    ax.text(x + 0.08, y - 0.06, sub, ha="center", va="center", fontsize=7.6, color=MUTED, transform=ax.transAxes)
for (a, b) in [((0.18, 0.62), (0.22, 0.80)), ((0.18, 0.62), (0.22, 0.40)), ((0.38, 0.80), (0.42, 0.80)), ((0.38, 0.40), (0.42, 0.40)),
               ((0.58, 0.80), (0.62, 0.80)), ((0.58, 0.40), (0.62, 0.40)), ((0.78, 0.80), (0.82, 0.64)), ((0.78, 0.40), (0.82, 0.56)),
               ((0.50, 0.63), (0.70, 0.57))]:
    ax.annotate("", xy=b, xytext=a, xycoords="axes fraction", arrowprops=dict(arrowstyle="->", color=MUTED, lw=1))
ax.text(0.60, 0.60, "face in shot\n(confidence)", fontsize=7, color=MUTED, ha="center", transform=ax.transAxes)
save(fig, "f01_pipeline")

# ---------------------------------------------------------------- F2 identification thresholds
ei = load(R / "eval_identity.json")
th = [r["threshold"] for r in ei["by_threshold"]]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4))
a1.plot(th, [r["faces_named"] for r in ei["by_threshold"]], "o-", color=INK, label="faces named")
a1.set_xlabel("match threshold (cosine)"); a1.set_ylabel("faces named", color=INK)
b1 = a1.twinx(); b1.plot(th, [r["distinct_oski_students_found"] for r in ei["by_threshold"]], "s--", color=OSKI, label="students found")
b1.set_ylabel("distinct students found (of 58)", color=OSKI); b1.spines["right"].set_visible(True)
a1.set_title("More permissive matching names more faces")
a2.bar([str(t) for t in th], [r["named_outside_section_(certainly_wrong)"] for r in ei["by_threshold"]], color=[RED if r["named_outside_section_(certainly_wrong)"] else OSKI for r in ei["by_threshold"]])
for i, r in enumerate(ei["by_threshold"]):
    a2.text(i, r["named_outside_section_(certainly_wrong)"] + 0.3, f'{r["estimated_correct_name_rate"] * 100:.1f}% est. correct', ha="center", fontsize=7.5, color=MUTED)
a2.set_xlabel("match threshold"); a2.set_ylabel("faces matched to another section\n(certainly wrong)")
a2.set_title("…but errors appear below 0.50")
save(fig, "f02_identification_thresholds")

# ---------------------------------------------------------------- F3 verification (same-seat vs same-frame pairs)
fp = load(R / "check_face_pairs.json")
rows = fp["by_threshold"]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.plot([r["threshold"] for r in rows], [r["true_match_rate"] * 100 for r in rows], "o-", color=OSKI, label="same person matched (%)")
ax.plot([r["threshold"] for r in rows], [r["false_match_vs_70_enrolled"] * 100 for r in rows], "s-", color=RED, label="wrong person clears bar vs 70 enrolled (%)")
ax.axvline(0.363, color=MUTED, ls=":", lw=1); ax.text(0.366, 50, "OpenCV\ndefault", fontsize=7.5, color=MUTED)
ax.axvline(0.50, color=INK, ls="--", lw=1); ax.text(0.503, 50, "pilot\ndefault", fontsize=7.5)
ax.set_xlabel("threshold"); ax.set_ylabel("%"); ax.legend(frameon=False, fontsize=8)
ax.set_title(f'{fp["same_person_pairs"]:,} same-seat and {fp["different_person_pairs"]:,} same-frame pairs')
save(fig, "f03_verification")

# ---------------------------------------------------------------- F4 camera coverage per class
fig, ax = plt.subplots(figsize=(10, 2.8))
for i, s in enumerate(sessions):
    y = len(sessions) - 1 - i
    ax.barh(y, s["duration"] / 60, left=0, color="#f0f0ee", height=0.6)
    if s["class_start"]:
        ax.barh(y, s["class_start"] / 60, left=0, color="#e4e4e0", height=0.6)
    for a, b in s["camera"]:
        ax.barh(y, (b - a) / 60, left=a / 60, color=GOLD, height=0.6)
    cov = sum(b - a for a, b in s["camera"]) / s["duration"] * 100
    ax.text(s["duration"] / 60 + 1, y, f'{cov:.0f}%  ·  {s["resolution"].replace(",", "×")}', va="center", fontsize=8, color=MUTED)
ax.set_yticks(range(len(sessions)), [label[s["date"]] for s in reversed(sessions)])
ax.set_xlabel("minutes into recording"); ax.set_xlim(0, 150)
ax.set_title("When the moving room camera showed the class (gold); grey = before class")
save(fig, "f04_camera_coverage")

# ---------------------------------------------------------------- F5 attendance across classes
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.3), gridspec_kw={"width_ratios": [1.2, 1]})
x = np.arange(len(sessions))
present = [s["present_3s"] for s in sessions]
glimpsed = [sum(1 for r in roster if r["attendance"].get(s["date"], {}).get("seconds", 0) > 0 and not r["attendance"][s["date"]]["present"]) for s in sessions]
a1.bar(x, present, color=OSKI, label="recognised ≥3 s")
a1.bar(x, glimpsed, bottom=present, color=GOLD, label="glimpsed only")
a1.axhline(58, color=MUTED, ls=":", lw=1); a1.text(-0.4, 58.8, "58 enrolled", fontsize=7.5, color=MUTED)
a1.set_xticks(x, [f'{label[s["date"]]}\n{s["resolution"].replace(",", "×")}' for s in sessions], fontsize=8)
a1.set_ylim(0, 64); a1.legend(frameon=False, fontsize=8, loc="lower right"); a1.set_title("Students recognised per class")
dist = Counter(r["sessions_present"] for r in roster)
a2.bar(range(6), [dist.get(k, 0) for k in range(6)], color=[RED if k == 0 else OSKI for k in range(6)])
for k in range(6):
    a2.text(k, dist.get(k, 0) + 0.4, str(dist.get(k, 0)), ha="center", fontsize=8)
a2.set_xlabel("classes recognised in (of 5)"); a2.set_ylabel("students"); a2.set_title("55 of 58 seen at least once")
save(fig, "f05_attendance")

# ---------------------------------------------------------------- F6 anonymised attendance heatmap
M = np.array([[r["attendance"].get(d, {}).get("seconds", 0) for d in dates] for r in sorted(roster, key=lambda r: anon[r["name"]])])
fig, ax = plt.subplots(figsize=(10, 2.6))
im = ax.imshow(np.log1p(M.T), aspect="auto", cmap="Greens")
ax.set_yticks(range(len(dates)), [label[d] for d in dates]); ax.set_xticks(range(0, 58, 4), [f"S{i + 1:02d}" for i in range(0, 58, 4)], fontsize=7)
cb = fig.colorbar(im, ax=ax, pad=0.01); cb.set_ticks(np.log1p([0, 10, 60, 300, 900])); cb.set_ticklabels(["0", "10s", "1m", "5m", "15m"])
ax.set_title("Time each student was recognised on camera, per class (anonymised)")
save(fig, "f06_attendance_matrix")

# ---------------------------------------------------------------- F7 one class on a timeline (Oct 8), anonymised
s8 = next(s for s in sessions if s["date"] == "2026-10-08")
rows8 = portal["transcripts"]["2026-10-08"]
fig, ax = plt.subplots(figsize=(10, 2.6))
tracks = ["Called on", "Students", "Professor", "Camera on class"]
for a, b in s8["camera"]:
    ax.barh(3, (b - a) / 60, left=a / 60, color=GOLD, height=0.6)
cmap = plt.get_cmap("tab20")
ids = sorted({r["speaker"] for r in rows8 if r["speaker"]})
for r in rows8:
    if r["role"] == "professor":
        ax.barh(2, (r["end"] - r["start"]) / 60, left=r["start"] / 60, color=INK, height=0.6)
    elif r["role"] == "student":
        c = cmap(ids.index(r["speaker"]) % 20) if r["speaker"] else "#c9c9c4"
        ax.barh(1, (r["end"] - r["start"]) / 60, left=r["start"] / 60, color=c, height=0.6)
for c in s8["calls"]:
    ax.plot(c["t"] / 60, 0, "o", color=PURPLE, ms=6)
ax.axvspan(0, s8["class_start"] / 60, color="#f0f0ee", zorder=-1)
ax.set_yticks(range(4), tracks); ax.set_xlabel("minutes"); ax.set_xlim(0, s8["duration"] / 60)
ax.set_title("One class (Oct 8): named students in colour, unknown student voices grey, name calls in purple")
save(fig, "f07_class_timeline")

# ---------------------------------------------------------------- F8 fast attendance
fig, ax = plt.subplots(figsize=(6.4, 3.2))
pts = {"Oct 8 (1080p)": [(135, 37, 57), (225, 38, 77), (7200, 43, 600)], "Sep 22 (576p)": [(165, 34, 59), (275, 37, 65), (7200, 43, 600)]}
for (k, v), col in zip(pts.items(), [INK, OSKI]):
    ax.plot([p[0] for p in v], [p[1] for p in v], "o-", color=col, label=k)
    for f, n, t in v:
        ax.annotate(f"{t}s", (f, n), textcoords="offset points", xytext=(4, -10), fontsize=7, color=MUTED)
ax.set_xscale("log"); ax.set_xlabel("frames examined (log)"); ax.set_ylabel("students recognised")
ax.set_title("A few frames per camera shot recovers ~86–88%"); ax.legend(frameon=False, fontsize=8)
save(fig, "f08_fast_attendance")

# ---------------------------------------------------------------- F9 voiceprints: same vs different speaker
def norm(v): return v / np.linalg.norm(v)
anch = []
for s in sessions:
    sd = MEDIA / s["id"]
    V = np.load(sd / "turn_voice_v2.npz")
    turns = json.loads((sd / "turns_v2.json").read_text())
    for r in portal["comments"]:
        if r["date"] == s["date"] and r["how"] == "called by name":
            t = min(turns, key=lambda x: abs(x["start"] - r["start"]))
            if str(t["i"]) in V.files:
                anch.append((r["student"], s["date"], norm(V[str(t["i"])])))
same, diff = [], []
for i in range(len(anch)):
    for j in range(i + 1, len(anch)):
        sim = float(anch[i][2] @ anch[j][2])
        (same if anch[i][0] == anch[j][0] else diff).append(sim)
fig, ax = plt.subplots(figsize=(6.4, 3.2))
bins = np.linspace(-0.2, 1, 30)
ax.hist(diff, bins=bins, color="#c9c9c4", label=f"different students ({len(diff)} pairs)")
ax.hist(same, bins=bins, color=PURPLE, alpha=0.85, label=f"same student ({len(same)} pairs)")
ax.axvline(0.5, color=INK, ls="--", lw=1); ax.set_xlabel("voiceprint similarity (cosine)"); ax.set_ylabel("pairs")
ax.legend(frameon=False, fontsize=8); ax.set_title("Comments labelled by name calls, across 5 classes")
save(fig, "f09_voice_similarity")

# ---------------------------------------------------------------- F10 who-is-speaking cues
sc = load(S8 / "speaker_cues.json")["summary"]
fig, ax = plt.subplots(figsize=(6.4, 3))
names_ = ["speaker in shot", "gaze of others", "lip motion", "nearest centre", "largest face"]
vals = [sc["speaker_in_view"], sc["gaze"]["right"], sc["lips"]["right"], sc["centre"]["right"], sc["largest"]["right"]]
ax.barh(names_[::-1], vals[::-1], color=[RED, RED, RED, RED, OSKI][::-1] if False else [OSKI if v >= 6 else RED for v in vals][::-1])
for i, v in enumerate(vals[::-1]):
    ax.text(v + 0.1, i, f"{v} of {sc['comments']}", va="center", fontsize=8)
ax.set_xlim(0, sc["comments"] + 1.5); ax.set_title(f"Visual cues among ~{sc['median_faces_in_shot']:.0f} faces per shot")
save(fig, "f10_speaker_cues")

# ---------------------------------------------------------------- F11 transcription speed and names
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3))
cfg = ["small.en\nCPU", "large-v3-turbo\nCPU batched*", "large-v3-turbo\nMac GPU (mlx)"]
a1.bar(cfg, [15, 34, 6.7], color=[MUTED, MUTED, OSKI])
for i, v in enumerate([15, 34, 6.7]):
    a1.text(i, v + 0.6, f"{v:g} min", ha="center", fontsize=8)
a1.set_ylabel("minutes for 2 h of audio"); a1.set_title("Transcription time (*machine under load)")
a2.bar(["no hints", "class list as hints"], [4, 10], color=[MUTED, OSKI])
a2.set_ylim(0, 11); a2.set_ylabel("names recognisable (of ~10 called)")
for i, v in enumerate([4, 10]):
    a2.text(i, v + 0.2, str(v), ha="center", fontsize=8)
a2.set_title("Names the instructor called (Oct 8)")
save(fig, "f11_transcription")

# ---------------------------------------------------------------- F12 rubric agreement
sb = load(S8 / "scoring_B.json")
agree = load(S8 / "scoring_agreement.json")
fig, ax = plt.subplots(figsize=(4.8, 3.2))
cnt = Counter()
diffs = {(x["turn"], x["criterion"]) for x in agree["differences"]}
crit = {"r": "relevance", "e": "evidence", "b": "builds_on_others", "i": "insight"}
for r in sb:
    for k, name in crit.items():
        b = r[k]
        a = b + (-1 if (r["turn"], name) in diffs and b > 0 else 0)
        cnt[(a, b)] += 1
H = np.zeros((6, 6))
for (a, b), n in cnt.items():
    H[a, b] = n
ax.imshow(H, cmap="Purples"); ax.set_xlabel("run B score"); ax.set_ylabel("run A score")
for a in range(6):
    for b in range(6):
        if H[a, b]:
            ax.text(b, a, int(H[a, b]), ha="center", va="center", fontsize=8, color="white" if H[a, b] > 20 else INK)
ax.set_title(f'{agree["identical"]} of {agree["scores_compared"]} scores identical')
save(fig, "f12_rubric_agreement")

# ---------------------------------------------------------------- F13 timings
from_findings = [("Download a class", 1), ("Find camera shots", 0.6), ("Attendance, fast", 1), ("Attendance, full", 10),
                 ("Transcript (Mac GPU)", 7), ("Voiceprints", 1), ("Professor/student split", 5), ("Name cards (optional)", 7),
                 ("Gallery and room views", 0.25), ("Summary and review sheet", 1.5), ("Rubric scoring", 1)]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.barh([k for k, _ in from_findings][::-1], [v for _, v in from_findings][::-1], color=OSKI)
ax.set_xlabel("minutes per 2-hour class, one Mac"); ax.set_title("Pipeline step times")
save(fig, "f13_timings")

# ---------------------------------------------------------------- Images: blurred class frame with detections, author frame, panorama
sys_path = str(ROOT)
import sys  # noqa: E402
sys.path.insert(0, sys_path)
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402
gal = np.load(S8 / "gallery.npz")
G = gal["emb"]
back = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=24)
cap = cv2.VideoCapture(str(S8 / "camera.mp4")); cap.set(cv2.CAP_PROP_POS_MSEC, 900 * 1000); ok, img = cap.read(); cap.release()
faces_found = back.faces(img)
# Desk name cards are legible at 1080p: soften the whole frame so no card can be read.
img = cv2.GaussianBlur(img, (0, 0), 2.6)
for f in faces_found:
    x, y, w, h = [max(0, int(v)) for v in f.box]
    s_ = G @ (f.embedding / np.linalg.norm(f.embedding)); o = np.argsort(-s_)[:2]
    named = s_[o[0]] >= 0.5 and s_[o[0]] - s_[o[1]] >= 0.05
    pad = int(0.25 * max(w, h))
    y0, y1, x0, x1 = max(0, y - pad), y + h + pad, max(0, x - pad), x + w + pad
    img[y0:y1, x0:x1] = cv2.GaussianBlur(img[y0:y1, x0:x1], (0, 0), 14)
    col = (88, 125, 63) if named else (21, 161, 224)
    cv2.rectangle(img, (x, y), (x + w, y + h), col, 4)
    cv2.putText(img, f"{s_[o[0]]:.2f}", (x, y + h + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2, cv2.LINE_AA)
cv2.imwrite(str(FIG / "i01_detections_blurred.jpg"), cv2.resize(img, (1600, 900)), [cv2.IMWRITE_JPEG_QUALITY, 85])
me = DATA / "results" / "me-in-class.jpg"
if me.exists():
    (FIG / "i02_author_match.jpg").write_bytes(me.read_bytes())
pan = cv2.imread(str(S8 / "class_view" / "panorama.jpg"))
if pan is not None:
    pfaces = back.faces(pan)
    pan = cv2.GaussianBlur(pan, (0, 0), 2.2)
    for f in pfaces:
        x, y, w, h = [max(0, int(v)) for v in f.box]
        pad = int(0.3 * max(w, h))
        pan[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad] = cv2.GaussianBlur(pan[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad], (0, 0), 14)
    cv2.imwrite(str(FIG / "i03_panorama_blurred.jpg"), pan, [cv2.IMWRITE_JPEG_QUALITY, 82])
print("wrote images")

# ---------------------------------------------------------------- anonymised results
res = {
    "setting": {"students": len(roster), "classes": len(sessions), "gallery": int(len(G)), "sections_in_gallery": 4},
    "sessions": [{"date": s["date"], "resolution": s["resolution"], "duration_s": s["duration"], "class_start_s": s["class_start"],
                  "camera_on_students_s": round(sum(b - a for a, b in s["camera"]), 1), "recognised_3s": s["present_3s"],
                  "professor_min": s["professor_minutes"], "student_side_min": s["student_minutes"], "name_calls": len(s["calls"])} for s in sessions],
    "students": [{"id": anon[r["name"]], "classes_recognised": r["sessions_present"], "seconds_on_camera": {d: r["attendance"].get(d, {}).get("seconds", 0) for d in dates},
                  "named_comments": r["comments"], "named_talk_s": r["talk_seconds"], "times_called": r["called"], "voiceprint": r["voiceprint"]}
                 for r in sorted(roster, key=lambda r: anon[r["name"]])],
    "face_identification": ei, "face_verification": fp, "camera_check": {k: v for k, v in load(R / "check_camera.json")["camera"].items() if k != "timeline"},
    "audio_check": {k: v for k, v in load(R / "check_audio.json")["audio"].items() if k != "turn_timeline"},
    "name_cards": load(S8 / "name_cards.json"), "speaker_cues": sc, "name_to_voice": load(S8 / "name_to_voice.json"),
    "voice_pairs": {"same": len(same), "different": len(diff), "same_median": round(float(np.median(same)), 3) if same else None,
                    "different_median": round(float(np.median(diff)), 3) if diff else None},
    "rubric_agreement": agree, "presence_single_class": load(S8 / "presence.json"),
    "across_sessions": load(S8 / "across_sessions.json"),
}
(OUT / "data" / "results.json").write_text(json.dumps(res, indent=1))
print("wrote results.json")
