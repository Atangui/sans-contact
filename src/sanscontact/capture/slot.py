"""Hand-off between threads that keeps only the newest item.

There is no queue: a new frame overwrites the previous one, so a slow consumer
never accumulates latency. Frame buffers are preallocated, reused and zeroed
when the camera stops.
"""

from __future__ import annotations

import threading
import time

import numpy as np


class FrameSlot:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._buffer: np.ndarray | None = None
        self._seq = 0
        self._t_ns = 0
        self._closed = False
        self.overwritten = 0
        self._taken_seq = 0

    def publish(self, frame: np.ndarray, t_ns: int) -> None:
        with self._cond:
            if self._closed:
                return
            if self._buffer is None or self._buffer.shape != frame.shape or self._buffer.dtype != frame.dtype:
                if self._buffer is not None:
                    self._buffer.fill(0)
                self._buffer = np.empty_like(frame)
            np.copyto(self._buffer, frame)
            if self._seq > self._taken_seq:
                self.overwritten += 1
            self._seq += 1
            self._t_ns = t_ns
            self._cond.notify_all()

    def take(self, dst: np.ndarray | None, after_seq: int, timeout: float) -> tuple[np.ndarray, int, int] | None:
        """Copy the newest frame newer than ``after_seq`` into ``dst`` (reused when possible)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._closed and self._seq <= after_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            if self._closed or self._buffer is None:
                return None
            if dst is None or dst.shape != self._buffer.shape or dst.dtype != self._buffer.dtype:
                if dst is not None:
                    dst.fill(0)
                dst = np.empty_like(self._buffer)
            np.copyto(dst, self._buffer)
            self._taken_seq = self._seq
            return dst, self._seq, self._t_ns

    def close(self) -> None:
        with self._cond:
            self._closed = True
            if self._buffer is not None:
                self._buffer.fill(0)
                self._buffer = None
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed


class LatestSlot[T]:
    """Same idea for small immutable results (no copy needed)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._item: T | None = None
        self._seq = 0
        self._closed = False

    def publish(self, item: T) -> None:
        with self._cond:
            if self._closed:
                return
            self._item = item
            self._seq += 1
            self._cond.notify_all()

    def take(self, after_seq: int, timeout: float) -> tuple[T, int] | None:
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._closed and self._seq <= after_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            if self._closed or self._item is None:
                return None
            return self._item, self._seq

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._item = None
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed
