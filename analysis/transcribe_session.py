"""Transcribe one session once and cache the words, turns and turn voiceprints, so later
analyses don't redo the slow part.

    python analysis/transcribe_session.py <session_dir> [audio_file] [whisper_model]

Writes into <session_dir> (which must be under data/, never committed):
    words.json        [[start, end, word, probability], ...]
    turns.json        [{"i", "start", "end", "words"}, ...]   pause-split turns
    turn_voice.npz    ECAPA embedding per turn of 1.5 s or more, keyed by turn index
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classroom.backends.speech import SR, EcapaVoices, load_audio  # noqa: E402

sess = Path(sys.argv[1])
audio_file = sys.argv[2] if len(sys.argv) > 2 else str(sess / "front_with_audio.mp4")
model_name = sys.argv[3] if len(sys.argv) > 3 else "small.en"

from faster_whisper import WhisperModel  # noqa: E402

audio = load_audio(audio_file)
segs, _ = WhisperModel(model_name, device="cpu").transcribe(
    audio, language="en", word_timestamps=True, vad_filter=True)
words = [[round(w.start, 2), round(w.end, 2), w.word, round(w.probability, 3)] for s in segs for w in (s.words or [])]
(sess / "words.json").write_text(json.dumps(words))
print(f"{len(words)} words", flush=True)

turns = []
for w in words:
    if turns and w[0] - turns[-1]["end"] < 0.8:
        turns[-1]["end"] = w[1]
        turns[-1]["words"].append(w[2])
    else:
        turns.append({"i": len(turns), "start": w[0], "end": w[1], "words": [w[2]]})
for t in turns:
    t["text"] = "".join(t.pop("words")).strip()
(sess / "turns.json").write_text(json.dumps(turns))

enc = EcapaVoices(Path.home() / ".cache" / "classroom-pilot")
embs = {}
for t in turns:
    if t["end"] - t["start"] >= 1.5:
        embs[str(t["i"])] = enc.embed(audio[int(t["start"] * SR):int(t["end"] * SR)])
np.savez(sess / "turn_voice.npz", **embs)
print(f"{len(turns)} turns, {len(embs)} with voiceprints", flush=True)
