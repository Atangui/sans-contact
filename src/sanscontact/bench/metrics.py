"""Aggregated technical metrics: rates, latencies, CPU and memory. No positions."""

from __future__ import annotations

import ctypes
import os
import threading
import time
from collections import deque
from ctypes import wintypes

import numpy as np

from sanscontact import _win32 as w


class RollingStats:
    def __init__(self, size: int = 300) -> None:
        self._values: deque[float] = deque(maxlen=size)
        self._lock = threading.Lock()

    def add(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    def snapshot(self) -> tuple[float, float, int]:
        """(mean, 95th percentile, count); zeros when empty."""
        with self._lock:
            values = np.fromiter(self._values, dtype=np.float64)
        if values.size == 0:
            return 0.0, 0.0, 0
        return float(values.mean()), float(np.percentile(values, 95)), int(values.size)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


STAGES = ("handoff", "convert", "detect", "interpret", "smooth", "inject", "total")


class PipelineMetrics:
    def __init__(self) -> None:
        self.stages = {name: RollingStats() for name in STAGES}
        self.frames = 0
        self.frames_with_hand = 0
        self.engagements = 0
        self.gestures: dict[str, int] = {}
        self._lock = threading.Lock()

    def count_gestures(self, events) -> None:
        """Count recognised gestures (numbers only: no time, no position)."""
        if not events:
            return
        with self._lock:
            for event in events:
                self.gestures[event] = self.gestures.get(event, 0) + 1

    def count_frame(self, hand_present: bool) -> None:
        with self._lock:
            self.frames += 1
            if hand_present:
                self.frames_with_hand += 1

    def add_ms(self, stage: str, ms: float) -> None:
        self.stages[stage].add(ms)

    def hand_ratio(self) -> float:
        return self.frames_with_hand / self.frames if self.frames else 0.0

    def reset(self) -> None:
        with self._lock:
            self.frames = self.frames_with_hand = 0
            self.gestures = {}
        for stats in self.stages.values():
            stats.clear()


class ProcessUsage:
    """CPU share (all cores = 100 %) and working set of this process."""

    def __init__(self) -> None:
        self._process = w.GetCurrentProcess()
        self._cpus = os.cpu_count() or 1
        self._last = self._sample()

    def _sample(self) -> tuple[float, float]:
        creation, exit_, kernel, user = (wintypes.FILETIME() for _ in range(4))
        w.GetProcessTimes(self._process, ctypes.byref(creation), ctypes.byref(exit_), ctypes.byref(kernel),
                          ctypes.byref(user))

        def seconds(ft: wintypes.FILETIME) -> float:
            return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7

        return time.perf_counter(), seconds(kernel) + seconds(user)

    def cpu_percent(self) -> float:
        now = self._sample()
        wall = now[0] - self._last[0]
        busy = now[1] - self._last[1]
        self._last = now
        return 100.0 * busy / (wall * self._cpus) if wall > 0 else 0.0

    def memory_mb(self) -> float:
        counters = w.PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(w.PROCESS_MEMORY_COUNTERS)
        if not w.K32GetProcessMemoryInfo(self._process, ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.WorkingSetSize / (1024 * 1024)
