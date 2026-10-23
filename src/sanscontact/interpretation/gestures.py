"""Gesture state machine: clicks, double click, drag and drop, scrolling, clutch.

Explicit states, one transition table (see docs/GESTES.md):

    POINT ──pinch thumb+index──▶ LEFT_PENDING ──held min_press──▶ LEFT_DOWN ──release──▶ POINT (click)
                                       │ released too soon: ignored          │ hand moves
                                       ▼                                     ▼
                                     POINT                                 DRAG ──release──▶ POINT (drop)
    POINT ──pinch thumb+middle, index away──▶ RIGHT_PENDING ──▶ RIGHT_DOWN ──release──▶ POINT (right click)
    POINT ──index+middle straight, ring+pinky folded──▶ SCROLL ──posture lost──▶ POINT
    POINT ──fist──▶ CLUTCH (cursor frozen) ──fist opened──▶ POINT

Robustness:
- every distance is divided by the hand size;
- hysteresis: a pinch starts below ``press`` and ends above ``release`` (> press);
- minimum durations: a pinch shorter than ``min_press_s`` is ignored, postures need
  ``posture_frames`` consecutive frames;
- the cursor freezes as soon as a pinch starts and is put back where it was just
  before (rollback), so the click lands where the person aimed;
- after a click the cursor stays frozen during the double-click time, so a second
  pinch makes a double click Windows accepts;
- a fist always wins over a pinch (in a fist the thumb rests near the fingers).

The machine is pure: it returns actions, the caller sends them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from sanscontact.interpretation.hand_pose import PoseFeatures

WHEEL_DELTA = 120


class State(StrEnum):
    POINT = "point"
    CLUTCH = "clutch"
    LEFT_PENDING = "left_pending"
    LEFT_DOWN = "left_down"
    DRAG = "drag"
    RIGHT_PENDING = "right_pending"
    RIGHT_DOWN = "right_down"
    SCROLL = "scroll"


class Action(StrEnum):
    LEFT_DOWN = "left_down"
    LEFT_UP = "left_up"
    RIGHT_DOWN = "right_down"
    RIGHT_UP = "right_up"
    WHEEL = "wheel"  # vertical, positive = scroll up
    HWHEEL = "hwheel"  # horizontal, positive = scroll right


@dataclass(frozen=True)
class MouseAction:
    action: Action
    amount: int = 0


@dataclass(frozen=True)
class GestureConfig:
    press: float = 0.25
    release: float = 0.38
    min_press_s: float = 0.06
    drag_start: float = 0.35  # palm travel while pinched, in hand sizes
    double_click_s: float = 0.5
    double_click_move: float = 0.4  # palm travel that cancels the double-click freeze, in hand sizes
    posture_frames: int = 2
    scroll_dead_zone: float = 0.10  # in hand sizes
    scroll_speed: float = 12.0  # wheel notches per second, per hand size beyond the dead zone
    scroll_smooth: bool = True  # False: whole notches only (WHEEL_DELTA), for applications that need them
    scroll_invert: bool = False
    lost_release_s: float = 0.25  # a button never stays down longer than this once the hand is lost

    def __post_init__(self) -> None:
        if not 0 < self.press < self.release:
            raise ValueError("pinch thresholds must satisfy 0 < press < release")


@dataclass(frozen=True)
class GestureFrame:
    state: State
    freeze: bool
    rollback: bool = False
    actions: tuple[MouseAction, ...] = ()
    events: tuple[str, ...] = ()
    pinch_index: float = 1.0
    pinch_middle: float = 1.0


@dataclass
class _Context:
    since: float = 0.0
    anchor: tuple[float, float] = (0.0, 0.0)
    frames: int = 0
    scroll_acc: list[float] = field(default_factory=lambda: [0.0, 0.0])


def intent(pose: PoseFeatures, config: GestureConfig) -> str:
    """Which gesture a single posture asks for, before any timing: the coherence rules.

    Order matters: the fist wins (its thumb rests near the fingers), then the pinches,
    then the two-finger posture. Everything else is plain pointing.
    """
    if pose.fist:
        return "clutch"
    if pose.pinch_index < config.press and pose.pinch_middle >= config.press and not pose.curled[0]:
        return "left"
    if pose.pinch_middle < config.press and pose.pinch_index > config.release and not pose.curled[1]:
        return "right"
    if pose.two_fingers(config.release):
        return "scroll"
    return "point"


class GestureMachine:
    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self.state = State.POINT
        self._ctx = _Context()
        self._fist_frames = 0
        self._two_frames = 0
        self._last_t: float | None = None
        self._last_seen: float | None = None
        self._freeze_until = 0.0
        self._freeze_anchor = (0.0, 0.0)
        self._last_click_t = -math.inf
        self.counts = {"click": 0, "double_click": 0, "right_click": 0, "drag": 0, "scroll": 0, "clutch": 0,
                       "ignored": 0}

    # ---- public API --------------------------------------------------------------------------
    def update(self, pose: PoseFeatures, t: float, aspect: float = 4 / 3) -> GestureFrame:
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        self._last_seen = t
        self._fist_frames = self._fist_frames + 1 if pose.fist else 0
        self._two_frames = self._two_frames + 1 if pose.two_fingers(self.config.release) else 0
        handler = getattr(self, f"_on_{self.state.value}")
        frame = handler(pose, t, dt, aspect)
        for event in frame.events:
            if event in self.counts:
                self.counts[event] += 1
        return frame

    def hand_missing(self, t: float) -> GestureFrame:
        """No hand this frame. Buttons are released if it lasts more than ``lost_release_s``."""
        self._last_t = t
        if self._last_seen is not None and t - self._last_seen >= self.config.lost_release_s:
            actions = self.reset()
            return GestureFrame(State.POINT, freeze=False, actions=actions, events=("lost",) if actions else ())
        return GestureFrame(self.state, freeze=self.state is not State.DRAG)

    def reset(self) -> tuple[MouseAction, ...]:
        """Back to POINT; returns the button releases needed so nothing stays pressed."""
        actions = self._releases()
        self.state = State.POINT
        self._ctx = _Context()
        self._fist_frames = self._two_frames = 0
        self._freeze_until = 0.0
        return actions

    # ---- states -----------------------------------------------------------------------------
    def _on_point(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        c = self.config
        frozen = t < self._freeze_until
        if frozen and _travel(self._freeze_anchor, pose, aspect) > c.double_click_move:
            self._freeze_until = 0.0
            frozen = False
        wanted = intent(pose, c)
        if wanted == "clutch" and self._fist_frames >= c.posture_frames:
            return self._go(State.CLUTCH, pose, t, freeze=True, events=("clutch",))
        if wanted == "left":
            return self._go(State.LEFT_PENDING, pose, t, freeze=True, rollback=not frozen)
        if wanted == "right":
            return self._go(State.RIGHT_PENDING, pose, t, freeze=True, rollback=not frozen)
        if wanted == "scroll" and self._two_frames >= c.posture_frames:
            return self._go(State.SCROLL, pose, t, freeze=True, events=("scroll",))
        return self._frame(freeze=frozen, pose=pose)

    def _on_left_pending(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        c = self.config
        if pose.fist or pose.pinch_index > c.release:
            return self._go(State.POINT, pose, t, freeze=False, events=("ignored",))
        if t - self._ctx.since >= c.min_press_s:
            self.state = State.LEFT_DOWN
            return self._frame(freeze=True, pose=pose, actions=(MouseAction(Action.LEFT_DOWN),))
        return self._frame(freeze=True, pose=pose)

    def _on_left_down(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        c = self.config
        if pose.pinch_index > c.release:
            double = t - self._last_click_t <= c.double_click_s
            self._last_click_t = -math.inf if double else t
            # Keep the cursor still where the pinch started, so a second pinch is a valid double click.
            self._freeze_until = t + c.double_click_s
            self._freeze_anchor = self._ctx.anchor
            return self._go(State.POINT, pose, t, freeze=True, actions=(MouseAction(Action.LEFT_UP),),
                            events=("click", "double_click") if double else ("click",))
        if _travel(self._ctx.anchor, pose, aspect) > c.drag_start:
            self.state = State.DRAG
            return self._frame(freeze=False, pose=pose, events=("drag",))
        return self._frame(freeze=True, pose=pose)

    def _on_drag(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        if pose.pinch_index > self.config.release:
            return self._go(State.POINT, pose, t, freeze=False, actions=(MouseAction(Action.LEFT_UP),),
                            events=("drop",))
        return self._frame(freeze=False, pose=pose)

    def _on_right_pending(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        c = self.config
        if pose.fist or pose.pinch_middle > c.release or pose.pinch_index < c.press:
            return self._go(State.POINT, pose, t, freeze=False, events=("ignored",))
        if t - self._ctx.since >= c.min_press_s:
            self.state = State.RIGHT_DOWN
            return self._frame(freeze=True, pose=pose, actions=(MouseAction(Action.RIGHT_DOWN),))
        return self._frame(freeze=True, pose=pose)

    def _on_right_down(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        if pose.pinch_middle > self.config.release:
            return self._go(State.POINT, pose, t, freeze=False, actions=(MouseAction(Action.RIGHT_UP),),
                            events=("right_click",))
        return self._frame(freeze=True, pose=pose)

    def _on_scroll(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        c = self.config
        if self._two_frames == 0:
            self._ctx.frames += 1
            if self._ctx.frames >= c.posture_frames:
                return self._go(State.POINT, pose, t, freeze=False)
            return self._frame(freeze=True, pose=pose)
        self._ctx.frames = 0
        # Mirrored view: the hand moving right on screen means x decreasing in the image.
        offset_x = -(pose.center[0] - self._ctx.anchor[0]) * aspect / pose.size
        offset_y = -(pose.center[1] - self._ctx.anchor[1]) / pose.size
        actions = []
        for axis, offset, kind in ((0, offset_x, Action.HWHEEL), (1, offset_y, Action.WHEEL)):
            excess = max(0.0, abs(offset) - c.scroll_dead_zone)
            velocity = math.copysign(excess * c.scroll_speed * WHEEL_DELTA, offset) if excess else 0.0
            if c.scroll_invert:
                velocity = -velocity
            self._ctx.scroll_acc[axis] += velocity * dt
            step = 1 if c.scroll_smooth else WHEEL_DELTA
            amount = int(self._ctx.scroll_acc[axis] / step) * step
            if amount:
                self._ctx.scroll_acc[axis] -= amount
                actions.append(MouseAction(kind, amount))
        return self._frame(freeze=True, pose=pose, actions=tuple(actions))

    def _on_clutch(self, pose: PoseFeatures, t: float, dt: float, aspect: float) -> GestureFrame:
        if self._fist_frames == 0:
            self._ctx.frames += 1
            if self._ctx.frames >= self.config.posture_frames:
                return self._go(State.POINT, pose, t, freeze=False)
        else:
            self._ctx.frames = 0
        return self._frame(freeze=True, pose=pose)

    # ---- helpers ----------------------------------------------------------------------------
    def _go(self, state: State, pose: PoseFeatures, t: float, freeze: bool, rollback: bool = False,
            actions: tuple[MouseAction, ...] = (), events: tuple[str, ...] = ()) -> GestureFrame:
        self.state = state
        self._ctx = _Context(since=t, anchor=pose.center)
        return self._frame(freeze=freeze, pose=pose, rollback=rollback, actions=actions, events=events)

    def _frame(self, freeze: bool, pose: PoseFeatures, rollback: bool = False,
               actions: tuple[MouseAction, ...] = (), events: tuple[str, ...] = ()) -> GestureFrame:
        return GestureFrame(self.state, freeze, rollback, actions, events, pose.pinch_index, pose.pinch_middle)

    def _releases(self) -> tuple[MouseAction, ...]:
        if self.state in (State.LEFT_DOWN, State.DRAG):
            return (MouseAction(Action.LEFT_UP),)
        if self.state is State.RIGHT_DOWN:
            return (MouseAction(Action.RIGHT_UP),)
        return ()


def _travel(anchor: tuple[float, float], pose: PoseFeatures, aspect: float) -> float:
    """Palm displacement from ``anchor``, in hand sizes."""
    return math.hypot((pose.center[0] - anchor[0]) * aspect, pose.center[1] - anchor[1]) / pose.size
