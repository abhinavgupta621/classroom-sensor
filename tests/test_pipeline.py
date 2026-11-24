"""Logic tests with fake models: no network, no real faces or voices."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from classroom.attendance import take_attendance
from classroom.backends import DetectedFace, Word
from classroom.config import Config
from classroom.contribution import SR, build_contributions, label_words, student_stats
from classroom.gallery import Gallery
from classroom.report import render_session, term_summary
from classroom.roster import load_roster
from classroom.scoring import score
from classroom.session import cross_check, purge_person, purge_session, session_dir, write_session

DIM = 8
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def onehot(i, noise=0.0):
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    return v + noise


@pytest.fixture
def roster(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text(
        "person_id,name,role,face_consent,voice_consent\n"
        "p1,Ada,student,yes,yes\n"
        "p2,Ben,student,yes,yes\n"
        "p3,Cy,student,no,no\n"      # opted out of both
        "p4,Di,student,yes,yes\n"
        "prof,Prof Ng,instructor,yes,yes\n"
    )
    return load_roster(p)


def gallery(kind):
    g = Gallery(kind)
    for i, pid in enumerate(["p1", "p2", "p3", "p4", "prof"]):
        g.add(pid, onehot(i))
    return g


def test_roster_rejects_bad_consent(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("person_id,name,role,face_consent,voice_consent\nx,X,student,maybe,yes\n")
    with pytest.raises(ValueError, match="face_consent"):
        load_roster(p)


def test_gallery_threshold_margin_and_consent(roster):
    g = gallery("face")
    assert g.match(onehot(0), 0.4, 0.05).person_id == "p1"
    halfway = onehot(0) + onehot(1)  # equally like Ada and Ben: must not pick one
    m = g.match(halfway, 0.4, 0.05)
    assert not m.accepted and m.candidate in {"p1", "p2"}
    assert "p3" not in g.restrict_to_consented(roster).people()
    # Cy's template on disk is ignored at match time because consent is withdrawn.
    assert g.restrict_to_consented(roster).match(onehot(2), 0.4, 0.05).person_id is None


class ScriptFaces:
    """frames are dicts {t: [face index, ...]}; the 'image' is just the timestamp."""

    def __init__(self, script):
        self.script = script

    def faces(self, t):
        return [DetectedFace(onehot(i), (0, 0, 40, 40), 0.9) for i in self.script.get(t, [])]


def test_attendance_statuses(roster):
    cfg = Config(frame_every_s=60)
    # Recording starts 5 min early; class 9:00-10:00 (offsets 300..3900 s).
    times = [i * 60.0 for i in range(0, 66)]
    script = {}
    for t in times:
        faces = []
        if t >= 240:
            faces.append(0)  # Ada: early, stays
        if t >= 300 + 20 * 60:
            faces.append(1)  # Ben: 20 min late
        if t == 600:
            faces.append(3)  # Di: seen once only
        script[t] = faces
    script[1200] = script[1200] + [0]  # Ada matched twice in one frame
    res = take_attendance(((t, t) for t in times), ScriptFaces(script), gallery("face"), roster,
                          recorded_at=T0 - timedelta(minutes=5), class_start=T0,
                          class_end=T0 + timedelta(hours=1), cfg=cfg)
    rows = {r.person_id: r for r in res.rows}
    assert "prof" not in rows
    assert rows["p1"].status == "on_time" and rows["p1"].presence == 1.0
    assert rows["p1"].needs_review and "twice" in rows["p1"].note
    assert rows["p2"].status == "late" and rows["p2"].minutes_late == 20.0
    assert rows["p3"].status == "not_tracked"
    assert rows["p4"].status == "absent" and rows["p4"].needs_review


def test_left_early(roster):
    cfg = Config(frame_every_s=60)
    times = [i * 60.0 for i in range(0, 61)]
    script = {t: [0] + ([1] if t <= 1800 else []) for t in times}
    res = take_attendance(((t, t) for t in times), ScriptFaces(script), gallery("face"), roster,
                          T0, T0, T0 + timedelta(hours=1), cfg)
    rows = {r.person_id: r for r in res.rows}
    assert rows["p2"].left_early and not rows["p1"].left_early


class SampleVoices:
    """Audio samples carry the speaker index; the 'voiceprint' is the majority index."""

    def embed(self, clip):
        vals = np.round(clip).astype(int)
        return onehot(int(np.bincount(vals, minlength=DIM).argmax()))


def speech(segments, total_s):
    audio = np.full(int(total_s * SR), 7.0, dtype=np.float32)  # 7 = nobody enrolled
    words = []
    for spk, s, e, text in segments:
        audio[int(s * SR):int(e * SR)] = spk
        toks = text.split()
        step = (e - s) / len(toks)
        words += [Word(s + k * step, s + (k + 1) * step - 0.05, " " + tok) for k, tok in enumerate(toks)]
    return words, audio


def test_contributions_split_handoff_without_pause(roster):
    cfg = Config()
    words, audio = speech([
        (4, 0.0, 6.0, "so what would you do about the supplier problem here"),
        (0, 6.0, 14.0, "I would renegotiate because their margin is thin and they need volume"),  # no pause
        (1, 15.5, 21.0, "building on Ada the volume lever only works if demand holds"),
        (2, 23.0, 28.0, "I think we should also look at a second source"),  # Cy: no voice consent
        (0, 30.0, 30.6, "yes"),  # too short to identify
    ], 32)
    g = gallery("voice").restrict_to_consented(roster)
    contribs = build_contributions(label_words(words, audio, SampleVoices(), g, cfg), roster, cfg)
    kinds = [(c.kind, c.speaker_id) for c in contribs]
    assert kinds[0] == ("instructor", "prof")
    assert ("student", "p1") in kinds and ("student", "p2") in kinds
    assert ("unknown", None) in kinds  # Cy is never named
    assert kinds[-1] == ("short", None)
    ada = next(c for c in contribs if c.speaker_id == "p1")
    assert "I would renegotiate" in ada.text and "supplier" not in ada.text
    assert 5.0 <= ada.start <= 7.0
    stats = student_stats(contribs, roster)
    assert stats["p1"]["turns"] == 1 and stats["p4"]["turns"] == 0
    assert not stats["p3"]["voice_tracked"]


def test_smoothing_stops_unconsented_voice_flickering_onto_a_classmate():
    # Seen in the real smoke test: an unenrolled speaker's 10 s turn came out as
    # unknown / Ben / unknown / Ben in one-second pieces.
    from classroom.contribution import UNKNOWN, _smooth

    words = [Word(float(i), i + 0.9, f" w{i}") for i in range(10)]
    labels = [UNKNOWN, UNKNOWN, "p2", UNKNOWN, UNKNOWN, UNKNOWN, "p2", UNKNOWN, UNKNOWN, "p2"]
    out = _smooth([(w, l, None) for w, l in zip(words, labels)], 2.0)
    assert {l for _, l, _ in out} == {UNKNOWN}
    # A real hand-off (two long runs) is left alone.
    labels = ["p1"] * 5 + ["p2"] * 5
    out = _smooth([(w, l, None) for w, l in zip(words, labels)], 2.0)
    assert [l for _, l, _ in out] == labels


class FakeStream:
    def __init__(self, payload, stop="end_turn"):
        self.msg = SimpleNamespace(stop_reason=stop, model="claude-opus-5-5",
                                   content=[SimpleNamespace(type="text", text=json.dumps(payload))])
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    def __enter__(self):
        return SimpleNamespace(get_final_message=lambda: self.msg)

    def __exit__(self, *a):
        return False


def fake_client(stream):
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))


def _contribs(roster):
    cfg = Config()
    words, audio = speech([(4, 0, 4, "what is the risk here"), (0, 5, 10, "the supplier could walk away tomorrow"),
                           (1, 11, 16, "Ada is right and the contract has no exit fee")], 17)
    return build_contributions(label_words(words, audio, SampleVoices(), gallery("voice"), cfg), roster, cfg)


def test_scoring_clamps_and_ignores_unknown_ids(roster):
    contribs = _contribs(roster)
    ids = [c.id for c in contribs if c.kind == "student"]
    payload = {"contributions": [
        {"id": ids[0], "relevance": 9, "evidence": 3, "builds_on_others": 1, "insight": 4, "summary": "s", "rationale": "r"},
        {"id": ids[1], "relevance": 4, "evidence": 4, "builds_on_others": 5, "insight": 3, "summary": "s", "rationale": "r"},
        {"id": "c999", "relevance": 5, "evidence": 5, "builds_on_others": 5, "insight": 5, "summary": "x", "rationale": "x"},
    ], "session_themes": ["supplier risk"]}
    stream = FakeStream(payload)
    out = score(contribs, Config(), client=fake_client(stream))
    assert set(out["scores"]) == set(ids)
    assert out["scores"][ids[0]]["relevance"] == 5
    assert out["scores"][ids[1]]["mean"] == 4.0
    k = stream.kwargs
    assert k["model"] == "claude-opus-5-5" and k["fallbacks"] == "default"
    assert k["output_config"]["format"]["type"] == "json_schema"
    assert "Prof Ng" not in k["messages"][0]["content"]  # instructor shown by role only


def test_scoring_refusal_raises(roster):
    with pytest.raises(RuntimeError, match="declined"):
        score(_contribs(roster), Config(), client=fake_client(FakeStream({}, stop="refusal")))


def test_session_files_report_term_and_purge(tmp_path, roster):
    cfg = Config(data_dir=tmp_path / "data", frame_every_s=60)
    times = [i * 60.0 for i in range(0, 61)]
    script = {t: [0, 1, 3] for t in times}
    att = take_attendance(((t, t) for t in times), ScriptFaces(script), gallery("face"), roster,
                          T0, T0, T0 + timedelta(hours=1), cfg)
    contribs = _contribs(roster)
    cross_check(att, contribs)
    meta = {"course": "CORE", "session_id": "s1", "class_start": T0.isoformat(),
            "class_end": (T0 + timedelta(hours=1)).isoformat(), "start_offset_s": 0}
    out = session_dir(cfg, "CORE", "s1")
    summary = write_session(out, meta, att, contribs, None, roster)
    page = render_session(summary)
    assert "Here but haven&#x27;t spoken (1)" in page or "haven't spoken (1)" in page
    assert "Di" in page and (out / "attendance.csv").exists()
    write_session(session_dir(cfg, "CORE", "s2"), {**meta, "session_id": "s2"}, att, [], None, roster)
    term = {r["person_id"]: r for r in term_summary(cfg.data_dir / "sessions" / "CORE")}
    assert term["p1"]["present"] == 2 and term["p1"]["sessions_since_spoke"] == 1
    assert term["p4"]["sessions_since_spoke"] == 2
    assert purge_session(cfg, "CORE", "s1") and not out.exists()
    gallery("face").save(cfg.data_dir / "galleries" / "face.npz")
    assert purge_person(cfg, "p1")["face"] is True
    assert "p1" not in Gallery.load("face", cfg.data_dir / "galleries" / "face.npz").people()
    log = (cfg.data_dir / "audit.log").read_text()
    assert "purge_person" in log and "Ada" not in log


def test_session_dir_rejects_path_tricks(tmp_path):
    with pytest.raises(ValueError):
        session_dir(Config(data_dir=tmp_path), "CORE", "../../etc")
