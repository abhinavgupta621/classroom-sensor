"""Face detection and recognition with OpenCV's YuNet + SFace (Apache-2.0 models from
opencv_zoo). CPU-only, no torch, and fast enough to sample a 4K room camera every
few seconds.

SFace's published cosine threshold is 0.363; the pilot defaults a little stricter (see
config.py) and sends near-misses to the review queue rather than guessing.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np

from . import DetectedFace

MODELS = {
    "yunet": (
        "face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ),
    "sface": (
        "face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ),
}


def model_path(name: str, cache: Path) -> Path:
    fname, url = MODELS[name]
    p = cache / fname
    if not p.exists():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(p)
    return p


class OpenCVFaces:
    def __init__(self, cache: Path, min_det_score: float = 0.8, min_face_px: int = 24):
        import cv2

        self.cv2 = cv2
        self.min_face_px = min_face_px
        self.det = cv2.FaceDetectorYN.create(
            str(model_path("yunet", cache)), "", (320, 320), min_det_score, 0.3, 5000
        )
        self.rec = cv2.FaceRecognizerSF.create(str(model_path("sface", cache)), "")

    def faces(self, image_bgr: np.ndarray) -> list[DetectedFace]:
        h, w = image_bgr.shape[:2]
        self.det.setInputSize((w, h))
        _, found = self.det.detect(image_bgr)
        out: list[DetectedFace] = []
        if found is None:
            return out
        for row in found:
            x, y, fw, fh = (int(v) for v in row[:4])
            if min(fw, fh) < self.min_face_px:
                continue  # too small to recognise reliably; counted as unidentified
            aligned = self.rec.alignCrop(image_bgr, row)
            emb = self.rec.feature(aligned).reshape(-1).astype(np.float32)
            out.append(DetectedFace(emb, (x, y, fw, fh), float(row[-1])))
        return out
