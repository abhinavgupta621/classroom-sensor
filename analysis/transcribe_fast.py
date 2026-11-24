"""Faster, name-aware transcription experiment.

    python analysis/transcribe_fast.py <session_dir> <section> [model] [batch]

Batched faster-whisper (default large-v3-turbo) with hotwords: the section's first names and
course terms, so names the professor says come out spelled like the roster.
Writes words_<model>.json and timing_<model>.json; prints how many roster first names
appear in the transcript.
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classroom.backends.speech import load_audio  # noqa: E402

sess, section = Path(sys.argv[1]), sys.argv[2]
model_name = sys.argv[3] if len(sys.argv) > 3 else "large-v3-turbo"
batch = int(sys.argv[4]) if len(sys.argv) > 4 else 8

from faster_whisper import BatchedInferencePipeline, WhisperModel  # noqa: E402

g = np.load(sess / "gallery.npz")
firsts = sorted({str(n).split()[0] for n, s in zip(g["names"], g["sections"]) if s == section})
terms = ["Haas", "BATNA", "ZOPA", "groupthink", "Lewin", "Ginzel", "Kahneman", "Tversky", "Granovetter",
         "path-goal", "Big Five", "DLPs", "Defining Leadership Principles"]
hot = ", ".join(firsts + terms)

t0 = time.time()
audio = load_audio(str(sess / "front_with_audio.mp4"))
t_load = time.time() - t0
model = WhisperModel(model_name, device="cpu", compute_type="int8")
pipe = BatchedInferencePipeline(model=model)
t1 = time.time()
segs, info = pipe.transcribe(audio, language="en", word_timestamps=True, batch_size=batch,
                             hotwords=hot, vad_filter=True)
words = [[round(w.start, 2), round(w.end, 2), w.word, round(w.probability, 3)] for s in segs for w in (s.words or [])]
t_tx = time.time() - t1
safe = model_name.replace("/", "_")
(sess / f"words_{safe}.json").write_text(json.dumps(words))
text = "".join(w[2] for w in words)
found = sorted({f for f in firsts if re.search(r"\b" + re.escape(f) + r"\b", text)})
res = {"model": model_name, "batch": batch, "audio_minutes": round(len(audio) / 16000 / 60, 1),
       "decode_s": round(t_load, 1), "transcribe_s": round(t_tx, 1),
       "x_realtime": round(len(audio) / 16000 / t_tx, 1), "words": len(words),
       "section_first_names_in_text": found, "count": len(found)}
(sess / f"timing_{safe}.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
