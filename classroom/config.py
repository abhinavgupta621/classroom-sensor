"""Tunable settings, in one place. Every threshold here should be re-checked against the
pilot's own labelled sessions (see README, "Calibrating") before results are used.
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    data_dir: Path = Path("data")  # galleries, session outputs, audit log; never commit
    model_cache: Path = Path.home() / ".cache" / "classroom-pilot"

    # Faces
    frame_every_s: float = 10.0  # how often to sample the room camera
    # SFace cosine. Measured on the the core course room camera (Oct 8, 1080p; 2,733 same-person
    # and 19,801 different-person pairs): at 0.40 a face clears the bar for someone else in a
    # 70-person gallery ~18% of the time; at 0.50 it's ~0.7%, with ~97% of same-person pairs
    # still matching. The published default (0.363) is far too loose for a full class.
    face_threshold: float = 0.50
    face_margin: float = 0.05  # best must beat the runner-up by this much
    face_review_floor: float = 0.40  # below the bar but above this goes to review
    min_sightings: int = 2  # sightings needed to mark someone present
    late_grace_min: float = 5.0  # arriving within this of start is on time
    leave_grace_min: float = 10.0  # last seen this long before the end = left early

    # Voices
    # ECAPA cosine. In the synthetic smoke test enrolled speakers scored ~0.84 and an
    # unenrolled one 0.29-0.35 against her nearest classmate, so 0.30 would have credited
    # her words to someone else. Real room audio scores lower: calibrate (README).
    voice_threshold: float = 0.50
    voice_margin: float = 0.08
    voice_review_floor: float = 0.35
    min_turn_s: float = 1.5  # shorter turns are too short to identify a voice
    turn_gap_s: float = 0.8  # a pause this long starts a new turn
    min_run_s: float = 2.0  # a speaker label must hold this long inside a turn

    # Transcription
    whisper_model: str = "large-v3"
    device: str = "auto"  # "cuda" on a GPU box

    # Scoring
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"

    rubric: list[str] = field(
        default_factory=lambda: [
            "relevance: addresses the question or case under discussion",
            "evidence: uses facts from the case, data or readings",
            "builds_on_others: engages with what a classmate said",
            "insight: adds a new angle, framework or implication",
        ]
    )
