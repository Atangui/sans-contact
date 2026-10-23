"""From a point in the camera image to a point on the desktop.

The image is mirrored (move the hand right, the cursor goes right). A
rectangular active zone, away from the image borders where detection is
weaker, is mapped onto the whole virtual desktop, all screens included.
"""

from __future__ import annotations

from dataclasses import dataclass

from sanscontact.geometry import Rect
from sanscontact.interpretation.hand_pose import PoseFeatures
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
