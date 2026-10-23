"""Coherence analysis (docs/GESTES.md): no posture can be taken for another gesture."""

import itertools

import numpy as np
import pytest

from sanscontact.interpretation.gestures import GestureConfig, intent
from sanscontact.interpretation.hand_pose import features
from tests.synthetic.hand_model import make_hand

EXPECTED = {
    "open": "point",  # engagement in standby, plain pointing once active
    "relaxed": "point",
    "point": "point",  # index pointing at something: still just pointing
    "fist": "clutch",
    "two_fingers": "scroll",
    "pinch_index": "left",
    "pinch_middle": "right",
}
VARIATIONS = list(itertools.product((0.10, 0.18, 0.30), (-35, 0, 35), ("left", "right"), (4 / 3, 16 / 9)))


@pytest.mark.parametrize("posture", sorted(EXPECTED))
def test_each_posture_triggers_only_its_gesture(posture):
    config = GestureConfig()
    for size, angle, side, aspect in VARIATIONS:
        hand = make_hand(posture, size=size, angle_deg=angle, person_hand=side, aspect=aspect)
        got = intent(features(hand, aspect), config)
        assert got == EXPECTED[posture], (posture, size, angle, side, aspect, got)


@pytest.mark.parametrize("posture", sorted(EXPECTED))
def test_robust_to_landmark_noise(posture):
    config = GestureConfig()
    rng = np.random.default_rng(7)
    results = [intent(features(make_hand(posture, noise=0.015, rng=rng), 4 / 3), config) for _ in range(50)]
    assert results.count(EXPECTED[posture]) >= 48  # at most 2 noisy frames out of 50, absorbed by debouncing


def test_half_closed_pinches_never_click():
    config = GestureConfig()
    for finger in ("index", "middle"):
        for amount in np.linspace(0.0, 0.6, 25):
            got = intent(features(make_hand(f"pinch_{finger}", pinch=amount), 4 / 3), config)
            assert got == "point", (finger, amount, got)


def test_pointing_postures_keep_the_thumb_far_from_the_fingertips():
    config = GestureConfig()
    for posture in ("open", "relaxed", "point", "two_fingers"):
        pose = features(make_hand(posture), 4 / 3)
        assert pose.pinch_index > config.release and (posture == "point" or pose.pinch_middle > config.release)
