"""What perception hands over: a few numbers per hand, never an image."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Landmark indexes (MediaPipe hand topology).
WRIST = 0
THUMB = (1, 2, 3, 4)
INDEX = (5, 6, 7, 8)
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)
PINKY = (17, 18, 19, 20)
FINGERS = (INDEX, MIDDLE, RING, PINKY)
PALM = (0, 5, 9, 13, 17)


@dataclass(frozen=True, eq=False)
class HandObservation:
    """21 landmarks in normalised image coordinates (x right, y down, 0..1, not mirrored)."""

    landmarks: np.ndarray  # shape (21, 3), float32
    handedness: str  # "Left" / "Right" as seen in the (non-mirrored) image
    score: float


@dataclass(frozen=True, eq=False)
class Observation:
    seq: int
    t_capture_ns: int
    aspect: float  # width / height of the analysed frame
    hands: tuple[HandObservation, ...]
    timings_ns: dict[str, int] = field(default_factory=dict)
