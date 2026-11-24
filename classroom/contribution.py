"""Who said what, from the classroom audio.

1. Transcribe with word timings.
2. Group words into turns at pauses.
3. Label each turn by voice: short turns get one embedding; long turns are cut into
   overlapping 3-second windows so a hand-off between speakers without a pause is
   still caught. Each word takes the label of the nearest window.
4. Re-group words into contributions wherever the speaker label changes.

Speakers who don't consent to voice matching are never identified: their speech stays
in the transcript as "Unidentified" and is not attributed to anyone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .backends import Word
from .config import Config
from .gallery import Gallery, Match
from .roster import Person

SR = 16000
# 3 s is about the least audio ECAPA identifies reliably; a 0.5 s hop places a speaker
# change to within roughly a word. (ECAPA on CPU is ~10 ms a window, so 90 minutes of
# speech is about two minutes of work.)
WIN_S, HOP_S = 3.0, 0.5
UNKNOWN, SHORT = "unknown", "short"


@dataclass
class Contribution:
    id: str
    speaker_id: str | None
    speaker_name: str
    kind: str  # student | instructor | unknown | short
    start: float
    end: float
    text: str
    voice_score: float
    needs_review: bool

    @property
    def seconds(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["seconds"] = round(self.seconds, 1)
        return d


def _turns(words: list[Word], gap: float) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in words:
        if out and w.start - out[-1][-1].end < gap:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _clip(audio: np.ndarray, s: float, e: float) -> np.ndarray:
    return audio[max(0, int(s * SR)): max(0, int(e * SR))]


def _label(m: Match) -> str:
    return m.person_id if m.accepted else UNKNOWN


def label_words(words, audio, voice_backend, gallery: Gallery, cfg: Config):
    """Returns [(word, label, match_or_None)] in order."""
    out = []
    for turn in _turns(words, cfg.turn_gap_s):
        s, e = turn[0].start, turn[-1].end
        if e - s < cfg.min_turn_s:
            out.extend((w, SHORT, None) for w in turn)
            continue
        if e - s <= WIN_S + HOP_S:
            m = gallery.match(voice_backend.embed(_clip(audio, s, e)), cfg.voice_threshold, cfg.voice_margin)
            out.extend((w, _label(m), m) for w in turn)
            continue
        windows = []
        t = s
        while t < e:
            ws, we = t, min(t + WIN_S, e)
            if we - ws >= cfg.min_turn_s:
                m = gallery.match(voice_backend.embed(_clip(audio, ws, we)), cfg.voice_threshold, cfg.voice_margin)
                windows.append(((ws + we) / 2, m))
            t += HOP_S
        labelled = []
        for w in turn:
            mid = (w.start + w.end) / 2
            _, m = min(windows, key=lambda cw: abs(cw[0] - mid))
            labelled.append((w, _label(m), m))
        out.extend(_smooth(labelled, cfg.min_run_s))
    return out


def _smooth(labelled, min_run_s: float):
    """Within one turn, a speaker label that holds for less than min_run_s is noise
    (an unenrolled voice brushing past a classmate's template, or a window straddling
    a hand-off). Fold each such run into its longer neighbour until none are left."""
    while True:
        runs = []  # [label, first_index, last_index]
        for i, (_, label, _) in enumerate(labelled):
            if runs and runs[-1][0] == label:
                runs[-1][2] = i
            else:
                runs.append([label, i, i])
        if len(runs) < 2:
            return labelled
        dur = lambda r: labelled[r[2]][0].end - labelled[r[1]][0].start
        short = min(runs, key=dur)
        if dur(short) >= min_run_s:
            return labelled
        k = runs.index(short)
        neighbours = [runs[j] for j in (k - 1, k + 1) if 0 <= j < len(runs)]
        target = max(neighbours, key=dur)[0]
        for i in range(short[1], short[2] + 1):
            w, _, m = labelled[i]
            labelled[i] = (w, target, m)


def build_contributions(labelled, roster: dict[str, Person], cfg: Config) -> list[Contribution]:
    groups: list[list] = []
    for item in labelled:
        w, label, _ = item
        if groups:
            pw, plabel, _ = groups[-1][-1]
            if label == plabel and w.start - pw.end < cfg.turn_gap_s * 3:
                groups[-1].append(item)
                continue
        groups.append([item])

    out: list[Contribution] = []
    for i, g in enumerate(groups, start=1):
        label = g[0][1]
        matches = [m for _, _, m in g if m is not None]
        score = float(np.mean([m.score for m in matches])) if matches else 0.0
        text = "".join(w.text for w, _, _ in g).strip()
        if label in (UNKNOWN, SHORT):
            kind, pid, name = label, None, "Unidentified"
            # An unknown turn whose best guess was close is worth a human look.
            review = label == UNKNOWN and any(m.score >= cfg.voice_review_floor for m in matches)
        else:
            p = roster[label]
            kind, pid, name = ("instructor" if p.is_instructor else "student"), label, p.name
            review = any((m.score - m.runner_up) < cfg.voice_margin * 2 for m in matches)
        out.append(Contribution(f"c{i:03d}", pid, name, kind, g[0][0].start, g[-1][0].end,
                                text, round(score, 3), review))
    return out


def contribute(audio_path, transcriber, voice_backend, gallery: Gallery,
               roster: dict[str, Person], cfg: Config) -> list[Contribution]:
    gallery = gallery.restrict_to_consented(roster)
    audio = transcriber.load_audio(audio_path)
    words = transcriber.words(audio)
    return build_contributions(label_words(words, audio, voice_backend, gallery, cfg), roster, cfg)


def student_stats(contribs: list[Contribution], roster: dict[str, Person]) -> dict[str, dict]:
    stats = {pid: {"name": p.name, "turns": 0, "talk_seconds": 0.0, "words": 0,
                   "voice_tracked": p.voice_consent}
             for pid, p in roster.items() if not p.is_instructor}
    for c in contribs:
        if c.kind == "student" and c.speaker_id in stats:
            s = stats[c.speaker_id]
            s["turns"] += 1
            s["talk_seconds"] = round(s["talk_seconds"] + c.seconds, 1)
            s["words"] += len(c.text.split())
    return stats
