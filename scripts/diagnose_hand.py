"""Diagnose hand detection and the engagement posture, numbers only.

Waits until the camera is free, then until a hand appears, then measures for a
few seconds while the person holds an open palm. Prints aggregated numbers:
how often the hand is seen, how the detector and the tracker behave, and the
posture measurements used by the engagement gesture. No image is shown, written
or kept; nothing is stored on disk.

Usage: .venv\\Scripts\\python.exe scripts\\diagnose_hand.py [seconds]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sanscontact.privacy import network_guard  # noqa: E402

network_guard.install()

import numpy as np  # noqa: E402

from sanscontact.capture.camera import CameraSpec  # noqa: E402
from sanscontact.capture.devices import find_camera  # noqa: E402
from sanscontact.config.settings import Settings  # noqa: E402
from sanscontact.interpretation.engagement import EngagementDetector  # noqa: E402
from sanscontact.interpretation.hand_pose import features, scaled_points, straightness  # noqa: E402
from sanscontact.perception.engines import hand_engine_factory  # noqa: E402
from sanscontact.perception.types import FINGERS, THUMB  # noqa: E402
from sanscontact.perception.webcam import WebcamHandSource  # noqa: E402


def pct(values, q):
    return round(float(np.percentile(values, q)), 3) if values else None


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    settings = Settings()
    camera = find_camera(settings.camera_backend, settings.camera_name)
    if camera is None:
        print(json.dumps({"error": "no eligible camera"}))
        return 1
    spec = CameraSpec(camera.backend, camera.index, camera.name, settings.frame_width, settings.frame_height,
                      settings.frame_rate)
    engines = []

    def factory():
        engines.append(hand_engine_factory(settings)())
        return engines[-1]

    # Wait (up to 3 minutes) for the camera to be free and deliver a steady stream.
    source = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        failures: list[str] = []
        source = WebcamHandSource(spec, factory, on_failure=failures.append)
        source.start()
        seq, count, started = 0, 0, time.monotonic()
        while time.monotonic() - started < 8.0 and not failures:
            obs = source.latest(seq, timeout=1.0)
            if obs is not None:
                seq, count = obs.seq, count + 1
            if count >= 45:  # about 1.5 s of frames at 30 i/s: the camera is ours
                break
        if count >= 45 and not failures:
            break
        source.stop()
        source = None
        time.sleep(2.0)
    if source is None:
        print(json.dumps({"error": "camera not available"}))
        return 1

    rows = []
    try:
        # Wait (up to 3 minutes) for a hand, then measure.
        last_seq, start = 0, None
        hard_stop = time.monotonic() + 180 + seconds
        while time.monotonic() < hard_stop:
            obs = source.latest(last_seq, timeout=0.5)
            if obs is None:
                continue
            last_seq = obs.seq
            if start is None:
                if not obs.hands:
                    continue
                start = time.monotonic()
                for key in engines[-1].counters:
                    engines[-1].counters[key] = 0
            if time.monotonic() - start > seconds:
                break
            row = {"t": time.monotonic() - start, "hand": bool(obs.hands), "presence": engines[-1].last_presence}
            if obs.hands:
                hand = max(obs.hands, key=lambda h: features(h, obs.aspect).size)
                pose = features(hand, obs.aspect)
                points = scaled_points(hand.landmarks, obs.aspect)
                row.update(
                    pose=pose,
                    straight=[straightness(points, f) for f in FINGERS],
                    thumb_straight=straightness(points, THUMB[1:]),
                    thumb_away=float(np.linalg.norm(points[4] - points[5])) / pose.size,
                    aspect=obs.aspect,
                )
            rows.append(row)
        counters = dict(engines[-1].counters)
        fps = source.fps
    finally:
        source.stop()

    with_hand = [r for r in rows if r["hand"]]
    runs, run = [], 0
    for r in rows:
        run = run + 1 if r["hand"] else 0
        runs.append(run)
    engagement = EngagementDetector(hold_s=settings.engagement_hold_s)
    fired = sum(engagement.update(r.get("pose"), r["t"], r.get("aspect", 4 / 3)) for r in rows)
    drift = []
    for a, b in zip(with_hand, with_hand[1:], strict=False):
        if b["t"] - a["t"] < 0.1:
            pa, pb = a["pose"], b["pose"]
            drift.append(np.hypot((pb.center[0] - pa.center[0]) * a["aspect"], pb.center[1] - pa.center[1]) / pa.size)
    report = {
        "frames": len(rows),
        "fps": round(fps, 1),
        "hand_seen_percent": round(100 * len(with_hand) / len(rows)) if rows else 0,
        "longest_continuous_hand_frames": max(runs) if runs else 0,
        "engine": counters,
        "presence_when_lost": {"p50": pct([r["presence"] for r in rows if not r["hand"]], 50)},
        "hand_size_image_height": {"p50": pct([r["pose"].size for r in with_hand], 50)},
        "open_palm_percent": round(100 * sum(r["pose"].open_palm for r in with_hand) / len(with_hand)) if with_hand
        else 0,
        "extended_percent_thumb_index_middle_ring_pinky": [
            round(100 * sum(r["pose"].extended[i] for r in with_hand) / len(with_hand)) if with_hand else 0
            for i in range(5)],
        "finger_straightness_p10_index_middle_ring_pinky": [pct([r["straight"][i] for r in with_hand], 10)
                                                            for i in range(4)],
        "thumb_straightness_p10": pct([r["thumb_straight"] for r in with_hand], 10),
        "thumb_away_p10": pct([r["thumb_away"] for r in with_hand], 10),
        "spread_deg_p10_im_mr_rp": [pct([r["pose"].spread_deg[i] for r in with_hand], 10) for i in range(3)],
        "spread_deg_p50_im_mr_rp": [pct([r["pose"].spread_deg[i] for r in with_hand], 50) for i in range(3)],
        "thumb_spread_deg_p10": pct([r["pose"].thumb_spread_deg for r in with_hand], 10),
        "palm_drift_per_frame_hand_sizes_p90": pct(drift, 90),
        "engagements_simulated": int(fired),
        "network_attempts": network_guard.attempts(),
    }
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
