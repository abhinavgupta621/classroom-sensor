"""Command line.

    python -m classroom enroll-faces  --roster roster.csv --photos enroll/faces/
    python -m classroom enroll-voices --roster roster.csv --clips  enroll/voices/
    python -m classroom session --roster roster.csv --course CORE --session-id 2026-12-01 \\
        --video room.mp4 [--audio room.wav] --recorded-at 2026-12-01T08:55 \\
        --start 2026-12-01T09:00 --end 2026-12-01T10:30 [--no-score] [--context "Case: ..."]
    python -m classroom term-report --course CORE
    python -m classroom purge-session --course CORE --session-id 2026-12-01
    python -m classroom purge-person --person-id 3034...

Enrollment files are named by person id: <person_id>.jpg, <person_id>_2.jpg, <person_id>.wav ...
Times without a UTC offset are read as the machine's local time.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import Config
from .gallery import Gallery
from .roster import load_roster

IMG = {".jpg", ".jpeg", ".png", ".webp"}
AUD = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4"}


def _when(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.astimezone()


def _files_by_person(folder: Path, exts: set[str], roster) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in exts:
            continue
        pid = f.stem.split("_")[0]
        if pid in roster:
            out.setdefault(pid, []).append(f)
        else:
            print(f"  skip {f.name}: {pid} is not on the roster", file=sys.stderr)
    return out


def enroll_faces(args, cfg: Config) -> int:
    import cv2

    from .backends.face_opencv import OpenCVFaces
    from .session import audit, galleries_dir

    roster = load_roster(args.roster)
    path = galleries_dir(cfg) / "face.npz"
    gallery = Gallery.load("face", path)
    backend = OpenCVFaces(cfg.model_cache)
    enrolled = skipped = 0
    for pid, files in _files_by_person(Path(args.photos), IMG, roster).items():
        if not roster[pid].face_consent:
            print(f"  skip {pid}: no face consent")
            skipped += 1
            continue
        gallery.remove(pid)  # re-enrolling replaces, never accumulates stale photos
        for f in files:
            img = cv2.imread(str(f))
            faces = backend.faces(img) if img is not None else []
            if len(faces) != 1:
                print(f"  skip {f.name}: found {len(faces)} faces, need exactly 1")
                continue
            gallery.add(pid, faces[0].embedding)
        enrolled += pid in gallery.people()
    gallery.save(path)
    audit(cfg, "enroll_faces", enrolled=enrolled, skipped_no_consent=skipped, total=len(gallery))
    print(f"face gallery: {len(gallery)} people ({enrolled} enrolled now)")
    return 0


def enroll_voices(args, cfg: Config) -> int:
    from .backends.speech import SR, EcapaVoices, load_audio

    from .session import audit, galleries_dir

    roster = load_roster(args.roster)
    path = galleries_dir(cfg) / "voice.npz"
    gallery = Gallery.load("voice", path)
    backend = EcapaVoices(cfg.model_cache)
    enrolled = skipped = 0
    for pid, files in _files_by_person(Path(args.clips), AUD, roster).items():
        if not roster[pid].voice_consent:
            print(f"  skip {pid}: no voice consent")
            skipped += 1
            continue
        gallery.remove(pid)
        for f in files:
            audio = load_audio(f)
            if len(audio) < SR * 10:
                print(f"  skip {f.name}: under 10 seconds of audio")
                continue
            # Several 6-second pieces make a steadier voiceprint than one long clip.
            step = SR * 6
            for i in range(0, len(audio) - step + 1, step):
                gallery.add(pid, backend.embed(audio[i:i + step]))
        enrolled += pid in gallery.people()
    gallery.save(path)
    audit(cfg, "enroll_voices", enrolled=enrolled, skipped_no_consent=skipped, total=len(gallery))
    print(f"voice gallery: {len(gallery)} people ({enrolled} enrolled now)")
    return 0


def run_session(args, cfg: Config) -> int:
    from .report import render_session
    from .session import audit, cross_check, galleries_dir, session_dir, write_session

    roster = load_roster(args.roster)
    recorded_at, start, end = _when(args.recorded_at), _when(args.start), _when(args.end)
    if not recorded_at <= end or not start < end:
        print("times are out of order: need recorded-at <= end and start < end", file=sys.stderr)
        return 2
    out = session_dir(cfg, args.course, args.session_id)
    att = contribs = scored = None

    if args.video:
        from .attendance import sample_video, take_attendance
        from .backends.face_opencv import OpenCVFaces

        print("attendance: sampling the room camera…")
        att = take_attendance(sample_video(args.video, cfg.frame_every_s), OpenCVFaces(cfg.model_cache),
                              Gallery.load("face", galleries_dir(cfg) / "face.npz"),
                              roster, recorded_at, start, end, cfg)

    audio = args.audio or args.video
    if audio and not args.no_audio:
        from .backends.speech import EcapaVoices, WhisperTranscriber
        from .contribution import contribute

        print("contributions: transcribing and matching voices…")
        contribs = contribute(audio, WhisperTranscriber(cfg.whisper_model, cfg.device),
                              EcapaVoices(cfg.model_cache), Gallery.load("voice", galleries_dir(cfg) / "voice.npz"),
                              roster, cfg)
        if att is not None:
            cross_check(att, contribs)
        if not args.no_score:
            from .scoring import score

            print("scoring contributions with Claude…")
            try:
                scored = score(contribs, cfg, args.context or "")
            except Exception as e:  # the rest of the report is still useful
                print(f"  scoring skipped: {e}", file=sys.stderr)

    meta = {"course": args.course, "session_id": args.session_id,
            "recorded_at": recorded_at.isoformat(), "class_start": start.isoformat(),
            "class_end": end.isoformat(),
            "start_offset_s": (start - recorded_at).total_seconds()}
    summary = write_session(out, meta, att, contribs, scored, roster)
    (out / "report.html").write_text(render_session(summary), encoding="utf-8")
    audit(cfg, "session", course=args.course, session_id=args.session_id,
          attendance_rows=len(att.rows) if att else 0, contributions=len(contribs or []),
          scored=bool(scored and scored.get("scores")))
    print(f"wrote {out}/report.html")
    return 0


def term_report(args, cfg: Config) -> int:
    from .report import term_summary

    root = cfg.data_dir / "sessions" / args.course
    rows = term_summary(root)
    if not rows:
        print("no sessions yet")
        return 1
    out = root / "term.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="classroom")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enroll-faces"); p.add_argument("--roster", required=True); p.add_argument("--photos", required=True)
    p = sub.add_parser("enroll-voices"); p.add_argument("--roster", required=True); p.add_argument("--clips", required=True)
    p = sub.add_parser("session")
    for a in ("--roster", "--course", "--session-id", "--recorded-at", "--start", "--end"):
        p.add_argument(a, required=True)
    p.add_argument("--video"); p.add_argument("--audio"); p.add_argument("--context")
    p.add_argument("--no-score", action="store_true"); p.add_argument("--no-audio", action="store_true")
    p.add_argument("--whisper-model", help="default large-v3; small.en is fine for a quick test")
    p.add_argument("--device", help="auto, cpu or cuda")
    p = sub.add_parser("check-recording", help="is a room's recording good enough? numbers only, no identities")
    p.add_argument("--video"); p.add_argument("--audio"); p.add_argument("--out", type=Path)
    p.add_argument("--whisper-model"); p.add_argument("--device")
    p = sub.add_parser("term-report"); p.add_argument("--course", required=True)
    p = sub.add_parser("purge-session"); p.add_argument("--course", required=True); p.add_argument("--session-id", required=True)
    p = sub.add_parser("purge-person"); p.add_argument("--person-id", required=True)

    args = ap.parse_args(argv)
    cfg = Config(data_dir=args.data_dir)
    if getattr(args, "whisper_model", None):
        cfg.whisper_model = args.whisper_model
    if getattr(args, "device", None):
        cfg.device = args.device
    if args.cmd == "enroll-faces":
        return enroll_faces(args, cfg)
    if args.cmd == "enroll-voices":
        return enroll_voices(args, cfg)
    if args.cmd == "session":
        if not (args.video or args.audio):
            ap.error("session needs --video, --audio or both")
        return run_session(args, cfg)
    if args.cmd == "term-report":
        return term_report(args, cfg)
    if args.cmd == "check-recording":
        from .check import run
        res = run(args.video, args.audio, cfg, args.out)
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "timeline"} for k, v in res.items()}, indent=2))
        return 0
    if args.cmd == "purge-session":
        from .session import purge_session
        print("deleted" if purge_session(cfg, args.course, args.session_id) else "no such session")
        return 0
    if args.cmd == "purge-person":
        from .session import purge_person
        print(purge_person(cfg, args.person_id))
        return 0
    return 1
