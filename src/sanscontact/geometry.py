"""Screen geometry in physical pixels (the process is PER_MONITOR_AWARE_V2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Half-open rectangle: right and bottom are excluded, as in Win32 RECT."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        return (min(max(x, self.left), self.right - 1), min(max(y, self.top), self.bottom - 1))


def union(rects: Sequence[Rect]) -> Rect:
    if not rects:
        raise ValueError("no rectangle")
    return Rect(min(r.left for r in rects), min(r.top for r in rects),
                max(r.right for r in rects), max(r.bottom for r in rects))


def clamp_to_screens(x: float, y: float, screens: Sequence[Rect]) -> tuple[int, int]:
    """Nearest pixel that lies on a real screen (the bounding box can contain dead areas)."""
    best: tuple[float, float] | None = None
    best_d = float("inf")
    for screen in screens:
        cx, cy = screen.clamp(x, y)
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_d:
            best, best_d = (cx, cy), d
    if best is None:
        raise ValueError("no screen")
    return int(round(best[0])), int(round(best[1]))
