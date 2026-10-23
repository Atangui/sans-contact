"""Geometry around the hand models: anchors, decoding, regions of interest, crop and projection.

Parameters follow the ones MediaPipe publishes for its hand pipeline
(palm_detection_cpu.pbtxt, palm_detection_detection_to_roi.pbtxt,
hand_landmark_landmarks_to_roi.pbtxt, rect_transformation_calculator.cc).
Everything here is pure arithmetic on numbers: no image is kept.

Coordinates are normalised to the image (0..1, x right, y down). A ``NormRect``
is a rotated rectangle; rotation is in radians, positive clockwise on screen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PALM_INPUT = 192
HAND_INPUT = 224
PALM_STRIDES = (8, 16, 16, 16)
PALM_KEYPOINTS = 7
# Palm keypoints: 0 = wrist centre, 2 = middle-finger base.
PALM_ROTATION = (0, 2)
PALM_ROI = {"scale": 2.6, "shift_y": -0.5}
HAND_ROI = {"scale": 2.0, "shift_y": -0.1}
# Landmarks that stay stable when fingers move (no fingertips), used to follow the hand.
STABLE_LANDMARKS = (0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18)
NORMALIZE_Z = 0.4


@dataclass(frozen=True)
class NormRect:
    x_center: float
    y_center: float
    width: float
    height: float
    rotation: float = 0.0

    def bounds(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box (x0, y0, x1, y1), ignoring rotation."""
        return (self.x_center - self.width / 2, self.y_center - self.height / 2,
                self.x_center + self.width / 2, self.y_center + self.height / 2)


@dataclass(frozen=True)
class Palm:
    score: float
    box: tuple[float, float, float, float]  # x_center, y_center, width, height
    keypoints: np.ndarray  # (7, 2)


def normalize_radians(angle: float) -> float:
    return angle - 2 * math.pi * math.floor((angle + math.pi) / (2 * math.pi))


def ssd_anchors(input_size: int = PALM_INPUT, strides: tuple[int, ...] = PALM_STRIDES) -> np.ndarray:
    """Anchor centres (N, 2). Fixed anchor size; two anchors per layer and location."""
    anchors = []
    layer = 0
    while layer < len(strides):
        per_location = 0
        last = layer
        while last < len(strides) and strides[last] == strides[layer]:
            per_location += 2  # aspect ratio 1.0 plus the interpolated scale
            last += 1
        size = math.ceil(input_size / strides[layer])
        for y in range(size):
            for x in range(size):
                anchors.extend([((x + 0.5) / size, (y + 0.5) / size)] * per_location)
        layer = last
    return np.array(anchors, dtype=np.float64)


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -100.0, 100.0)))


def decode_palms(raw_boxes: np.ndarray, raw_scores: np.ndarray, anchors: np.ndarray,
                 min_score: float = 0.5, input_size: int = PALM_INPUT) -> list[Palm]:
    """Raw detector outputs -> palms in the detector's (letterboxed) normalised space."""
    boxes = raw_boxes.reshape(-1, 4 + 2 * PALM_KEYPOINTS)
    scores = sigmoid(raw_scores.reshape(-1).astype(np.float64))
    palms = []
    for i in np.flatnonzero(scores >= min_score):
        raw = boxes[i].astype(np.float64) / input_size
        ax, ay = anchors[i]
        keypoints = raw[4:].reshape(PALM_KEYPOINTS, 2) + (ax, ay)
        palms.append(Palm(float(scores[i]), (raw[0] + ax, raw[1] + ay, raw[2], raw[3]), keypoints))
    return palms


def _iou(a: tuple, b: tuple) -> float:
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def weighted_nms(palms: list[Palm], iou_threshold: float = 0.3) -> list[Palm]:
    """MediaPipe's WEIGHTED non-maximum suppression: overlapping detections are averaged by score."""
    remaining = sorted(palms, key=lambda p: p.score, reverse=True)
    kept = []
    while remaining:
        best = remaining[0]
        cluster = [p for p in remaining if _iou(best.box, p.box) > iou_threshold]
        weights = np.array([p.score for p in cluster])
        total = weights.sum()
        box = tuple(float(v) for v in (np.array([p.box for p in cluster]) * weights[:, None]).sum(0) / total)
        keypoints = (np.stack([p.keypoints for p in cluster]) * weights[:, None, None]).sum(0) / total
        kept.append(Palm(best.score, box, keypoints))
        remaining = [p for p in remaining if p not in cluster]
    return kept


def letterbox(width: int, height: int, size: int = PALM_INPUT) -> tuple[float, int, int, int, int]:
    """(scale, resized width, resized height, left pad, top pad) to fit an image in a square input."""
    scale = min(size / width, size / height)
    new_w, new_h = round(width * scale), round(height * scale)
    return scale, new_w, new_h, (size - new_w) // 2, (size - new_h) // 2


def remove_letterbox(palm: Palm, width: int, height: int, size: int = PALM_INPUT) -> Palm:
    _, new_w, new_h, left, top = letterbox(width, height, size)
    sx, sy = new_w / size, new_h / size
    ox, oy = left / size, top / size
    cx, cy, w, h = palm.box
    keypoints = (palm.keypoints - (ox, oy)) / (sx, sy)
    return Palm(palm.score, ((cx - ox) / sx, (cy - oy) / sy, w / sx, h / sy), keypoints)


def _rotation(x0: float, y0: float, x1: float, y1: float, width: int, height: int) -> float:
    """Rotation that makes the vector (p0 -> p1) point straight up (target angle 90 degrees)."""
    return normalize_radians(math.pi / 2 - math.atan2(-(y1 - y0) * height, (x1 - x0) * width))


def transform_rect(rect: NormRect, width: int, height: int, scale: float, shift_y: float = 0.0,
                   shift_x: float = 0.0, square_long: bool = True) -> NormRect:
    """MediaPipe's RectTransformationCalculator: shift in the rotated frame, square, then scale."""
    w, h, r = rect.width, rect.height, rect.rotation
    if r == 0.0:
        cx = rect.x_center + w * shift_x
        cy = rect.y_center + h * shift_y
    else:
        dx = (width * w * shift_x * math.cos(r) - height * h * shift_y * math.sin(r)) / width
        dy = (width * w * shift_x * math.sin(r) + height * h * shift_y * math.cos(r)) / height
        cx, cy = rect.x_center + dx, rect.y_center + dy
    if square_long:
        side = max(w * width, h * height)
        w, h = side / width, side / height
    return NormRect(cx, cy, w * scale, h * scale, r)


def palm_to_rect(palm: Palm, width: int, height: int) -> NormRect:
    """Region where the whole hand should be, from a palm detection."""
    (x0, y0), (x1, y1) = palm.keypoints[PALM_ROTATION[0]], palm.keypoints[PALM_ROTATION[1]]
    rotation = _rotation(x0, y0, x1, y1, width, height)
    cx, cy, w, h = palm.box
    return transform_rect(NormRect(cx, cy, w, h, rotation), width, height, PALM_ROI["scale"], PALM_ROI["shift_y"])


def landmarks_to_rect(landmarks: np.ndarray, width: int, height: int) -> NormRect:
    """Region for the next frame, from this frame's landmarks (the hand is followed, not re-detected)."""
    points = np.asarray(landmarks[list(STABLE_LANDMARKS), :2], dtype=np.float64)
    wrist = points[0]
    middle = (points[4] + points[8]) / 2  # index and ring finger bases...
    middle = (middle + points[6]) / 2  # ...averaged with the middle finger base
    rotation = _rotation(wrist[0], wrist[1], middle[0], middle[1], width, height)
    cos, sin = math.cos(-rotation), math.sin(-rotation)
    center = (points.min(0) + points.max(0)) / 2
    px = (points[:, 0] - center[0]) * width
    py = (points[:, 1] - center[1]) * height
    rx = px * cos - py * sin
    ry = px * sin + py * cos
    mid_x, mid_y = (rx.min() + rx.max()) / 2, (ry.min() + ry.max()) / 2
    cos_r, sin_r = math.cos(rotation), math.sin(rotation)
    cx = (mid_x * cos_r - mid_y * sin_r) / width + center[0]
    cy = (mid_x * sin_r + mid_y * cos_r) / height + center[1]
    rect = NormRect(cx, cy, (rx.max() - rx.min()) / width, (ry.max() - ry.min()) / height, rotation)
    return transform_rect(rect, width, height, HAND_ROI["scale"], HAND_ROI["shift_y"])


def crop_matrix(rect: NormRect, width: int, height: int, size: int = HAND_INPUT) -> np.ndarray:
    """2x3 affine matrix mapping image pixels to the (size x size) crop of a rotated rectangle."""
    cos, sin = math.cos(rect.rotation), math.sin(rect.rotation)
    rotation = np.array([[cos, -sin], [sin, cos]])
    to_image = rotation @ np.diag([rect.width * width / size, rect.height * height / size])
    offset = np.array([rect.x_center * width, rect.y_center * height]) - to_image @ np.array([size / 2, size / 2])
    inverse = np.linalg.inv(to_image)
    return np.hstack([inverse, (-inverse @ offset)[:, None]])


def project_landmarks(crop_landmarks: np.ndarray, rect: NormRect, size: int = HAND_INPUT) -> np.ndarray:
    """Landmarks in crop pixels (21, 3) -> normalised image coordinates (21, 3)."""
    x = crop_landmarks[:, 0] / size - 0.5
    y = crop_landmarks[:, 1] / size - 0.5
    cos, sin = math.cos(rect.rotation), math.sin(rect.rotation)
    out = np.empty((crop_landmarks.shape[0], 3), dtype=np.float32)
    out[:, 0] = (cos * x - sin * y) * rect.width + rect.x_center
    out[:, 1] = (sin * x + cos * y) * rect.height + rect.y_center
    out[:, 2] = crop_landmarks[:, 2] / size / NORMALIZE_Z * rect.width
    return out


def rect_iou(a: NormRect, b: NormRect) -> float:
    """Overlap of the axis-aligned bounds of two rectangles."""
    return _iou((a.x_center, a.y_center, a.width, a.height), (b.x_center, b.y_center, b.width, b.height))
