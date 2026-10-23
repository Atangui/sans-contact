"""Gesture state machine on synthetic sequences (30 frames per second)."""

import numpy as np
import pytest

from sanscontact.interpretation.gestures import Action, GestureConfig, GestureMachine, State
from sanscontact.interpretation.hand_pose import features
from tests.synthetic.hand_model import make_hand

FPS = 30
DT = 1 / FPS
ASPECT = 4 / 3


def pose(posture="relaxed", center=(0.5, 0.5), **kw):
    return features(make_hand(posture, center=center, aspect=ASPECT, **kw), ASPECT)


def pinch(amount, finger="index", center=(0.5, 0.5)):
    return pose(f"pinch_{finger}", center=center, pinch=amount)


class Run:
    """Feeds a machine frame by frame and records everything it returns."""

    def __init__(self, config=None):
        self.machine = GestureMachine(config or GestureConfig())
        self.t = 0.0
        self.frames = []

    def feed(self, poses):
        for p in poses:
            self.frames.append(self.machine.update(p, self.t, ASPECT))
            self.t += DT
        return self

    def hold(self, p, seconds):
        return self.feed([p] * round(seconds * FPS))

    @property
    def actions(self):
        return [a.action for f in self.frames for a in f.actions]

    @property
    def events(self):
        return [e for f in self.frames for e in f.events]


def test_pinch_and_release_is_one_left_click():
    run = Run().hold(pose(), 0.2).hold(pinch(1.0), 0.15).hold(pinch(0.0), 0.2)
    assert run.actions == [Action.LEFT_DOWN, Action.LEFT_UP]
    assert run.events.count("click") == 1


def test_the_cursor_freezes_as_soon_as_the_pinch_starts_and_rolls_back():
    run = Run().hold(pose(), 0.2).feed([pinch(1.0)])
    first = run.frames[-1]
    assert first.freeze and first.rollback and first.state is State.LEFT_PENDING


def test_a_too_short_pinch_is_ignored():
    run = Run().hold(pose(), 0.2).feed([pinch(1.0)]).hold(pinch(0.0), 0.2)  # one frame only
    assert run.actions == [] and "ignored" in run.events


def test_hesitant_pinch_inside_the_hysteresis_band_does_nothing():
    cfg = GestureConfig()
    in_band = [p for p in (pinch(a) for a in np.linspace(0.0, 1.0, 101))
               if cfg.press + 0.01 < p.pinch_index < cfg.release - 0.01]
    assert len(in_band) > 5
    run = Run().hold(pose(), 0.2).feed(in_band + in_band[::-1])
    assert min(f.pinch_index for f in run.frames[6:]) > cfg.press
    assert run.actions == []


def test_hysteresis_keeps_the_button_down_until_release_threshold():
    cfg = GestureConfig()
    run = Run().hold(pose(), 0.2).hold(pinch(1.0), 0.15)
    middle = next(a for a in np.linspace(1.0, 0.0, 200) if cfg.press < pinch(a).pinch_index < cfg.release)
    run.hold(pinch(middle), 0.3)
    assert run.actions == [Action.LEFT_DOWN]  # still pressed inside the band
    run.hold(pinch(0.0), 0.1)
    assert run.actions == [Action.LEFT_DOWN, Action.LEFT_UP]


def test_moving_while_pinched_becomes_a_drag_and_drop():
    run = Run().hold(pose(), 0.2).hold(pinch(1.0), 0.15)
    path = [pinch(1.0, center=(0.5 - 0.01 * i, 0.5)) for i in range(15)]
    run.feed(path)
    drag_frames = [f for f in run.frames if f.state is State.DRAG]
    assert drag_frames and not drag_frames[-1].freeze  # the cursor follows during the drag
    run.hold(pinch(0.0, center=(0.36, 0.5)), 0.1)
    assert run.actions == [Action.LEFT_DOWN, Action.LEFT_UP]
    assert "drag" in run.events and "drop" in run.events


def test_two_quick_pinches_make_a_double_click_with_the_cursor_frozen_between():
    run = Run().hold(pose(), 0.2).hold(pinch(1.0), 0.1).hold(pinch(0.0), 0.15)
    between = run.frames[-3:]
    assert all(f.freeze for f in between)
    run.hold(pinch(1.0), 0.1).hold(pinch(0.0), 0.1)
    assert run.actions == [Action.LEFT_DOWN, Action.LEFT_UP] * 2
    assert "double_click" in run.events


def test_moving_away_after_a_click_unfreezes_the_cursor():
    run = Run().hold(pose(), 0.2).hold(pinch(1.0), 0.1).hold(pinch(0.0), 0.05)
    run.feed([pose(center=(0.5 - 0.02 * i, 0.5)) for i in range(1, 10)])
    assert not run.frames[-1].freeze


def test_thumb_and_middle_finger_is_a_right_click():
    run = Run().hold(pose(), 0.2).hold(pinch(1.0, "middle"), 0.15).hold(pinch(0.0, "middle"), 0.15)
    assert run.actions == [Action.RIGHT_DOWN, Action.RIGHT_UP]
    assert "right_click" in run.events


def test_fist_freezes_the_cursor_and_never_clicks():
    run = Run().hold(pose(), 0.2).hold(pose("fist"), 0.5)
    assert run.machine.state is State.CLUTCH and run.frames[-1].freeze
    assert run.actions == []
    run.hold(pose(), 0.2)
    assert run.machine.state is State.POINT and not run.frames[-1].freeze


def test_two_fingers_scroll_proportionally_to_the_offset():
    def scrolled(offset_y, seconds=1.0):
        run = Run().hold(pose(), 0.1).hold(pose("two_fingers"), 0.1)
        run.hold(pose("two_fingers", center=(0.5, 0.5 - offset_y)), seconds)
        return sum(a.amount for f in run.frames for a in f.actions if a.action is Action.WHEEL)

    assert scrolled(0.01) == 0  # inside the dead zone
    small, large = scrolled(0.06), scrolled(0.10)
    assert 0 < small < large  # hand up: scroll up, faster when further
    assert scrolled(-0.10) < 0


def test_horizontal_scroll_follows_the_mirrored_view():
    run = Run().hold(pose(), 0.1).hold(pose("two_fingers"), 0.1)
    run.hold(pose("two_fingers", center=(0.42, 0.5)), 0.5)  # image left = screen right
    horizontal = [a.amount for f in run.frames for a in f.actions if a.action is Action.HWHEEL]
    assert horizontal and sum(horizontal) > 0


def test_notch_mode_sends_whole_wheel_deltas():
    run = Run(GestureConfig(scroll_smooth=False)).hold(pose(), 0.1).hold(pose("two_fingers"), 0.1)
    run.hold(pose("two_fingers", center=(0.5, 0.40)), 1.0)
    amounts = [a.amount for f in run.frames for a in f.actions if a.action is Action.WHEEL]
    assert amounts and all(a % 120 == 0 for a in amounts)


def test_losing_the_hand_during_a_drag_releases_the_button():
    machine = GestureMachine()
    t = 0.0
    for p in [pose()] * 3 + [pinch(1.0)] * 5 + [pinch(1.0, center=(0.38, 0.5))] * 3:
        machine.update(p, t, ASPECT)
        t += DT
    assert machine.state is State.DRAG
    assert machine.hand_missing(t + 0.1).actions == ()  # brief dropout tolerated
    released = machine.hand_missing(t + 0.3)
    assert [a.action for a in released.actions] == [Action.LEFT_UP] and machine.state is State.POINT


def test_reset_releases_whatever_is_pressed():
    run = Run().hold(pose(), 0.1).hold(pinch(1.0, "middle"), 0.15)
    assert run.machine.state is State.RIGHT_DOWN
    assert [a.action for a in run.machine.reset()] == [Action.RIGHT_UP]
    assert run.machine.reset() == ()


def test_invalid_thresholds_are_refused():
    with pytest.raises(ValueError):
        GestureConfig(press=0.4, release=0.3)


def test_talking_with_the_hands_never_clicks():
    """Natural movements: postures change, the hand moves, the thumb never closes on a finger."""
    rng = np.random.default_rng(42)
    run = Run()
    for _ in range(120):  # about 2 minutes of gesturing, in short segments
        posture = rng.choice(["open", "relaxed", "point", "relaxed"])
        center = (0.35 + 0.3 * rng.random(), 0.35 + 0.3 * rng.random())
        angle = rng.uniform(-40, 40)
        size = rng.uniform(0.12, 0.3)
        frames = int(rng.integers(10, 40))
        run.feed([pose(posture, center=center, angle_deg=angle, size=size, noise=0.02,
                       rng=rng) for _ in range(frames)])
    clicks = [a for a in run.actions if a in (Action.LEFT_DOWN, Action.RIGHT_DOWN)]
    assert clicks == []
