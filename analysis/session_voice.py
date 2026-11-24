"""Turns and voiceprints from a words file (e.g. words_mlx.json).

    python analysis/session_voice.py <session_dir> [words_file] [audio_file]

Writes turns_v2.json (pause-split turns with text) and turn_voice_v2.npz (ECAPA per turn of
1.5 s or more).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classroom.backends.speech import SR, EcapaVoices, load_audio  # noqa: E402

sess = Path(sys.argv[1])
words = json.loads((sess / (sys.argv[2] if len(sys.argv) > 2 else "words_mlx.json")).read_text())
audio_file = sys.argv[3] if len(sys.argv) > 3 else str(
    sess / ("front_with_audio.mp4" if (sess / "front_with_audio.mp4").exists() else "camera.mp4"))
turns = []
for w in words:
    if turns and w[0] - turns[-1]["end"] < 0.8:
        turns[-1]["end"] = w[1]; turns[-1]["w"].append(w[2])
    else:
        turns.append({"i": len(turns), "start": w[0], "end": w[1], "w": [w[2]]})
for t in turns:
    t["text"] = "".join(t.pop("w")).strip()
(sess / "turns_v2.json").write_text(json.dumps(turns))
audio = load_audio(audio_file)
enc = EcapaVoices(Path.home() / ".cache" / "classroom-pilot")
emb = {str(t["i"]): enc.embed(audio[int(t["start"] * SR):int(t["end"] * SR)])
       for t in turns if t["end"] - t["start"] >= 1.5}
np.savez(sess / "turn_voice_v2.npz", **emb)
print(f"{sess.name}: {len(turns)} turns, {len(emb)} voiceprints")
