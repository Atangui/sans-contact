"""Which hand-landmark engine runs. One place to plug it in."""

from __future__ import annotations

from sanscontact.config.settings import Settings
from sanscontact.perception.models import MODELS, load_verified
from sanscontact.perception.source import EngineFactory


class EngineUnavailable(RuntimeError):
    pass


def hand_engine_factory(settings: Settings) -> EngineFactory:
    """Return a factory creating the hand engine for the given settings.

    MediaPipe is not used (its native library embeds usage telemetry, which rule
    3.1 forbids): the MediaPipe hand models, in ONNX form, run on OpenCV.
    Model files are read and their SHA-256 checked here, before the camera is
    turned on; a missing or modified file raises ``ModelError``.
    """
    import cv2

    from sanscontact.perception.opencv_hands import OpenCvHandEngine

    # Few threads: the models are small, and more threads mostly burn CPU while waiting.
    cv2.setNumThreads(settings.opencv_threads)
    palm = load_verified(MODELS["palm"])
    hand = load_verified(MODELS["handpose"])
    return lambda: OpenCvHandEngine(palm, hand, num_hands=settings.num_hands)
