"""Model backends. Each is a small class with one job, so a model can be swapped
(or faked in tests) without touching the attendance or contribution logic.

    FaceBackend.faces(image_bgr) -> list[DetectedFace]
    VoiceBackend.embed(waveform_16k) -> np.ndarray
    Transcriber.words(audio_path) -> list[Word]; Transcriber.load_audio(path) -> np.ndarray
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class DetectedFace:
    embedding: np.ndarray
    box: tuple[int, int, int, int]  # x, y, w, h in frame pixels
    det_score: float


@dataclass
class Word:
    start: float  # seconds from the start of the recording
    end: float
    text: str
