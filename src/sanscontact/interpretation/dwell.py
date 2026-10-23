"""Click by dwelling: keep the cursor still for a moment to click (off by default).

An alternative to pinching for people with reduced mobility. It is off by
default, otherwise every pause to read would click. After a dwell click, the
cursor must move away before another one can happen.
"""

from __future__ import annotations

import math


class DwellClicker:
    def __init__(self, dwell_s: float = 1.0, radius_px: float = 12.0, rearm_px: float = 30.0) -> None:
        self.dwell_s = dwell_s
        self.radius_px = radius_px
        self.rearm_px = rearm_px
        self.reset()

    def reset(self) -> None:
        self._anchor: tuple[int, int] | None = None
        self._since = 0.0
        self._last_click: tuple[int, int] | None = None

    def progress(self, t: float) -> float:
        if self._anchor is None or not self._armed():
            return 0.0
        return min(1.0, (t - self._since) / self.dwell_s)

    def update(self, position: tuple[int, int] | None, t: float, allowed: bool) -> bool:
        """True exactly once when the cursor has stayed within ``radius_px`` for ``dwell_s``."""
        if not allowed or position is None:
            self._anchor = None
            return False
        if self._last_click is not None and _distance(position, self._last_click) > self.rearm_px:
            self._last_click = None
        if self._anchor is None or _distance(position, self._anchor) > self.radius_px:
            self._anchor, self._since = position, t
            return False
        if self._armed() and t - self._since >= self.dwell_s:
            self._last_click = self._anchor
            self._anchor = None
            return True
        return False

    def _armed(self) -> bool:
        return self._last_click is None


def _distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
