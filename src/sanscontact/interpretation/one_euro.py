"""One Euro filter (Casiez, Roussel, Vogel, CHI 2012): steady at rest, responsive in motion.

The cutoff frequency rises with speed: low cutoff (strong smoothing) when the
hand is still, higher cutoff (less lag) when it moves.
"""

from __future__ import annotations

import math


def _alpha(cutoff_hz: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter2D:
    """Filters a 2-D point; the speed driving the cutoff is the norm of the velocity."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.015, d_cutoff: float = 1.0) -> None:
        if min_cutoff <= 0 or d_cutoff <= 0 or beta < 0:
            raise ValueError("invalid One Euro parameters")
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._t: float | None = None
        self._x = (0.0, 0.0)
        self._dx = (0.0, 0.0)

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self._t is None:
            self._t = t
            self._x = (x, y)
            self._dx = (0.0, 0.0)
            return self._x
        dt = t - self._t
        if dt <= 0:
            return self._x
        self._t = t
        px, py = self._x
        raw_dx = ((x - px) / dt, (y - py) / dt)
        a_d = _alpha(self.d_cutoff, dt)
        dx = (a_d * raw_dx[0] + (1 - a_d) * self._dx[0], a_d * raw_dx[1] + (1 - a_d) * self._dx[1])
        speed = math.hypot(*dx)
        a = _alpha(self.min_cutoff + self.beta * speed, dt)
        self._x = (a * x + (1 - a) * px, a * y + (1 - a) * py)
        self._dx = dx
        return self._x
