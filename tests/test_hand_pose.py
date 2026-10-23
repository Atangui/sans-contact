import pytest

from sanscontact.interpretation.hand_pose import features, person_hand
from tests.synthetic.hand_model import make_hand

SIZES = (0.08, 0.18, 0.35)
ANGLES = (-35, 0, 35)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("aspect", (4 / 3, 16 / 9))
def test_open_palm_is_recognised_at_any_distance_and_angle(size, angle, aspect):
    pose = features(make_hand("open", size=size, angle_deg=angle, aspect=aspect), aspect)
    assert pose.open_palm
    assert pose.size == pytest.approx(size, rel=1e-6)


@pytest.mark.parametrize("posture", ["relaxed", "fist", "point"])
@pytest.mark.parametrize("size", SIZES)
def test_other_postures_are_not_an_open_palm(posture, size):
    assert not features(make_hand(posture, size=size), 4 / 3).open_palm


def test_fingers_extended():
    assert features(make_hand("fist"), 4 / 3).extended[1:] == (False, False, False, False)
    assert features(make_hand("point"), 4 / 3).extended[1:] == (True, False, False, False)
    assert features(make_hand("relaxed"), 4 / 3).extended[1:] == (True, True, True, True)


def test_relaxed_hand_fails_on_spread_not_on_extension():
    pose = features(make_hand("relaxed"), 4 / 3)
    assert all(pose.extended[1:]) and sum(pose.spread_deg) < 24.0


def test_open_palm_matches_what_a_real_hand_measured():
    """Values measured on a real open palm (diagnose_hand.py, 10th percentiles): must count as open."""
    from sanscontact.interpretation.hand_pose import PoseFeatures

    real = PoseFeatures(size=0.3, center=(0.5, 0.5), extended=(False, True, True, True, True),
                        spread_deg=(12.1, 5.6, 22.9), thumb_spread_deg=3.6, pinch_index=0.9, pinch_middle=1.1)
    assert real.open_palm
    together = PoseFeatures(size=0.3, center=(0.5, 0.5), extended=(False, True, True, True, True),
                            spread_deg=(4.0, 3.0, 6.0), thumb_spread_deg=3.6, pinch_index=0.9, pinch_middle=1.1)
    assert not together.open_palm
    pinching = PoseFeatures(size=0.3, center=(0.5, 0.5), extended=(False, True, True, True, True),
                            spread_deg=(12.1, 5.6, 22.9), thumb_spread_deg=3.6, pinch_index=0.2, pinch_middle=1.1)
    assert not pinching.open_palm


def test_small_noise_keeps_the_open_palm():
    pose = features(make_hand("open", noise=0.01), 4 / 3)
    assert pose.open_palm


def test_palm_centre_is_where_we_put_it():
    pose = features(make_hand("open", center=(0.3, 0.6)), 4 / 3)
    assert pose.center == pytest.approx((0.3, 0.6), abs=1e-6)


def test_handedness_is_swapped_for_non_mirrored_frames():
    assert person_hand(make_hand(person_hand="right").handedness) == "right"
    assert person_hand(make_hand(person_hand="left").handedness) == "left"
    assert person_hand("?") == "unknown"
