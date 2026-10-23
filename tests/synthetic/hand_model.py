"""Synthetic hands: 21 landmarks generated from a simple parametric model.

No image and no recording of a real person is ever used in tests. Postures are
built from joint angles, seen from the front: flexing a finger shortens its
projection (and folds it back past 90 degrees).
"""

from __future__ import annotations

import math

import numpy as np

from sanscontact.perception.types import HandObservation

# Hand frame: wrist at the origin, fingers towards -y, unit = wrist-to-middle-base distance.
# This template is a person's LEFT hand, palm towards a non-mirrored camera (thumb on the image left).
_MCP = {"index": (-0.30, -0.95), "middle": (0.0, -1.0), "ring": (0.27, -0.93), "pinky": (0.50, -0.80)}
_LENGTHS = {"index": (0.45, 0.27, 0.22), "middle": (0.50, 0.30, 0.23), "ring": (0.46, 0.28, 0.22),
            "pinky": (0.36, 0.22, 0.19)}
_THUMB_CMC = (-0.35, -0.25)
_THUMB_LENGTHS = (0.32, 0.27, 0.24)

_SPREAD_OPEN = {"index": -14.0, "middle": 0.0, "ring": 12.0, "pinky": 26.0}
_SPREAD_TOGETHER = {"index": -4.0, "middle": 0.0, "ring": 3.0, "pinky": 7.0}
_CURLED = (85.0, 95.0, 60.0)
_STRAIGHT = (0.0, 0.0, 0.0)

POSES = {
    # name: (spread, {finger: flex}, thumb_angle, thumb_flex)
    "open": (_SPREAD_OPEN, {}, -60.0, _STRAIGHT),
    "relaxed": (_SPREAD_TOGETHER, {}, -25.0, (20.0, 30.0, 20.0)),
    "fist": (_SPREAD_TOGETHER, {f: _CURLED for f in _MCP}, 35.0, (20.0, 40.0, 30.0)),
    "point": (_SPREAD_TOGETHER, {"middle": _CURLED, "ring": _CURLED, "pinky": _CURLED}, -20.0, (40.0, 60.0, 50.0)),
}


def _chain(base, direction_deg, lengths, flex):
    points = []
    x, y = base
    angle = math.radians(direction_deg)
    cumulative = 0.0
    for length, bend in zip(lengths, flex, strict=True):
        cumulative += math.radians(bend)
        projected = length * math.cos(cumulative)
        x += projected * math.sin(angle)
        y -= projected * math.cos(angle)
        points.append((x, y))
    return points


def hand_points(pose: str) -> np.ndarray:
    """(21, 2) points in the hand frame for the given posture."""
    spread, flexes, thumb_angle, thumb_flex = POSES[pose]
    points = np.zeros((21, 2))
    thumb = _chain(_THUMB_CMC, thumb_angle, _THUMB_LENGTHS, thumb_flex)
    points[1] = _THUMB_CMC
    points[2:5] = thumb
    for i, finger in enumerate(("index", "middle", "ring", "pinky")):
        base = 5 + 4 * i
        points[base] = _MCP[finger]
        flex = flexes.get(finger, _STRAIGHT)
        points[base + 1: base + 4] = _chain(_MCP[finger], spread[finger], _LENGTHS[finger], flex)
    return points


def make_hand(pose: str = "open", center=(0.5, 0.55), size: float = 0.18, angle_deg: float = 0.0,
              person_hand: str = "left", aspect: float = 4 / 3, noise: float = 0.0,
              rng: np.random.Generator | None = None, score: float = 0.95) -> HandObservation:
    """A HandObservation in normalised image coordinates.

    ``size`` is the wrist-to-middle-base distance in image-height units; ``center``
    is the palm centre in normalised coordinates.
    """
    points = hand_points(pose) * size
    if person_hand == "right":
        points[:, 0] *= -1
    a = math.radians(angle_deg)
    rotation = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    points = points @ rotation.T
    palm = points[[0, 5, 9, 13, 17]].mean(axis=0)
    points += np.array([center[0] * aspect, center[1]]) - palm
    if noise:
        rng = rng or np.random.default_rng(0)
        points += rng.normal(0.0, noise * size, points.shape)
    landmarks = np.zeros((21, 3), dtype=np.float32)
    landmarks[:, 0] = points[:, 0] / aspect
    landmarks[:, 1] = points[:, 1]
    label = "Right" if person_hand == "left" else "Left"  # models label as if mirrored
    return HandObservation(landmarks=landmarks, handedness=label, score=score)
