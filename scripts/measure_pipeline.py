"""Measure the capture + detection chain with the real camera, numbers only.

The camera is on for the given duration (default 6 s); frames stay in memory and
are never shown or written. The mouse is not driven. Prints frame rate, stage
timings, end-to-end latency (frame read -> landmarks), share of frames with a
hand, CPU and memory, then checks that the camera was released.

Usage: .venv\\Scripts\\python.exe scripts\\measure_pipeline.py [seconds] [opencv_threads]
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sanscontact.privacy import network_guard  # noqa: E402

network_guard.install()

from sanscontact.bench.metrics import ProcessUsage, RollingStats  # noqa: E402
from sanscontact.capture.camera import CameraSpec  # noqa: E402
from sanscontact.capture.devices import find_camera  # noqa: E402
from sanscontact.config.settings import Settings  # noqa: E402
from sanscontact.perception.engines import hand_engine_factory  # noqa: E402
from sanscontact.perception.webcam import WebcamHandSource  # noqa: E402
from sanscontact.privacy.endpoints import EndpointWatch  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    settings = Settings()
    if len(sys.argv) > 2:
        settings.opencv_threads = int(sys.argv[2])
    camera = find_camera(settings.camera_backend, settings.camera_name)
    if camera is None:
        print("no eligible camera")
        return 1
    spec = CameraSpec(camera.backend, camera.index, camera.name, settings.frame_width, settings.frame_height,
                      settings.frame_rate)
    failures: list[str] = []
    opened: list[float] = []
    source = WebcamHandSource(spec, hand_engine_factory(settings), on_failure=failures.append,
                              on_opened=lambda w, h, ms: opened.append(ms))
    stats = {name: RollingStats(10_000) for name in ("handoff", "convert", "detect", "end_to_end")}
    usage = ProcessUsage()
    watch = EndpointWatch()
    frames = with_hand = 0
    source.start()
    deadline = time.monotonic() + seconds + 4.0  # opening the camera takes a few seconds
    measuring_since = None
    last_seq = 0
    try:
        while time.monotonic() < deadline and not failures:
            observation = source.latest(last_seq, timeout=0.2)
            watch.poll()
            if observation is None:
                continue
            if measuring_since is None:
                measuring_since = time.monotonic()
                deadline = measuring_since + seconds
                usage.cpu_percent()
            last_seq = observation.seq
            frames += 1
            with_hand += bool(observation.hands)
            for stage, ns in observation.timings_ns.items():
                stats[stage].add(ns / 1e6)
            stats["end_to_end"].add((time.perf_counter_ns() - observation.t_capture_ns) / 1e6)
        cpu = usage.cpu_percent()
        memory = usage.memory_mb()
        fps = source.fps
    finally:
        source.stop()
    released = not any(t.name in ("capture", "inference") and t.is_alive() for t in threading.enumerate())
    report = {
        "camera": camera.name,
        "backend": camera.backend,
        "open_ms": round(opened[0]) if opened else None,
        "frames": frames,
        "fps": round(fps, 1),
        "frames_with_hand_percent": round(100 * with_hand / frames) if frames else 0,
        "cpu_percent_all_cores": round(cpu, 1),
        "memory_mb": round(memory),
        "network_attempts": network_guard.attempts(),
        "network_endpoints": watch.count,
        "camera_released": released,
        "failures": failures,
    }
    for name, stat in stats.items():
        mean, p95, _ = stat.snapshot()
        report[f"{name}_ms"] = {"mean": round(mean, 2), "p95": round(p95, 2)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
