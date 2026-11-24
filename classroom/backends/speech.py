"""Speech: transcription with word timings (faster-whisper) and speaker embeddings
(SpeechBrain ECAPA-TDNN, trained on VoxCeleb). Both run on CPU; on a GPU box set
device="cuda" in config for roughly 10x faster transcription.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import Word

SR = 16000


def load_audio(path: str | Path) -> np.ndarray:
    """Any audio or video file -> 16 kHz mono float32, via ffmpeg. (faster-whisper's own
    decoder breaks on PyAV 19, and ffmpeg reads every format a room system records.)"""
    import subprocess

    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn",
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {path}: {proc.stderr.decode(errors='replace')[:300]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


class WhisperTranscriber:
    def __init__(self, model: str = "large-v3", device: str = "auto", compute_type: str = "default"):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def load_audio(self, path: str | Path) -> np.ndarray:
        return load_audio(path)

    def words(self, audio: np.ndarray, language: str = "en") -> list[Word]:
        segments, _ = self.model.transcribe(
            audio, language=language, word_timestamps=True, vad_filter=True
        )
        out: list[Word] = []
        for seg in segments:
            for w in seg.words or []:
                out.append(Word(float(w.start), float(w.end), w.word))
        return out


class EcapaVoices:
    def __init__(self, cache: Path, device: str = "cpu"):
        import torch
        from speechbrain.inference.speaker import EncoderClassifier

        self.torch = torch
        self.enc = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(cache / "spkrec-ecapa-voxceleb"),
            run_opts={"device": device},
        )

    def embed(self, waveform_16k: np.ndarray) -> np.ndarray:
        with self.torch.no_grad():
            t = self.torch.from_numpy(np.ascontiguousarray(waveform_16k, dtype=np.float32))[None, :]
            return self.enc.encode_batch(t).reshape(-1).cpu().numpy().astype(np.float32)
