"""Transcription on the Mac's GPU (mlx-whisper), with the section's first names as a prompt.

    python analysis/transcribe_mlx.py <session_dir> <section> [audio_file] [model]

Writes words_mlx.json ([start, end, word, probability]) and timing_mlx.json.
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classroom.backends.speech import load_audio  # noqa: E402

import mlx_whisper  # noqa: E402

sess, section = Path(sys.argv[1]), sys.argv[2]
audio_file = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
model = sys.argv[4] if len(sys.argv) > 4 else "mlx-community/whisper-large-v3-turbo"
if audio_file is None:
    audio_file = str(sess / ("front_with_audio.mp4" if (sess / "front_with_audio.mp4").exists() else "camera.mp4"))

g = np.load(sess / "gallery.npz")
firsts = sorted({str(n).split()[0] for n, s in zip(g["names"], g["sections"]) if s == section})
prompt = "Core MBA course: leading people at Berkeley Haas. Students: " + ", ".join(firsts) + "."

t0 = time.time()
audio = load_audio(audio_file)
t1 = time.time()
out = mlx_whisper.transcribe(audio, path_or_hf_repo=model, language="en", word_timestamps=True,
                             initial_prompt=prompt, condition_on_previous_text=False)
t2 = time.time()
words = [[round(w["start"], 2), round(w["end"], 2), w["word"], round(w.get("probability", 0), 3)]
         for s in out["segments"] for w in s.get("words", [])]
(sess / "words_mlx.json").write_text(json.dumps(words))
text = "".join(w[2] for w in words)
found = sorted({f for f in firsts if re.search(r"\b" + re.escape(f) + r"\b", text)})
res = {"model": model, "audio_minutes": round(len(audio) / 16000 / 60, 1), "decode_s": round(t1 - t0, 1),
       "transcribe_s": round(t2 - t1, 1), "x_realtime": round(len(audio) / 16000 / (t2 - t1), 1),
       "words": len(words), "section_first_names_in_text": found, "count": len(found)}
(sess / "timing_mlx.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
