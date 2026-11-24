"""The instructor's view: one HTML page per session, and a term summary across sessions.

Built for the instructor only. It leads with who to bring in (people who haven't
spoken), not a leaderboard, and marks anything uncertain for review.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

CSS = """
:root{--bg:#fbfaf7;--fg:#1d2330;--mut:#667085;--line:#e6e2d8;--acc:#003262;--gold:#fdb515;
--warn:#b54708;--warnbg:#fff4e5}
@media (prefers-color-scheme:dark){:root{--bg:#14171d;--fg:#e8eaee;--mut:#9aa3b2;--line:#2a303a;
--acc:#8fb8ff;--warn:#ffb86b;--warnbg:#3a2a16}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px;color:var(--acc)}
.sub{color:var(--mut);margin:0 0 20px}.draft{background:var(--warnbg);color:var(--warn);
padding:8px 12px;border-radius:8px;margin:0 0 20px;font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{border:1px solid var(--line);border-radius:10px;padding:12px}
.tile b{display:block;font-size:24px}.tile span{color:var(--mut);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600}.rev{color:var(--warn);font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;border:1px solid var(--line);font-size:12px}
.quiet{display:flex;flex-wrap:wrap;gap:6px}.quiet span{border:1px solid var(--line);border-radius:99px;padding:2px 10px}
.wrap{overflow-x:auto}
"""


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _clock(iso: str | None) -> str:
    return iso[11:16] if iso else "—"


def render_session(summary: dict) -> str:
    m = summary["meta"]
    parts = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>{_e(m['course'])} {_e(m['session_id'])}</title><style>{CSS}</style><main>",
             f"<h1>{_e(m['course'])} · {_e(m['session_id'])}</h1>",
             f"<p class=sub>{_e(m.get('class_start','')[:16].replace('T',' '))} – {_clock(m.get('class_end'))}</p>",
             "<p class=draft>Draft from automatic matching. Rows marked <b>review</b> need a look before "
             "anything is recorded. Scores are suggestions, not grades.</p>"]

    att = summary.get("attendance")
    students = summary.get("students", {})
    if att:
        rows = att["rows"]
        count = lambda s: sum(r["status"] == s for r in rows)
        review_n = sum(r["needs_review"] for r in rows)
        parts.append("<div class=tiles>" + "".join(
            f"<div class=tile><b>{v}</b><span>{k}</span></div>" for k, v in [
                ("on time", count("on_time")), ("late", count("late")), ("absent", count("absent")),
                ("not tracked", count("not_tracked")), ("to review", review_n)]) + "</div>")
    if students:
        # With attendance, only people actually in the room count as quiet.
        present = ({r["person_id"] for r in att["rows"] if r["status"] in ("on_time", "late")}
                   if att else set(students))
        quiet = [s["name"] for pid, s in students.items()
                 if s["voice_tracked"] and s["turns"] == 0 and pid in present]
        parts.append(f"<h2>Here but haven't spoken ({len(quiet)})</h2>")
        parts.append("<div class=quiet>" + "".join(f"<span>{_e(n)}</span>" for n in sorted(quiet)) + "</div>"
                     if quiet else "<p class=sub>Everyone present spoke.</p>")

    if att:
        parts.append("<h2>Attendance</h2><div class=wrap><table><tr><th>Name</th><th>Status</th>"
                     "<th>Arrived</th><th>Last seen</th><th>Present</th><th></th></tr>")
        order = {"absent": 0, "late": 1, "not_tracked": 2, "on_time": 3}
        for r in sorted(att["rows"], key=lambda r: (not r["needs_review"], order[r["status"]], r["name"])):
            status = r["status"].replace("_", " ")
            if r["status"] == "late":
                status += f" ({r['minutes_late']:g} min)"
            if r["left_early"]:
                status += ", left early"
            flag = "<span class=rev>review</span> " if r["needs_review"] else ""
            parts.append(f"<tr><td>{_e(r['name'])}</td><td>{_e(status)}</td><td>{_clock(r['arrived'])}</td>"
                         f"<td>{_clock(r['last_seen'])}</td><td>{int(r['presence']*100)}%</td>"
                         f"<td>{flag}{_e(r['note'])}</td></tr>")
        parts.append("</table></div>")

    if students:
        parts.append("<h2>Participation</h2><div class=wrap><table><tr><th>Name</th><th>Turns</th>"
                     "<th>Talk time</th><th>Avg score</th></tr>")
        for s in sorted(students.values(), key=lambda s: (-s["turns"], s["name"])):
            if not s["voice_tracked"]:
                continue
            avg = "—" if s.get("avg_score") is None else f"{s['avg_score']:.1f}"
            parts.append(f"<tr><td>{_e(s['name'])}</td><td>{s['turns']}</td>"
                         f"<td>{int(s['talk_seconds']//60)}:{int(s['talk_seconds']%60):02d}</td><td>{avg}</td></tr>")
        parts.append("</table></div>")
        untracked = sorted(s["name"] for s in students.values() if not s["voice_tracked"])
        if untracked:
            parts.append(f"<p class=sub>Not voice-tracked (no consent): {_e(', '.join(untracked))}.</p>")

    contribs = [c for c in summary.get("contributions", []) if c["kind"] == "student"]
    if contribs:
        themes = summary.get("scoring", {}).get("session_themes") or []
        parts.append("<h2>What students said</h2>")
        if themes:
            parts.append("<p class=sub>Themes: " + _e("; ".join(themes)) + "</p>")
        parts.append("<div class=wrap><table><tr><th>When</th><th>Who</th><th>Summary</th><th>Score</th></tr>")
        t0 = float(m.get("start_offset_s", 0.0))  # minutes count from the scheduled start
        for c in contribs:
            mm = max(0, int((c["start"] - t0) // 60))
            summ = c.get("summary") or (c["text"][:180] + ("…" if len(c["text"]) > 180 else ""))
            flag = " <span class=rev>review</span>" if c["needs_review"] else ""
            sc = "—" if c.get("mean") is None else f"{c['mean']:.1f}"
            parts.append(f"<tr><td>{mm}m</td><td>{_e(c['speaker_name'])}{flag}</td>"
                         f"<td title='{_e(c['text'])}'>{_e(summ)}</td><td>{sc}</td></tr>")
        parts.append("</table></div>")
    parts.append("</main>")
    return "".join(parts)


def term_summary(sessions_root: Path) -> list[dict]:
    """Per student across every session of one course: attendance, lateness,
    participation and sessions since they last spoke."""
    sessions = sorted(p for p in sessions_root.iterdir() if (p / "session.json").exists())
    people: dict[str, dict] = {}
    for idx, sdir in enumerate(sessions):
        s = json.loads((sdir / "session.json").read_text(encoding="utf-8"))
        for r in s.get("attendance", {}).get("rows", []):
            p = people.setdefault(r["person_id"], {"person_id": r["person_id"], "name": r["name"],
                                                   "sessions": 0, "present": 0, "late": 0, "left_early": 0,
                                                   "turns": 0, "scores": [], "last_spoke": None})
            p["sessions"] += 1
            p["present"] += r["status"] in ("on_time", "late")
            p["late"] += r["status"] == "late"
            p["left_early"] += bool(r["left_early"])
        for pid, st in s.get("students", {}).items():
            p = people.setdefault(pid, {"person_id": pid, "name": st["name"], "sessions": 0, "present": 0,
                                        "late": 0, "left_early": 0, "turns": 0, "scores": [], "last_spoke": None})
            p["turns"] += st["turns"]
            if st["turns"]:
                p["last_spoke"] = idx
            if st.get("avg_score") is not None:
                p["scores"].append(st["avg_score"])
    out = []
    for p in people.values():
        scores = p.pop("scores")
        last = p.pop("last_spoke")
        p["avg_score"] = round(sum(scores) / len(scores), 2) if scores else None
        p["sessions_since_spoke"] = len(sessions) if last is None else len(sessions) - 1 - last
        out.append(p)
    return sorted(out, key=lambda p: p["name"])
