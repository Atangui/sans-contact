"""From a point in the camera image to a point on the desktop.

The image is mirrored (move the hand right, the cursor goes right). A
rectangular active zone, away from the image borders where detection is
weaker, is mapped onto the whole virtual desktop, all screens included.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from sanscontact.geometry import Rect, clamp_to_screens
from sanscontact.interpretation.hand_pose import PoseFeatures
from sanscontact.interpretation.one_euro import OneEuroFilter2D
from sanscontact.perception.types import INDEX, HandObservation


@dataclass(frozen=True)
class ActiveZone:
    x0: float = 0.2
    y0: float = 0.15
    x1: float = 0.8
    y1: float = 0.75

    @classmethod
    def from_list(cls, values: list[float]) -> ActiveZone:
        return cls(*values)


def reference_point(hand: HandObservation, pose: PoseFeatures, mode: str) -> tuple[float, float]:
    """A stable point: palm centre or index base, never the fingertip (it moves when pinching)."""
    if mode == "index_mcp":
        x, y = hand.landmarks[INDEX[0], :2]
        return float(x), float(y)
    return pose.center


def to_zone(x: float, y: float, zone: ActiveZone, mirror: bool = True) -> tuple[float, float]:
    if mirror:
        x = 1.0 - x
    u = (x - zone.x0) / (zone.x1 - zone.x0)
    v = (y - zone.y0) / (zone.y1 - zone.y0)
    return min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)


def zone_to_desktop(u: float, v: float, desktop: Rect) -> tuple[float, float]:
    return desktop.left + u * (desktop.width - 1), desktop.top + v * (desktop.height - 1)


class Pointer:
    """Where the cursor should be: mapping, smoothing, freezing, absolute or relative mode.

    - absolute (default): the active zone maps onto the whole desktop;
    - relative (option): hand movements move the cursor, faster movements further
      (acceleration); while frozen (clutch) the hand can be repositioned, like lifting a mouse.

    When a freeze starts with ``rollback``, the cursor goes back to where it was
    ``rollback_s`` earlier: closing a pinch moves the hand a little, the click must
    land where the person was aiming. Recent positions are kept in memory only.
    """

    def __init__(self, zone: ActiveZone, smoothing: OneEuroFilter2D, mode: str = "absolute",
                 relative_gain: float = 1.0, relative_accel: float = 0.5, rollback_s: float = 0.1) -> None:
        if mode not in ("absolute", "relative"):
            raise ValueError(f"unknown pointer mode {mode!r}")
        self.zone = zone
        self.smoothing = smoothing
        self.mode = mode
        self.relative_gain = relative_gain
        self.relative_accel = relative_accel
        self.rollback_s = rollback_s
        self.reset()

    def reset(self, cursor: tuple[int, int] | None = None) -> None:
        self.smoothing.reset()
        self._history: deque[tuple[float, int, int]] = deque(maxlen=60)
        self._frozen: tuple[int, int] | None = None
        self._cursor: tuple[float, float] | None = None if cursor is None else (float(cursor[0]), float(cursor[1]))
        self._previous: tuple[float, float, float] | None = None  # t, smoothed x, smoothed y

    @property
    def frozen(self) -> bool:
        return self._frozen is not None

    def update(self, x: float, y: float, t: float, desktop: Rect, screens: Sequence[Rect],
               freeze: bool = False, rollback: bool = False) -> tuple[int, int]:
        u, v = to_zone(x, y, self.zone)
        fx, fy = self.smoothing(*zone_to_desktop(u, v, desktop), t)
        if self.mode == "absolute" or self._cursor is None:
            wanted = (fx, fy)
        else:
            pt, px, py = self._previous if self._previous else (t, fx, fy)
            dx, dy = fx - px, fy - py
            dt = max(t - pt, 1e-3)
            speed = math.hypot(dx, dy) / dt  # pixels per second
            gain = self.relative_gain * (1.0 + self.relative_accel * min(speed / 1000.0, 3.0))
            wanted = (self._cursor[0] + dx * gain, self._cursor[1] + dy * gain)
        self._previous = (t, fx, fy)
        if freeze:
            if self._frozen is None:
                self._frozen = self._position_before(t) if rollback else self._current(wanted, screens)
            target = self._frozen
        else:
            self._frozen = None
            target = clamp_to_screens(wanted[0], wanted[1], screens)
        self._cursor = (float(target[0]), float(target[1]))
        self._history.append((t, target[0], target[1]))
        return target

    def _current(self, wanted: tuple[float, float], screens: Sequence[Rect]) -> tuple[int, int]:
        if self._history:
            return self._history[-1][1], self._history[-1][2]
        return clamp_to_screens(wanted[0], wanted[1], screens)

    def _position_before(self, t: float) -> tuple[int, int]:
        target_time = t - self.rollback_s
        best = None
        for when, x, y in self._history:
            if when <= target_time:
                best = (x, y)
            else:
                break
        if best is None and self._history:
            best = (self._history[0][1], self._history[0][2])
        if best is None:
            raise ValueError("no position yet")
        return best
