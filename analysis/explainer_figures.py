"""Charts that show how the pipeline works, from the pilot's own data (anonymised: no names, no faces).

    python analysis/explainer_figures.py   ->  paper-latex/figures/e01..e03.png

e01  how camera shots are found, and the three frames fast attendance reads in each student shot
e02  how a face gets a name: every face at 1080p against the threshold-and-margin rule
e03  how a voice gets a name: one student's name calls, then voice matches across five classes
"""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "data" / "media"
OUT = ROOT / "paper-latex" / "figures"
S8 = MEDIA / "2026-10-08-core-section-a"
P = json.loads((ROOT / "data" / "portal" / "portal.json").read_text())

# Palette checked with the dataviz validator (light surface): green, gold, purple, red. Gold marks are always labelled.
INK, MUTED, GRID = "#1c1c1a", "#6b6b66", "#e6e6e2"
GREEN, GOLD, PURPLE, RED, FRONT = "#2f8a4e", "#d99a00", "#5b3fc4", "#c0362c", "#d9d9d4"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#bbbbb6", "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left"})


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


order = sorted(P["roster"], key=lambda r: hashlib.sha256(("SALT-NOT-PUBLISHED" + r["id"]).encode()).hexdigest())
anon = {r["name"]: f"S{i + 1:02d}" for i, r in enumerate(order)}

# ---------------------------------------------------------------- e01 camera shots and fast-attendance frames
sh = json.loads((S8 / "shots.json").read_text())
move = np.load(S8 / "move_frac_4fps.npy")
a, b = 30 * 60, 42 * 60  # twelve minutes of the Oct 8 class
t = np.arange(len(move)) / 4.0
w = (t >= a) & (t <= b)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 2.9), sharex=True, gridspec_kw={"height_ratios": [1.6, 1], "hspace": 0.35})
ax1.fill_between(t[w] / 60, move[w], color="#9a9a94", lw=0, alpha=0.55)
for m in sh["moves"]:
    if a <= m <= b:
        ax1.axvline(m / 60, color=INK, lw=0.6, alpha=0.5)
ax1.set_ylabel("pixels changing")
ax1.set_ylim(0, 1)
ax1.set_yticks([0, 0.5, 1], ["0", "50%", "100%"])
ax1.set_title("1. Find camera moves in a tiny 160×90 copy, 4 frames a second")
ax1.text(a / 60 + 0.1, 0.88, "each spike is the camera turning; vertical lines are detected moves", fontsize=7.6, color=MUTED)
for s in sh["shots"]:
    if s["end"] < a or s["start"] > b:
        continue
    x0, x1 = max(s["start"], a) / 60, min(s["end"], b) / 60
    ax2.barh(0, x1 - x0, left=x0, height=0.62, color=GOLD if s["crowd"] else FRONT, edgecolor="white", linewidth=1)
    if s["crowd"]:
        for fr in (0.2, 0.5, 0.8):
            ax2.plot(x0 + fr * (x1 - x0), 0, "o", ms=3.6, color=INK, mec="white", mew=0.6)
ax2.set_ylim(-0.6, 1.3)
ax2.set_yticks([])
ax2.spines["left"].set_visible(False)
ax2.set_xlabel("minutes into the recording (8 Oct)")
ax2.set_title("2. Between moves is a shot; a shot with 3+ faces is a student shot", pad=2)
ax2.text(a / 60, 0.72, "gold: student shot   grey: front of room   ●: the 3 frames read for one-minute attendance", fontsize=7.6, color=MUTED, va="center")
save(fig, "e01_how_shots")

# ---------------------------------------------------------------- e02 naming rule
f = np.load(S8 / "faces.npz")
g = np.load(S8 / "gallery.npz")
names, sections = [str(n) for n in g["names"]], [str(s) for s in g["sections"]]
roster = {r["name"] for r in P["roster"]}
mine = {sections[i] for i, n in enumerate(names) if n in roster}
best, margin = f["best"], f["best"] - f["second"]
other = np.array([sections[i] not in mine for i in f["best_idx"]])
keep = np.random.default_rng(7).random(len(best)) < 0.45
fig, ax = plt.subplots(figsize=(3.5, 3.0))
ax.add_patch(plt.Rectangle((0.50, 0.05), 0.5, 1, color=GREEN, alpha=0.08, lw=0))
ax.axvline(0.50, color=INK, lw=0.9, ls="--")
ax.axhline(0.05, color=INK, lw=0.9, ls="--")
ax.scatter(best[keep & ~other], margin[keep & ~other], s=3, color="#a7a7a1", lw=0, alpha=0.6, label="best match is in this section")
ax.scatter(best[other], margin[other], s=7, color=RED, lw=0, alpha=0.8, label="best match is in another section\n(would be wrong if named)")
acc = (best >= 0.50) & (margin >= 0.05)
ax.text(0.515, 0.33, f"named\n{acc.sum():,} faces\n{(acc & other).sum()} certainly wrong", fontsize=7.8, color=GREEN, fontweight="bold", va="top")
ax.annotate("score ≥ 0.50", xy=(0.50, 0.27), xytext=(0.31, 0.27), fontsize=7.2, color=INK, va="center", arrowprops=dict(arrowstyle="->", lw=0.7, color=INK))
ax.annotate("lead ≥ 0.05", xy=(0.66, 0.05), xytext=(0.62, 0.15), fontsize=7.2, color=INK, arrowprops=dict(arrowstyle="->", lw=0.7, color=INK))
ax.set_xlim(0.15, 0.80)
ax.set_ylim(0, 0.40)
ax.set_xlabel("best match score (cosine)")
ax.set_ylabel("lead over the runner-up")
ax.set_title("How a face gets a name")
ax.legend(loc="upper left", fontsize=6.8, frameon=False, markerscale=2.2)
ax.grid(color=GRID, lw=0.5)
ax.set_axisbelow(True)
save(fig, "e02_how_faces")

# ---------------------------------------------------------------- e03 naming a voice
learned = sorted(P["voices"]["learned"], key=lambda l: -l["matches"])[0]
who = learned["student"]
dates = [s["date"] for s in P["sessions"]]
labels = dict(zip(dates, ["22 Sep", "24 Sep", "29 Sep", "6 Oct", "8 Oct"]))
fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [2.2, 1], "wspace": 0.32})
for i, d in enumerate(dates):
    ax.plot([0, 120], [i, i], color=GRID, lw=6, solid_capstyle="round", zorder=0)
for c in (c for c in P["comments"] if c["student"] == who):
    y, x = dates.index(c["date"]), c["start"] / 60
    if c["how"] == "called by name":
        ax.plot(x, y, "D", ms=8, color=PURPLE, mec="white", mew=0.8, zorder=3)
    else:
        ax.plot(x, y, "o", ms=4 + min(6, c["seconds"] / 15), color=GREEN, mec="white", mew=0.6, zorder=2)
ax.set_yticks(range(len(dates)), [labels[d] for d in dates])
ax.invert_yaxis()
ax.set_xlim(-2, 122)
ax.set_xlabel("minutes into class")
ax.set_title(f"One student ({anon[who]}) across five classes")
ax.plot([], [], "D", color=PURPLE, ms=6, label="instructor ends a sentence with the name; a reply of 5 s+ becomes the voiceprint")
ax.plot([], [], "o", color=GREEN, ms=6, label="a later comment that matches the voiceprint (score ≥ 0.50); size = length")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), fontsize=7, frameon=False, ncol=1)
called = [sum(1 for c in P["comments"] if c["date"] == d and c["how"] == "called by name") for d in dates]
voice = [sum(1 for c in P["comments"] if c["date"] == d and c["how"] == "voice match") for d in dates]
xs = np.arange(len(dates))
bx.bar(xs, called, width=0.66, color=PURPLE, edgecolor="white", linewidth=1, label="called by name")
bx.bar(xs, voice, width=0.66, bottom=called, color=GREEN, edgecolor="white", linewidth=1, label="voice match")
for x_, c_, v_ in zip(xs, called, voice):
    bx.text(x_, c_ + v_ + 0.6, str(c_ + v_), ha="center", fontsize=7.4, color=INK)
bx.set_xticks(xs, [labels[d] for d in dates], rotation=40, ha="right", fontsize=7.4)
bx.set_ylabel("named comments")
bx.set_title("All students")
bx.set_ylim(0, max(c + v for c, v in zip(called, voice)) * 1.45)
bx.legend(loc="upper right", fontsize=6.8, frameon=False)
bx.grid(axis="y", color=GRID, lw=0.5)
bx.set_axisbelow(True)
save(fig, "e03_how_voices")
