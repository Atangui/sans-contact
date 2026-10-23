"""Compare camera backends (opening time, real frame rate) without keeping any frame.

Frames are read into one reused buffer that is zeroed at the end; nothing is
displayed, written or analysed beyond counting them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sanscontact.capture.camera import CameraSpec, actual_size, open_capture
from sanscontact.capture.devices import find_camera


@dataclass(frozen=True)
class ProbeResult:
    backend: str
    camera: str | None
    opened: bool
    open_ms: float | None = None
    first_frame_ms: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None

    def score(self) -> float:
        """Higher is better: frame rate first, then opening time."""
        if not self.opened or not self.fps:
            return float("-inf")
        return self.fps - (self.open_ms or 0) / 1000.0


def probe(backend: str, camera_name: str | None, width: int, height: int, fps: int,
          seconds: float = 3.0) -> ProbeResult:
    device = find_camera(backend, camera_name)
    if device is None:
        return ProbeResult(backend, camera_name, opened=False)
    spec = CameraSpec(backend, device.index, device.name, width, height, fps)
    t0 = time.perf_counter()
    cap = open_capture(spec)
    if cap is None:
        return ProbeResult(backend, device.name, opened=False)
    frame = None
    try:
        open_ms = (time.perf_counter() - t0) * 1000
        ok, frame = cap.read(frame)
        first_ms = (time.perf_counter() - t0) * 1000 if ok else None
        count = 0
        start = time.perf_counter()
        while time.perf_counter() - start < seconds:
            ok, frame = cap.read(frame)
            if ok:
                count += 1
        elapsed = time.perf_counter() - start
        w, h = actual_size(cap)
        return ProbeResult(backend, device.name, True, open_ms, first_ms, count / elapsed if elapsed else None, w, h)
    finally:
        cap.release()
        if frame is not None:
            frame.fill(0)


def best(results: list[ProbeResult]) -> ProbeResult | None:
    usable = [r for r in results if r.opened and r.fps]
    return max(usable, key=ProbeResult.score) if usable else None
