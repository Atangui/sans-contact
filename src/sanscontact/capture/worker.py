"""Capture thread: reads frames into a reused buffer and publishes only the newest.

The camera is always released in ``finally``, and every frame buffer is zeroed
before the thread ends. Frames never leave memory.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np

from sanscontact.capture.camera import CameraSpec, actual_size, open_capture
from sanscontact.capture.slot import FrameSlot

READ_FAILURES_BEFORE_RECONNECT = 30
RECONNECT_WINDOW_S = 10.0


class CaptureWorker(threading.Thread):
    def __init__(
        self,
        spec: CameraSpec,
        slot: FrameSlot,
        on_failure: Callable[[str], None],
        on_opened: Callable[[int, int, float], None] | None = None,
        opener=open_capture,
        clock=time.perf_counter_ns,
    ) -> None:
        super().__init__(name="capture", daemon=True)
        self.spec = spec
        self.slot = slot
        self._on_failure = on_failure
        self._on_opened = on_opened
        self._open = opener
        self._clock = clock
        self._stop = threading.Event()
        self.frames = 0
        self.open_ms: float | None = None

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        cap = None
        frame: np.ndarray | None = None
        try:
            started = time.perf_counter()
            cap = self._open(self.spec)
            if cap is None:
                self._on_failure("camera_busy")
                return
            self.open_ms = (time.perf_counter() - started) * 1000
            if self._on_opened is not None:
                width, height = actual_size(cap)
                self._on_opened(width, height, self.open_ms)
            failures = 0
            while not self._stop.is_set():
                ok, frame = cap.read(frame)
                if not ok or frame is None:
                    failures += 1
                    if failures >= READ_FAILURES_BEFORE_RECONNECT:
                        cap.release()
                        cap = self._reconnect()
                        if cap is None:
                            if not self._stop.is_set():
                                self._on_failure("camera_lost")
                            return
                        failures = 0
                    else:
                        time.sleep(0.01)
                    continue
                failures = 0
                self.slot.publish(frame, self._clock())
                self.frames += 1
        finally:
            if cap is not None:
                cap.release()
            if frame is not None:
                frame.fill(0)
            self.slot.close()

    def _reconnect(self):
        deadline = time.monotonic() + RECONNECT_WINDOW_S
        while not self._stop.is_set() and time.monotonic() < deadline:
            cap = self._open(self.spec)
            if cap is not None:
                return cap
            self._stop.wait(1.0)
        return None
