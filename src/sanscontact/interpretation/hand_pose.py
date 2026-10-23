"""Scale-invariant description of a hand posture, computed from 21 landmarks.

Distances are divided by the hand size (wrist to middle-finger base), so the
result does not depend on how far the hand is from the camera. x is multiplied
by the image aspect ratio first, so both axes use the same unit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sanscontact.perception.types import FINGERS, INDEX, MIDDLE, PALM, THUMB, WRIST, HandObservation

STRAIGHT_FINGER = 0.88
STRAIGHT_THUMB = 0.85
THUMB_AWAY = 0.55
MIN_SPREAD_DEG = 8.0
MIN_THUMB_SPREAD_DEG = 25.0


@dataclass(frozen=True)
class PoseFeatures:
    size: float
    center: tuple[float, float]  # palm centre, normalised image coordinates (not scaled, not mirrored)
    extended: tuple[bool, bool, bool, bool, bool]  # thumb, index, middle, ring, pinky
    spread_deg: tuple[float, float, float]  # index-middle, middle-ring, ring-pinky
    thumb_spread_deg: float

    @property
    def open_palm(self) -> bool:
        return (
            all(self.extended)
            and min(self.spread_deg) >= MIN_SPREAD_DEG
            and self.thumb_spread_deg >= MIN_THUMB_SPREAD_DEG
        )


def scaled_points(landmarks: np.ndarray, aspect: float) -> np.ndarray:
    points = np.asarray(landmarks[:, :2], dtype=np.float64).copy()
    points[:, 0] *= aspect
    return points


def hand_size(points: np.ndarray) -> float:
    size = float(np.linalg.norm(points[MIDDLE[0]] - points[WRIST]))
    if size < 1e-6:
        size = float(np.mean([np.linalg.norm(points[i] - points[WRIST]) for i in PALM[1:]]))
    return max(size, 1e-6)


def straightness(points: np.ndarray, chain: tuple[int, ...]) -> float:
    segments = sum(float(np.linalg.norm(points[b] - points[a])) for a, b in zip(chain, chain[1:], strict=False))
    if segments < 1e-9:
        return 0.0
    return float(np.linalg.norm(points[chain[-1]] - points[chain[0]])) / segments


def _angle_deg(u: np.ndarray, v: np.ndarray) -> float:
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    cos = float(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def finger_extended(points: np.ndarray, finger: tuple[int, int, int, int]) -> bool:
    mcp, pip, _dip, tip = finger
    wrist = points[WRIST]
    farther = np.linalg.norm(points[tip] - wrist) > np.linalg.norm(points[pip] - wrist)
    return bool(farther and straightness(points, finger) >= STRAIGHT_FINGER)


def thumb_extended(points: np.ndarray, size: float) -> bool:
    away = np.linalg.norm(points[THUMB[3]] - points[INDEX[0]]) / size >= THUMB_AWAY
    return bool(away and straightness(points, THUMB[1:]) >= STRAIGHT_THUMB)


def features(hand: HandObservation, aspect: float) -> PoseFeatures:
    points = scaled_points(hand.landmarks, aspect)
    size = hand_size(points)
    directions = [points[f[3]] - points[f[0]] for f in FINGERS]
    spread = tuple(_angle_deg(directions[i], directions[i + 1]) for i in range(3))
    thumb_dir = points[THUMB[3]] - points[THUMB[1]]
    center = hand.landmarks[list(PALM), :2].mean(axis=0)
    return PoseFeatures(
        size=size,
        center=(float(center[0]), float(center[1])),
        extended=(thumb_extended(points, size), *(finger_extended(points, f) for f in FINGERS)),
        spread_deg=spread,  # type: ignore[arg-type]
        thumb_spread_deg=_angle_deg(thumb_dir, directions[0]),
    )


def person_hand(label: str) -> str:
    """Which hand of the person this is.

    Hand models label hands as if the frame were mirrored (selfie view). Our
    frames are not mirrored, so the label is swapped.
    """
    return {"Left": "right", "Right": "left"}.get(label, "unknown")
