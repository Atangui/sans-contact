"""Open a webcam with OpenCV at the lowest useful resolution."""

from __future__ import annotations

from dataclasses import dataclass

import cv2

BACKENDS = {"msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW}
MJPG = ord("M") | ord("J") << 8 | ord("P") << 16 | ord("G") << 24


@dataclass(frozen=True)
class CameraSpec:
    backend: str
    index: int
    name: str
    width: int = 640
    height: int = 480
    fps: int = 30


def open_capture(spec: CameraSpec) -> cv2.VideoCapture | None:
    """Open and configure the camera; None if it cannot be opened (busy, unplugged...)."""
    api = BACKENDS[spec.backend]
    params = [
        cv2.CAP_PROP_FRAME_WIDTH, spec.width,
        cv2.CAP_PROP_FRAME_HEIGHT, spec.height,
    ]
    cap = cv2.VideoCapture(spec.index, api, params)
    if not cap.isOpened():
        cap.release()
        return None
    if spec.backend == "dshow":
        cap.set(cv2.CAP_PROP_FOURCC, MJPG)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, spec.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, spec.height)
    cap.set(cv2.CAP_PROP_FPS, spec.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def actual_size(cap: cv2.VideoCapture) -> tuple[int, int]:
    return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
