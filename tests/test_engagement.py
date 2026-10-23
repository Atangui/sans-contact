import pytest

from sanscontact.interpretation.engagement import EngagementDetector
from sanscontact.interpretation.hand_pose import features
from tests.synthetic.hand_model import make_hand

FPS = 30
ASPECT = 4 / 3


def pose(posture="open", center=(0.5, 0.55)):
    return features(make_hand(posture, center=center), ASPECT)


def feed(detector, poses, start=0.0):
    fired = []
    for i, p in enumerate(poses):
        t = start + i / FPS
        if detector.update(p, t, ASPECT):
            fired.append(t)
    return fired


def test_still_open_palm_engages_after_hold_time_once():
    fired = feed(EngagementDetector(hold_s=1.0), [pose()] * 90)
    assert len(fired) == 1
    assert fired[0] == pytest.approx(1.0, abs=1.5 / FPS)


def test_moving_palm_never_engages():
    poses = [pose(center=(0.2 + 0.01 * i, 0.55)) for i in range(60)]  # sweeps across the image
    assert feed(EngagementDetector(hold_s=1.0), poses) == []


def test_other_postures_never_engage():
    for posture in ("relaxed", "fist", "point"):
        assert feed(EngagementDetector(), [pose(posture)] * 90) == []


def test_interruption_restarts_the_hold():
    poses = [pose()] * 20 + [pose("fist")] * 5 + [pose()] * 20
    assert feed(EngagementDetector(hold_s=1.0), poses) == []


def test_short_dropouts_are_tolerated():
    poses = [pose()] * 15 + [None] + [pose()] * 20
    assert len(feed(EngagementDetector(hold_s=1.0, grace_frames=2), poses)) == 1


def test_must_release_before_engaging_again():
    detector = EngagementDetector(hold_s=0.5)
    assert len(feed(detector, [pose()] * 60)) == 1
    assert len(feed(detector, [None] * 5 + [pose()] * 30, start=10.0)) == 1


def test_progress():
    detector = EngagementDetector(hold_s=1.0)
    feed(detector, [pose()] * 16)
    assert 0.4 < detector.progress(15 / FPS + 0.0) <= 0.55
