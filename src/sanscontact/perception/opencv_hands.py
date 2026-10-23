"""Hand landmarks with OpenCV's DNN module: no MediaPipe runtime, no network code.

Same two-stage pipeline as MediaPipe:
1. palm detection on the whole (letterboxed) frame, only when no hand is followed;
2. 21 landmarks on a rotated crop around the hand; the crop for the next frame
   comes from these landmarks, so the hand is followed cheaply.

Models: MediaPipe hand models converted to ONNX by OpenCV Zoo (Apache-2.0).
Inputs are NHWC float32 RGB in [0, 1]. Working buffers are reused and zeroed on close.
"""

from __future__ import annotations

import cv2
import numpy as np

from sanscontact.perception import hand_geometry as g
from sanscontact.perception.source import HandLandmarkEngine
from sanscontact.perception.types import HandObservation

SAME_HAND_IOU = 0.5


class OpenCvHandEngine(HandLandmarkEngine):
    def __init__(self, palm_model: bytes, hand_model: bytes, num_hands: int = 1,
                 min_detection: float = 0.5, min_presence: float = 0.5) -> None:
        self._palm = cv2.dnn.readNetFromONNX(np.frombuffer(palm_model, dtype=np.uint8))
        self._hand = cv2.dnn.readNetFromONNX(np.frombuffer(hand_model, dtype=np.uint8))
        self._palm_outputs = self._palm.getUnconnectedOutLayersNames()
        self._hand_outputs = self._hand.getUnconnectedOutLayersNames()
        if len(self._palm_outputs) != 2 or len(self._hand_outputs) != 4:
            raise RuntimeError("unexpected model outputs")
        self.num_hands = num_hands
        self.min_detection = min_detection
        self.min_presence = min_presence
        self._anchors = g.ssd_anchors()
        self._tracked: list[g.NormRect] = []
        self._palm_canvas = np.zeros((g.PALM_INPUT, g.PALM_INPUT, 3), dtype=np.uint8)
        self._palm_blob = np.zeros((1, g.PALM_INPUT, g.PALM_INPUT, 3), dtype=np.float32)
        self._crop = np.zeros((g.HAND_INPUT, g.HAND_INPUT, 3), dtype=np.uint8)
        self._hand_blob = np.zeros((1, g.HAND_INPUT, g.HAND_INPUT, 3), dtype=np.float32)
        self._resized: np.ndarray | None = None
        self.palm_runs = 0

    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> list[HandObservation]:  # noqa: ARG002
        height, width = rgb.shape[:2]
        rects = list(self._tracked)
        if len(rects) < self.num_hands:
            for rect in self._detect_palms(rgb):
                if len(rects) >= self.num_hands:
                    break
                if all(g.rect_iou(rect, other) < SAME_HAND_IOU for other in rects):
                    rects.append(rect)
        hands: list[HandObservation] = []
        followed: list[g.NormRect] = []
        for rect in rects:
            hand = self._landmarks(rgb, rect)
            if hand is not None:
                hands.append(hand)
                followed.append(g.landmarks_to_rect(hand.landmarks, width, height))
        self._tracked = followed
        return hands

    def reset(self) -> None:
        self._tracked = []

    def close(self) -> None:
        self._tracked = []
        for buffer in (self._palm_canvas, self._palm_blob, self._crop, self._hand_blob, self._resized):
            if buffer is not None:
                buffer.fill(0)

    def _detect_palms(self, rgb: np.ndarray) -> list[g.NormRect]:
        height, width = rgb.shape[:2]
        _, new_w, new_h, left, top = g.letterbox(width, height)
        if self._resized is None or self._resized.shape[:2] != (new_h, new_w):
            self._resized = np.zeros((new_h, new_w, 3), dtype=np.uint8)
        cv2.resize(rgb, (new_w, new_h), dst=self._resized, interpolation=cv2.INTER_AREA)
        self._palm_canvas.fill(0)
        self._palm_canvas[top:top + new_h, left:left + new_w] = self._resized
        np.multiply(self._palm_canvas, 1.0 / 255.0, out=self._palm_blob[0], casting="unsafe")
        self._palm.setInput(self._palm_blob)
        boxes, scores = self._palm.forward(self._palm_outputs)
        if boxes.shape[-1] != 18:  # outputs listed in the other order
            boxes, scores = scores, boxes
        self.palm_runs += 1
        palms = g.weighted_nms(g.decode_palms(boxes, scores, self._anchors, self.min_detection))
        return [g.palm_to_rect(g.remove_letterbox(p, width, height), width, height) for p in palms]

    def _landmarks(self, rgb: np.ndarray, rect: g.NormRect) -> HandObservation | None:
        height, width = rgb.shape[:2]
        matrix = g.crop_matrix(rect, width, height)
        cv2.warpAffine(rgb, matrix, (g.HAND_INPUT, g.HAND_INPUT), dst=self._crop, flags=cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE)
        np.multiply(self._crop, 1.0 / 255.0, out=self._hand_blob[0], casting="unsafe")
        self._hand.setInput(self._hand_blob)
        landmarks, presence, handedness, _world = self._hand.forward(self._hand_outputs)
        del _world  # 3-D world coordinates are not needed: dropped at once
        score = float(presence.reshape(-1)[0])
        if score < self.min_presence:
            return None
        points = g.project_landmarks(landmarks.reshape(21, 3).astype(np.float64), rect)
        # Binary classifier: the score is the probability of the first label, "Left".
        label = "Left" if float(handedness.reshape(-1)[0]) > 0.5 else "Right"
        return HandObservation(points, label, score)
