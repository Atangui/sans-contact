"""Webcam hand source: capture thread + inference thread, newest frame only."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

import cv2
import numpy as np

from sanscontact.capture.camera import CameraSpec
from sanscontact.capture.slot import FrameSlot, LatestSlot
from sanscontact.capture.worker import CaptureWorker
from sanscontact.perception.source import EngineFactory, HandLandmarkEngine, PointerSource
from sanscontact.perception.types import Observation


class InferenceWorker(threading.Thread):
    def __init__(self, frames: FrameSlot, results: LatestSlot[Observation], engine_factory: EngineFactory,
                 on_failure: Callable[[str], None]) -> None:
        super().__init__(name="inference", daemon=True)
        self.frames = frames
        self.results = results
        self._factory = engine_factory
        self._on_failure = on_failure
        self._stop = threading.Event()
        self._times: deque[float] = deque(maxlen=60)

    def stop(self) -> None:
        self._stop.set()

    @property
    def fps(self) -> float:
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0

    def run(self) -> None:
        engine: HandLandmarkEngine | None = None
        bgr: np.ndarray | None = None
        rgb: np.ndarray | None = None
        last_seq = 0
        last_ts = -1
        try:
            engine = self._factory()
            while not self._stop.is_set():
                taken = self.frames.take(bgr, last_seq, timeout=0.2)
                if taken is None:
                    if self.frames.closed:
                        return
                    continue
                bgr, last_seq, t_capture = taken
                t_start = time.perf_counter_ns()
                if rgb is None or rgb.shape != bgr.shape:
                    rgb = np.empty_like(bgr)
                cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB, dst=rgb)
                timestamp_ms = max(t_capture // 1_000_000, last_ts + 1)
                last_ts = timestamp_ms
                t_infer = time.perf_counter_ns()
                hands = engine.detect(rgb, timestamp_ms)
                t_end = time.perf_counter_ns()
                height, width = bgr.shape[:2]
                self.results.publish(Observation(
                    seq=last_seq,
                    t_capture_ns=t_capture,
                    aspect=width / height,
                    hands=tuple(hands),
                    timings_ns={"handoff": t_start - t_capture, "convert": t_infer - t_start,
                                "detect": t_end - t_infer},
                ))
                self._times.append(time.perf_counter())
        except Exception:
            self._on_failure("error")
            raise
        finally:
            if engine is not None:
                engine.close()
            for buffer in (bgr, rgb):
                if buffer is not None:
                    buffer.fill(0)
            self.results.close()


class WebcamHandSource(PointerSource):
    kind = "webcam-hand"

    def __init__(self, spec: CameraSpec, engine_factory: EngineFactory, on_failure: Callable[[str], None],
                 on_opened: Callable[[int, int, float], None] | None = None) -> None:
        self.spec = spec
        self._factory = engine_factory
        self._on_failure = on_failure
        self._on_opened = on_opened
        self._frames: FrameSlot | None = None
        self._results: LatestSlot[Observation] | None = None
        self._capture: CaptureWorker | None = None
        self._inference: InferenceWorker | None = None

    def start(self) -> None:
        self._frames = FrameSlot()
        self._results = LatestSlot()
        self._capture = CaptureWorker(self.spec, self._frames, self._on_failure, self._on_opened)
        self._inference = InferenceWorker(self._frames, self._results, self._factory, self._on_failure)
        self._inference.start()
        self._capture.start()

    def stop(self) -> None:
        for worker in (self._capture, self._inference):
            if worker is not None:
                worker.stop()
        if self._frames is not None:
            self._frames.close()
        for worker in (self._capture, self._inference):
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=5.0)
        if self._results is not None:
            self._results.close()

    def latest(self, after_seq: int, timeout: float) -> Observation | None:
        if self._results is None:
            return None
        taken = self._results.take(after_seq, timeout)
        return taken[0] if taken else None

    @property
    def fps(self) -> float:
        return self._inference.fps if self._inference else 0.0

    @property
    def dropped_frames(self) -> int:
        return self._frames.overwritten if self._frames else 0

    @property
    def closed(self) -> bool:
        return self._results is None or self._results.closed
