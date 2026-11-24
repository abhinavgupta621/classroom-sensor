"""One class session end to end, plus storage, the audit log and deletion."""
from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .attendance import AttendanceResult
from .config import Config
from .contribution import Contribution, student_stats
from .gallery import Gallery
from .roster import Person


def galleries_dir(cfg: Config) -> Path:
    return cfg.data_dir / "galleries"


def session_dir(cfg: Config, course: str, session_id: str) -> Path:
    for part in (course, session_id):
        if not part or "/" in part or part.startswith("."):
            raise ValueError(f"bad course or session id: {part!r}")
    return cfg.data_dir / "sessions" / course / session_id


def audit(cfg: Config, event: str, **fields) -> None:
    """Who-ran-what log. Counts and ids only; never embeddings, names or speech."""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
    with open(cfg.data_dir / "audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def cross_check(att: AttendanceResult, contribs: list[Contribution]) -> None:
    """Someone heard speaking but not seen is probably a missed face, not an absence."""
    spoke = {c.speaker_id for c in contribs if c.kind == "student"}
    for row in att.rows:
        if row.status == "absent" and row.person_id in spoke:
            row.needs_review = True
            row.note = (row.note + "; " if row.note else "") + "heard speaking but not seen"


def write_session(out: Path, meta: dict, att: AttendanceResult | None,
                  contribs: list[Contribution] | None, scored: dict | None,
                  roster: dict[str, Person]) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    summary = {"meta": meta}
    if att is not None:
        rows = [asdict(r) for r in att.rows]
        with open(out / "attendance.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["person_id"])
            w.writeheader()
            w.writerows(rows)
        summary["attendance"] = {"rows": rows, "review": att.review,
                                 "frames_sampled": att.frames_sampled,
                                 "max_faces_in_frame": att.max_faces_in_frame,
                                 "max_unidentified_in_frame": att.max_unidentified_in_frame}
    if contribs is not None:
        scores = (scored or {}).get("scores", {})
        dims = (scored or {}).get("dims", [])
        rows = []
        for c in contribs:
            d = c.to_dict()
            s = scores.get(c.id, {})
            d.update({k: s.get(k) for k in dims + ["mean", "summary", "rationale"]})
            rows.append(d)
        with open(out / "contributions.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["id"])
            w.writeheader()
            w.writerows(rows)
        stats = student_stats(contribs, roster)
        for c in contribs:
            s = scores.get(c.id)
            if s and c.speaker_id in stats:
                stats[c.speaker_id].setdefault("_means", []).append(s["mean"])
        for st in stats.values():
            means = st.pop("_means", [])
            st["avg_score"] = round(sum(means) / len(means), 2) if means else None
        summary["contributions"] = rows
        summary["students"] = stats
        summary["scoring"] = {k: v for k, v in (scored or {}).items() if k != "scores"}
    (out / "session.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def purge_session(cfg: Config, course: str, session_id: str) -> bool:
    d = session_dir(cfg, course, session_id)
    if not d.exists():
        return False
    shutil.rmtree(d)
    audit(cfg, "purge_session", course=course, session_id=session_id)
    return True


def purge_person(cfg: Config, person_id: str) -> dict:
    """Deletes a person's face and voice templates. Past session files still name them;
    remove those with purge_session or by editing the session CSVs."""
    removed = {}
    for kind in ("face", "voice"):
        path = galleries_dir(cfg) / f"{kind}.npz"
        g = Gallery.load(kind, path)
        removed[kind] = g.remove(person_id)
        if removed[kind]:
            g.save(path)
    audit(cfg, "purge_person", person_id=person_id, **removed)
    return removed
