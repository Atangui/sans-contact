"""Engagement gesture: open palm, fingers spread, held still for about one second."""

from __future__ import annotations

import math

from sanscontact.interpretation.hand_pose import PoseFeatures


class EngagementDetector:
    def __init__(self, hold_s: float = 1.0, max_motion: float = 0.35, grace_frames: int = 2) -> None:
        self.hold_s = hold_s
        self.max_motion = max_motion  # allowed palm drift, in hand sizes
        self.grace_frames = grace_frames
        self.reset()

    def reset(self) -> None:
        self._start: float | None = None
        self._anchor: tuple[float, float] | None = None
        self._misses = 0
        self._armed = True

    def progress(self, t: float) -> float:
        if self._start is None:
            return 0.0
        return min(1.0, (t - self._start) / self.hold_s)

    def update(self, pose: PoseFeatures | None, t: float, aspect: float = 4 / 3) -> bool:
        """Feed one frame; returns True once, when the gesture completes."""
        if pose is None or not pose.open_palm:
            self._misses += 1
            if self._misses > self.grace_frames:
                self._start = None
                self._anchor = None
                self._armed = True
            return False
        self._misses = 0
        if not self._armed:
            return False
        if self._start is None or self._anchor is None:
            self._start, self._anchor = t, pose.center
            return False
        drift = math.hypot((pose.center[0] - self._anchor[0]) * aspect, pose.center[1] - self._anchor[1])
        if drift / pose.size > self.max_motion:
            self._start, self._anchor = t, pose.center
            return False
        if t - self._start >= self.hold_s:
            self._start = None
            self._anchor = None
            self._armed = False
            return True
        return False
