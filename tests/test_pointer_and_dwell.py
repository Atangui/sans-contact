import pytest

from sanscontact.geometry import Rect
from sanscontact.interpretation.dwell import DwellClicker
from sanscontact.interpretation.hand_pose import features
from sanscontact.interpretation.one_euro import OneEuroFilter2D
from sanscontact.interpretation.pointer import ActiveZone, Pointer
from tests.synthetic.hand_model import make_hand

DESK = Rect(0, 0, 1920, 1200)
SCREENS = [DESK]


def pointer(mode="absolute"):
    # Very light smoothing so positions are easy to predict.
    return Pointer(ActiveZone(), OneEuroFilter2D(min_cutoff=10.0, beta=1.0), mode=mode, rollback_s=0.1)


def drive(p, xs, start=0.0, freeze=False, rollback_first=False, y=0.45):
    out = []
    for i, x in enumerate(xs):
        out.append(p.update(x, y, start + i / 30, DESK, SCREENS, freeze=freeze, rollback=rollback_first and i == 0))
    return out


def test_freeze_with_rollback_returns_to_where_the_cursor_was():
    p = pointer()
    positions = drive(p, [0.40 + 0.002 * i for i in range(10)])
    frozen = drive(p, [0.45] * 5, start=10 / 30, freeze=True, rollback_first=True)
    assert len(set(frozen)) == 1
    assert frozen[0] in positions[-5:-1]  # a position from about 0.1 s before
    assert frozen[0] != positions[-1]


def test_absolute_mode_jumps_back_after_a_freeze():
    p = pointer()
    drive(p, [0.5] * 10)
    drive(p, [0.3] * 10, start=1.0, freeze=True)
    after = drive(p, [0.3] * 15, start=2.0)
    assert after[-1][0] > 1300  # hand on the image left: cursor on the right, at its absolute place


def test_relative_mode_clutch_lets_the_hand_move_back():
    p = pointer("relative")
    p.reset(cursor=(960, 600))
    drive(p, [0.5] * 5)
    moved = drive(p, [0.5 - 0.01 * i for i in range(1, 11)], start=0.2)
    assert moved[-1][0] > 960  # hand moves left in the image: cursor moves right
    held = drive(p, [0.5] * 10, start=1.0, freeze=True)  # fist: bring the hand back
    assert len(set(held)) == 1
    after = drive(p, [0.5] * 5, start=2.0)
    assert after[-1] == pytest.approx(held[-1], abs=2)  # no jump when the clutch opens


def test_positions_stay_on_screen():
    p = pointer()
    out = drive(p, [-0.5, 1.5, 2.0])
    assert all(DESK.contains(x, y) for x, y in out)


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        Pointer(ActiveZone(), OneEuroFilter2D(), mode="teleport")


def test_dwell_click_after_staying_still_then_rearms_after_moving_away():
    dwell = DwellClicker(dwell_s=1.0, radius_px=10, rearm_px=30)
    t, clicks = 0.0, []
    for _ in range(45):
        clicks.append(dwell.update((500, 500), t, allowed=True))
        t += 1 / 30
    assert clicks.count(True) == 1
    assert not any(dwell.update((505, 503), t + i, True) for i in range(3))  # still there: no second click
    elsewhere = [dwell.update((600, 500), t + 3 + i / 30, True) for i in range(40)]
    assert elsewhere.count(True) == 1  # moved away: armed again


def test_dwell_does_nothing_when_not_allowed_or_moving():
    dwell = DwellClicker(dwell_s=0.5)
    assert not any(dwell.update((100 + 5 * i, 100), i / 30, True) for i in range(60))
    assert not any(dwell.update((100, 100), i / 30, False) for i in range(60))


def test_reference_features_are_consistent_for_the_pointer():
    hand = make_hand("relaxed", center=(0.3, 0.6))
    assert features(hand, 4 / 3).center == pytest.approx((0.3, 0.6))
