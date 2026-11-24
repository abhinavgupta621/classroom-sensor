"""Enrolled face and voice templates, and matching against them.

A gallery stores one or more L2-normalised embeddings per person (several enrollment
photos or clips give a sturdier template). Only embeddings are kept: enrollment photos
and audio are read, embedded and never copied.

Matching takes the best cosine similarity per person, then requires both an absolute
threshold and a margin over the runner-up, so look-alikes come back as "needs review"
instead of a confident wrong name.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .roster import Person


def normalise(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class Match:
    person_id: str | None  # None when nobody clears the bar
    score: float  # best similarity
    runner_up: float  # second-best person's similarity
    candidate: str | None  # best person even when not accepted, for the review queue

    @property
    def accepted(self) -> bool:
        return self.person_id is not None


class Gallery:
    def __init__(self, kind: str):
        if kind not in {"face", "voice"}:
            raise ValueError("kind must be face or voice")
        self.kind = kind
        self._emb: dict[str, list[np.ndarray]] = {}

    def add(self, person_id: str, embedding: np.ndarray) -> None:
        self._emb.setdefault(person_id, []).append(normalise(embedding))

    def remove(self, person_id: str) -> bool:
        return self._emb.pop(person_id, None) is not None

    def people(self) -> list[str]:
        return sorted(self._emb)

    def __len__(self) -> int:
        return len(self._emb)

    def restrict_to_consented(self, roster: dict[str, Person]) -> "Gallery":
        """A copy holding only people on the roster who still consent to this kind."""
        out = Gallery(self.kind)
        for pid, embs in self._emb.items():
            p = roster.get(pid)
            ok = p is not None and (p.face_consent if self.kind == "face" else p.voice_consent)
            if ok:
                out._emb[pid] = list(embs)
        return out

    def match(self, embedding: np.ndarray, threshold: float, margin: float) -> Match:
        if not self._emb:
            return Match(None, 0.0, 0.0, None)
        q = normalise(embedding)
        scores = sorted(
            ((max(float(q @ e) for e in embs), pid) for pid, embs in self._emb.items()),
            reverse=True,
        )
        best, pid = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1.0
        accepted = best >= threshold and (best - second) >= margin
        return Match(pid if accepted else None, best, second, pid)

    # Storage: one .npz per gallery; keys are "<person_id>__<n>".
    def save(self, path: str | Path) -> None:
        arrays = {f"{pid}__{i}": e for pid, embs in self._emb.items() for i, e in enumerate(embs)}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **arrays)

    @classmethod
    def load(cls, kind: str, path: str | Path) -> "Gallery":
        g = cls(kind)
        if not Path(path).exists():
            return g
        with np.load(path) as data:
            for key in data.files:
                pid = key.rsplit("__", 1)[0]
                g._emb.setdefault(pid, []).append(data[key].astype(np.float32))
        return g
