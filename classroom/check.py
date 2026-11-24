"""Is this room's recording good enough for the pilot? Measured without identifying anyone.

Camera: samples frames, detects faces, and measures how big they are. Recognition needs
about 24 px across at minimum and works much better from 40 px. Faces are then
grouped by similarity (no names, nothing saved) to estimate how many different people
the camera ever captures clearly.

Audio: transcribes, splits into turns, groups turns by voice (again no names) and takes
the biggest group, by talk time, as the instructor. It then compares everyone else's
speech with the instructor's on loudness and transcription confidence, and counts how
many of their turns are long enough (3 s or more) for a voiceprint.

Nothing visual or audio is written to disk; the output is numbers only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SIZE_BUCKETS = [(0, 24), (24, 40), (40, 64), (64, 10_000)]


def _cluster(embs: np.ndarray, threshold: float) -> np.ndarray:
    """Greedy agglomerative grouping by cosine similarity to group centroids."""
    labels = np.full(len(embs), -1)
    cents: list[np.ndarray] = []
    counts: list[int] = []
    for i, e in enumerate(embs):
        if cents:
            sims = np.array([c @ e for c in cents])
            k = int(sims.argmax())
            if sims[k] >= threshold:
                labels[i] = k
                c = cents[k] * counts[k] + e
                cents[k] = c / np.linalg.norm(c)
                counts[k] += 1
                continue
        labels[i] = len(cents)
        cents.append(e)
        counts.append(1)
    return labels


def check_camera(video: str, face_backend, every_s: float = 5.0, audience_min_faces: int = 3,
                 cluster_threshold: float = 0.45) -> dict:
    from .attendance import sample_video

    frames = 0
    audience_frames = 0
    per_frame_recognisable = []
    sizes = []
    embs = []
    timeline = []
    for t, img in sample_video(video, every_s):
        frames += 1
        faces = face_backend.faces(img)
        s = [min(f.box[2], f.box[3]) for f in faces]
        sizes += s
        rec = [f for f in faces if min(f.box[2], f.box[3]) >= 40]
        per_frame_recognisable.append(len(rec))
        embs += [f.embedding / np.linalg.norm(f.embedding) for f in rec]
        is_aud = len(faces) >= audience_min_faces
        audience_frames += is_aud
        timeline.append((round(t), len(faces), len(rec)))
    sizes_a = np.array(sizes) if sizes else np.zeros(0)
    buckets = {f"{lo}-{hi if hi < 10_000 else ''}px": int(((sizes_a >= lo) & (sizes_a < hi)).sum())
               for lo, hi in SIZE_BUCKETS}
    distinct = 0
    seen_often = 0
    if embs:
        labels = _cluster(np.stack(embs), cluster_threshold)
        _, counts = np.unique(labels, return_counts=True)
        distinct = int(len(counts))
        seen_often = int((counts >= 3).sum())
    pf = np.array(per_frame_recognisable) if per_frame_recognisable else np.zeros(1)
    return {
        "frames_sampled": frames,
        "sample_every_s": every_s,
        "share_of_time_students_on_screen": round(audience_frames / frames, 3) if frames else 0,
        "faces_detected": int(len(sizes_a)),
        "face_size_buckets": buckets,
        "share_faces_recognisable_40px": round(float((sizes_a >= 40).mean()), 3) if len(sizes_a) else 0,
        "share_faces_borderline_24_40px": round(float(((sizes_a >= 24) & (sizes_a < 40)).mean()), 3) if len(sizes_a) else 0,
        "median_face_px": float(np.median(sizes_a)) if len(sizes_a) else 0,
        "max_recognisable_in_one_frame": int(pf.max()),
        "distinct_people_captured_clearly_est": distinct,
        "distinct_people_seen_3plus_times_est": seen_often,
        "timeline": timeline,  # (t, faces, recognisable) per sample
    }


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def face_pairs(video: str, face_backend, every_s: float = 2.0, thresholds=(0.30, 0.363, 0.40, 0.45, 0.50),
               min_px: int = 24, gallery_size: int = 70) -> dict:
    """Face-matching accuracy on this room's own footage, with no identities.

    Same-person pairs: a face and the face in the same place one sample later (students
    barely move in 2 s). Different-person pairs: two faces in the same frame. Same-seat
    pairs are easier than matching a classroom face to an enrollment photo, so the
    true-match rate here is an upper bound; the false-match rate is a fair estimate.
    """
    from .attendance import sample_video

    genuine, impostor = [], []
    gen_by_size: dict[str, list[float]] = {"24-40": [], "40-64": [], "64+": []}
    prev = None
    prev_t = None
    for t, img in sample_video(video, every_s):
        faces = [f for f in face_backend.faces(img) if min(f.box[2], f.box[3]) >= min_px]
        embs = [f.embedding / np.linalg.norm(f.embedding) for f in faces]
        for i in range(len(faces)):
            for j in range(i + 1, len(faces)):
                impostor.append(float(embs[i] @ embs[j]))
        if prev and prev_t is not None and t - prev_t <= every_s + 0.01:
            for f, e in zip(faces, embs):
                best = max(((_iou(f.box, pf.box), pe) for pf, pe in prev), key=lambda x: x[0], default=(0, None))
                if best[0] >= 0.6:
                    s = float(e @ best[1])
                    genuine.append(s)
                    px = min(f.box[2], f.box[3])
                    gen_by_size["24-40" if px < 40 else "40-64" if px < 64 else "64+"].append(s)
        prev = list(zip(faces, embs))
        prev_t = t
    g, im = np.array(genuine), np.array(impostor)
    rows = []
    for th in thresholds:
        tar = float((g >= th).mean()) if len(g) else None
        far = float((im >= th).mean()) if len(im) else None
        rows.append({"threshold": th, "true_match_rate": round(tar, 4) if tar is not None else None,
                     "false_match_rate_per_pair": round(far, 5) if far is not None else None,
                     # chance a face wrongly clears the bar against at least one of N enrolled people
                     f"false_match_vs_{gallery_size}_enrolled": round(1 - (1 - far) ** gallery_size, 4) if far is not None else None})
    return {
        "same_person_pairs": len(g), "different_person_pairs": len(im),
        "same_person_similarity_median": round(float(np.median(g)), 3) if len(g) else None,
        "different_person_similarity_p99": round(float(np.percentile(im, 99)), 3) if len(im) else None,
        "different_person_similarity_max": round(float(im.max()), 3) if len(im) else None,
        "true_match_rate_by_face_size_at_0.40": {k: (round(float((np.array(v) >= 0.40).mean()), 3), len(v))
                                                 for k, v in gen_by_size.items() if v},
        "by_threshold": rows,
    }


def check_audio(audio_path: str, voice_backend, whisper_model: str = "small.en", device: str = "auto",
                turn_gap_s: float = 0.8, cluster_threshold: float = 0.55) -> dict:
    from faster_whisper import WhisperModel

    from .backends.speech import SR, load_audio

    audio = load_audio(audio_path)
    model = WhisperModel(whisper_model, device=device)
    segs, _ = model.transcribe(audio, language="en", word_timestamps=True, vad_filter=True)
    words = [w for s in segs for w in (s.words or [])]

    turns = []
    for w in words:
        if turns and w.start - turns[-1][-1].end < turn_gap_s:
            turns[-1].append(w)
        else:
            turns.append([w])

    rows = []
    for tw in turns:
        s, e = tw[0].start, tw[-1].end
        clip = audio[int(s * SR):int(e * SR)]
        if len(clip) < SR // 2:
            continue
        rms = float(np.sqrt(np.mean(clip ** 2)) + 1e-9)
        rows.append({"start": s, "end": e, "dur": e - s, "words": len(tw),
                     "conf": float(np.mean([w.probability for w in tw])),
                     "dbfs": 20 * np.log10(rms),
                     "emb": voice_backend.embed(clip) if e - s >= 3.0 else None})

    long_rows = [r for r in rows if r["emb"] is not None]
    if not long_rows:
        return {"turns": len(rows), "note": "no turns of 3 s or more"}
    embs = np.stack([r["emb"] / np.linalg.norm(r["emb"]) for r in long_rows])
    labels = _cluster(embs, cluster_threshold)
    talk = {}
    for r, l in zip(long_rows, labels):
        talk[l] = talk.get(l, 0.0) + r["dur"]
    instr = max(talk, key=talk.get)
    instr_c = embs[labels == instr].mean(0)
    instr_c /= np.linalg.norm(instr_c)
    # Short turns: assign to instructor or not by similarity where possible; otherwise count as other.
    for r in rows:
        if r["emb"] is not None:
            r["who"] = "instructor" if float((r["emb"] / np.linalg.norm(r["emb"])) @ instr_c) >= cluster_threshold else "other"
        else:
            r["who"] = "short"

    def summ(sel):
        if not sel:
            return {"turns": 0}
        return {"turns": len(sel), "minutes": round(sum(r["dur"] for r in sel) / 60, 1),
                "median_loudness_dbfs": round(float(np.median([r["dbfs"] for r in sel])), 1),
                "median_transcript_confidence": round(float(np.median([r["conf"] for r in sel])), 3)}

    instr_rows = [r for r in rows if r["who"] == "instructor"]
    other_rows = [r for r in rows if r["who"] == "other"]
    short_rows = [r for r in rows if r["who"] == "short"]
    other_clusters = len(set(int(l) for l in labels if l != instr))
    return {
        "speech_minutes": round(sum(r["dur"] for r in rows) / 60, 1),
        "instructor": summ(instr_rows),
        "others_3s_plus": summ(other_rows),
        "short_turns_under_3s": summ(short_rows),
        "voice_groups_among_others_est": other_clusters,
        "loudness_gap_db": (round(summ(instr_rows)["median_loudness_dbfs"] - summ(other_rows)["median_loudness_dbfs"], 1)
                            if instr_rows and other_rows else None),
        # Times only, no words: lets a camera timeline be lined up against who was talking.
        "turn_timeline": [(round(r["start"], 1), round(r["end"], 1), r["who"]) for r in rows],
    }


def run(video: str | None, audio: str | None, cfg, out: Path | None = None) -> dict:
    res = {}
    if video:
        from .backends.face_opencv import OpenCVFaces
        res["camera"] = check_camera(video, OpenCVFaces(cfg.model_cache, min_face_px=1))
    if audio:
        from .backends.speech import EcapaVoices
        res["audio"] = check_audio(audio, EcapaVoices(cfg.model_cache),
                                   cfg.whisper_model if cfg.whisper_model != "large-v3" else "small.en",
                                   cfg.device)
    if out:
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res
