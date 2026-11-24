"""Attendance from a camera facing the class.

Frames are sampled every few seconds. Each face found is matched against the
consented face gallery; a person needs `min_sightings` confident matches to count as
present. From the first and last sighting we get arrival and departure, and from those,
on time / late / left early against the scheduled class times.

Nothing visual is stored: frames are discarded after embedding, and unmatched faces
are only counted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Iterator

import numpy as np

from .config import Config
from .gallery import Gallery
from .roster import Person


@dataclass
class Sighting:
    t: float  # seconds into the recording
    score: float


@dataclass
class AttendanceRow:
    person_id: str
    name: str
    status: str  # on_time | late | absent | not_tracked
    arrived: str | None = None  # wall-clock ISO
    last_seen: str | None = None
    minutes_late: float = 0.0
    left_early: bool = False
    presence: float = 0.0  # share of sampled frames in class time where they were seen
    sightings: int = 0
    needs_review: bool = False
    note: str = ""


@dataclass
class AttendanceResult:
    rows: list[AttendanceRow]
    review: list[dict] = field(default_factory=list)  # uncertain matches, no images
    frames_sampled: int = 0
    max_faces_in_frame: int = 0
    max_unidentified_in_frame: int = 0


def sample_video(path: str, every_s: float) -> Iterator[tuple[float, np.ndarray]]:
    """Frames every `every_s` seconds by seeking. (Measured on a 2-hour 1080p class: seeking
    to 1,440 frames took 72 s, a sequential ffmpeg pass 83 s, so seeking stays.)"""
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = n / fps if n else None
    t = 0.0
    try:
        while duration is None or t <= duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            yield t, frame
            t += every_s
    finally:
        cap.release()


def take_attendance(
    frames: Iterable[tuple[float, np.ndarray]],
    face_backend,
    gallery: Gallery,
    roster: dict[str, Person],
    recorded_at: datetime,
    class_start: datetime,
    class_end: datetime,
    cfg: Config,
) -> AttendanceResult:
    gallery = gallery.restrict_to_consented(roster)
    seen: dict[str, list[Sighting]] = {}
    review: list[dict] = []
    res = AttendanceResult(rows=[])
    in_class_frames = 0
    seen_in_class: dict[str, int] = {}
    start_off = (class_start - recorded_at).total_seconds()
    end_off = (class_end - recorded_at).total_seconds()
    last_t = 0.0

    for t, frame in frames:
        last_t = t
        res.frames_sampled += 1
        in_class = start_off <= t <= end_off
        in_class_frames += in_class
        faces = face_backend.faces(frame)
        res.max_faces_in_frame = max(res.max_faces_in_frame, len(faces))
        unidentified = 0
        best_in_frame: dict[str, float] = {}
        for f in faces:
            m = gallery.match(f.embedding, cfg.face_threshold, cfg.face_margin)
            if m.accepted:
                if m.person_id in best_in_frame:
                    # The same person matched twice in one frame: one of them is wrong.
                    review.append({"t": t, "kind": "duplicate_in_frame", "candidate": m.person_id,
                                   "score": round(m.score, 3)})
                best_in_frame[m.person_id] = max(best_in_frame.get(m.person_id, 0.0), m.score)
            else:
                unidentified += 1
                if m.candidate and m.score >= cfg.face_review_floor:
                    review.append({"t": t, "kind": "uncertain_face", "candidate": m.candidate,
                                   "score": round(m.score, 3), "runner_up": round(m.runner_up, 3)})
        res.max_unidentified_in_frame = max(res.max_unidentified_in_frame, unidentified)
        for pid, score in best_in_frame.items():
            seen.setdefault(pid, []).append(Sighting(t, score))
            if in_class:
                seen_in_class[pid] = seen_in_class.get(pid, 0) + 1

    covers_end = last_t >= end_off - cfg.frame_every_s
    wall = lambda off: (recorded_at + timedelta(seconds=off)).isoformat(timespec="seconds")

    for pid, p in sorted(roster.items(), key=lambda kv: kv[1].name):
        if p.is_instructor:
            continue
        if not p.face_consent:
            res.rows.append(AttendanceRow(pid, p.name, "not_tracked",
                                          note="no face consent: mark by hand"))
            continue
        if pid not in gallery.people():
            res.rows.append(AttendanceRow(pid, p.name, "not_tracked", needs_review=True,
                                          note="consented but not enrolled"))
            continue
        s = seen.get(pid, [])
        if len(s) < cfg.min_sightings:
            row = AttendanceRow(pid, p.name, "absent", sightings=len(s))
            if s:
                row.needs_review = True
                row.note = "seen once only"
            res.rows.append(row)
            continue
        first, last = s[0].t, s[-1].t
        late_min = max(0.0, (first - start_off) / 60.0)
        status = "late" if late_min > cfg.late_grace_min else "on_time"
        left_early = covers_end and last < end_off - cfg.leave_grace_min * 60
        res.rows.append(AttendanceRow(
            pid, p.name, status,
            arrived=wall(first), last_seen=wall(last),
            minutes_late=round(late_min, 1) if status == "late" else 0.0,
            left_early=left_early,
            presence=round(seen_in_class.get(pid, 0) / in_class_frames, 2) if in_class_frames else 0.0,
            sightings=len(s),
        ))

    flagged = {r["candidate"] for r in review if r["kind"] == "duplicate_in_frame"}
    for row in res.rows:
        if row.person_id in flagged:
            row.needs_review = True
            row.note = (row.note + "; " if row.note else "") + "matched twice in one frame"
    res.review = review
    return res
