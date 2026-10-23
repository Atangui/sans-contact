"""Pinned model files: official source, SHA-256, and in-memory verification.

The application never downloads: scripts/fetch_models.py does it once. At
start-up the file is read, its hash checked, and only the verified bytes are
used, so what runs is exactly what was checked.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    filename: str
    url: str
    sha256: str


_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models"

# MediaPipe hand models (February 2023) converted to ONNX by OpenCV Zoo, Apache-2.0.
# Pinned to one commit of the repository; hashes are the ones published in its Git LFS pointers.
MODELS: dict[str, ModelSpec] = {
    "palm": ModelSpec(
        name="palm",
        filename="palm_detection_mediapipe_2023feb.onnx",
        url=f"{_ZOO}/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx",
        sha256="78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c",
    ),
    "handpose": ModelSpec(
        name="handpose",
        filename="handpose_estimation_mediapipe_2023feb.onnx",
        url=f"{_ZOO}/handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx",
        sha256="db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c",
    ),
}


class ModelError(RuntimeError):
    pass


def load_verified(spec: ModelSpec, directory: Path = MODELS_DIR) -> bytes:
    path = directory / spec.filename
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ModelError(f"{spec.filename} is missing: run scripts/fetch_models.py") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != spec.sha256:
        raise ModelError(f"{spec.filename}: SHA-256 mismatch ({digest})")
    return data


