"""The real models on OpenCV, fed with images that contain no person (black, noise)."""

import time

import numpy as np
import pytest

from sanscontact.config.settings import Settings
from sanscontact.perception import hand_geometry as g
from sanscontact.perception.engines import hand_engine_factory
from sanscontact.perception.models import MODELS, MODELS_DIR, ModelError, ModelSpec, load_verified
from sanscontact.privacy import network_guard

pytestmark = pytest.mark.skipif(
    not all((MODELS_DIR / spec.filename).exists() for spec in MODELS.values()),
    reason="models not downloaded (scripts/fetch_models.py)",
)


@pytest.fixture(scope="module")
def engine():
    eng = hand_engine_factory(Settings())()
    yield eng
    eng.close()


def test_no_hand_on_blank_or_noisy_frames(engine):
    rng = np.random.default_rng(0)
    frames = [np.zeros((480, 640, 3), np.uint8), rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)]
    for frame in frames:
        assert engine.detect(frame, 0) == []


def test_runs_fast_enough(engine):
    frame = np.full((480, 640, 3), 128, np.uint8)
    engine.detect(frame, 0)
    start = time.perf_counter()
    for i in range(20):
        engine.detect(frame, i)
    assert (time.perf_counter() - start) / 20 < 0.05  # palm search alone, every frame


def test_landmark_stage_returns_projected_points_for_any_crop(engine):
    rect = g.NormRect(0.5, 0.5, 0.4, 0.4 * 640 / 480, 0.3)
    engine.min_presence = 0.0  # accept whatever the model says, to check the plumbing
    try:
        hand = engine._landmarks(np.full((480, 640, 3), 90, np.uint8), rect)
    finally:
        engine.min_presence = 0.5
    assert hand.landmarks.shape == (21, 3) and hand.landmarks.dtype == np.float32
    assert hand.handedness in ("Left", "Right") and 0.0 <= hand.score <= 1.0


def test_buffers_are_zeroed_on_close():
    eng = hand_engine_factory(Settings())()
    eng.detect(np.full((480, 640, 3), 200, np.uint8), 0)
    assert eng._palm_canvas.any()
    eng.close()
    assert not eng._palm_canvas.any() and not eng._crop.any() and not eng._palm_blob.any()


def test_works_with_the_network_blocked(blocked_network):
    eng = hand_engine_factory(Settings())()
    try:
        eng.detect(np.zeros((480, 640, 3), np.uint8), 0)
    finally:
        eng.close()
    assert network_guard.attempts() == 0


def test_a_modified_model_is_refused(tmp_path):
    spec = MODELS["palm"]
    (tmp_path / spec.filename).write_bytes(b"not the real model")
    with pytest.raises(ModelError):
        load_verified(spec, tmp_path)
    with pytest.raises(ModelError):
        load_verified(ModelSpec("x", "missing.onnx", "", "0" * 64), tmp_path)
