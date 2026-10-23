"""Only the person who made the engagement gesture controls the cursor.

Once engaged, a hand is accepted only if it is the continuation of the engaged
hand: same side, similar size, no jump. Any other hand is ignored and its data
dropped immediately; it cannot trigger anything.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from sanscontact.interpretation.hand_pose import PoseFeatures, person_hand
from sanscontact.perception.types import HandObservation

Candidate = tuple[HandObservation, PoseFeatures]


def preferred(candidates: Sequence[Candidate], hand_pref: str) -> Candidate | None:
    """Before engagement: the allowed hand closest to the camera (largest)."""
    allowed = [c for c in candidates if hand_pref == "any" or person_hand(c[0].handedness) == hand_pref]
    return max(allowed, key=lambda c: c[1].size, default=None)


class HandLock:
    def __init__(self, max_jump: float = 0.25, jump_growth_per_s: float = 0.5,
                 size_ratio: tuple[float, float] = (0.6, 1.6)) -> None:
        self.max_jump = max_jump  # normalised image units per frame
        self.jump_growth_per_s = jump_growth_per_s
        self.size_ratio = size_ratio
        self.release()

    @property
    def engaged(self) -> bool:
        return self._side is not None

    def engage(self, candidate: Candidate, t: float) -> None:
        hand, pose = candidate
        self._side = person_hand(hand.handedness)
        self._center = pose.center
        self._size = pose.size
        self._seen_at = t

    def release(self) -> None:
        self._side: str | None = None
        self._center = (0.0, 0.0)
        self._size = 0.0
        self._seen_at = 0.0

    def missing_for(self, t: float) -> float:
        return t - self._seen_at if self.engaged else 0.0

    def select(self, candidates: Sequence[Candidate], t: float, aspect: float = 4 / 3) -> Candidate | None:
        if not self.engaged:
            return None
        allowed_jump = self.max_jump + self.jump_growth_per_s * max(0.0, t - self._seen_at)
        best: Candidate | None = None
        best_d = float("inf")
        for hand, pose in candidates:
            side = person_hand(hand.handedness)
            if side != self._side and side != "unknown" and self._side != "unknown":
                continue
            ratio = pose.size / self._size if self._size else 1.0
            if not self.size_ratio[0] <= ratio <= self.size_ratio[1]:
                continue
            d = math.hypot((pose.center[0] - self._center[0]) * aspect, pose.center[1] - self._center[1])
            if d <= allowed_jump and d < best_d:
                best, best_d = (hand, pose), d
        if best is not None:
            self._center = best[1].center
            self._size = best[1].size
            self._seen_at = t
        return best
