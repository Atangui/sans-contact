"""The online demo (docs/demo/engine.js) must behave exactly like the Python code it copies.

The demo runs a JavaScript port of the synthetic hand, the posture features, the gesture machine,
the engagement detector, the One Euro filter, the pointer, the hand lock, the dwell click and the
power machine. These tests feed both versions the same synthetic frames and compare every result.
They need Node.js (present on the CI runners); without it they are skipped.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from sanscontact.geometry import Rect
from sanscontact.interpretation.dwell import DwellClicker
from sanscontact.interpretation.engagement import EngagementDetector
from sanscontact.interpretation.gestures import GestureConfig, GestureMachine, State, intent
from sanscontact.interpretation.hand_pose import features
from sanscontact.interpretation.lock import HandLock, preferred
from sanscontact.interpretation.one_euro import OneEuroFilter2D
from sanscontact.interpretation.pointer import ActiveZone, Pointer, reference_point
from sanscontact.perception.types import HandObservation
from sanscontact.power import PowerMachine, Reason
from tests.synthetic.hand_model import POSES, make_hand

NODE = shutil.which("node")
HARNESS = Path(__file__).parent / "js" / "engine_harness.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is needed to run the demo engine")

FPS = 30
ASPECT = 4 / 3
DESKTOP = (0, 0, 1280, 800)
TOL = 1e-9


def run_js(request: dict):
    result = subprocess.run([NODE, str(HARNESS)], input=json.dumps(request), capture_output=True, text=True,
                            check=True, timeout=120)
    return json.loads(result.stdout)


def as_json_hand(hand: HandObservation) -> dict:
    return {"landmarks": hand.landmarks[:, :2].astype(float).tolist(), "handedness": hand.handedness}


def pose_dict(pose) -> dict:
    return {
        "size": pose.size, "center": list(pose.center), "extended": list(pose.extended),
        "spread_deg": list(pose.spread_deg), "thumb_spread_deg": pose.thumb_spread_deg,
        "pinch_index": pose.pinch_index, "pinch_middle": pose.pinch_middle, "tip_to_palm": list(pose.tip_to_palm),
        "open_palm": pose.open_palm, "curled": list(pose.curled), "fist": pose.fist,
        "two_fingers": pose.two_fingers(0.38),
    }


def assert_close(python, js, where):
    if isinstance(python, bool | str) or python is None:
        assert python == js, where
    elif isinstance(python, float | int):
        assert math.isclose(python, js, rel_tol=TOL, abs_tol=TOL), (where, python, js)
    elif isinstance(python, list | tuple):
        assert len(python) == len(js), where
        for i, (p, j) in enumerate(zip(python, js, strict=True)):
            assert_close(p, j, f"{where}[{i}]")
    elif isinstance(python, dict):
        assert set(python) == set(js), (where, sorted(python), sorted(js))
        for key in python:
            assert_close(python[key], js[key], f"{where}.{key}")
    else:
        raise TypeError(type(python))


VARIATIONS = [
    {"size": size, "angle_deg": angle, "person_hand": side, "aspect": aspect, "center": [cx, cy]}
    for size, angle, side, aspect, (cx, cy) in [
        (0.10, -35.0, "left", 4 / 3, (0.5, 0.55)),
        (0.18, 0.0, "right", 4 / 3, (0.3, 0.4)),
        (0.30, 35.0, "left", 16 / 9, (0.62, 0.7)),
        (0.15, -8.0, "right", 16 / 9, (0.45, 0.5)),
    ]
]


def test_synthetic_hands_are_the_same():
    requests = []
    for pose in sorted(POSES):
        for variation in VARIATIONS:
            for pinch in ((0.0, 0.4, 1.0) if pose.startswith("pinch") else (1.0,)):
                requests.append({"pose": pose, "pinch": pinch, **variation})
    js = run_js({"kind": "hands", "hands": requests})
    for request, landmarks in zip(requests, js, strict=True):
        hand = make_hand(request["pose"], center=tuple(request["center"]), size=request["size"],
                         angle_deg=request["angle_deg"], person_hand=request["person_hand"],
                         aspect=request["aspect"], pinch=request["pinch"])
        # Both sides store float32 landmarks: allow one float32 step for a different rounding path.
        assert np.allclose(hand.landmarks[:, :2], np.array(landmarks), rtol=0, atol=1e-7), request


def test_features_and_intent_are_the_same():
    rng = np.random.default_rng(11)
    hands = []
    for pose in sorted(POSES):
        for variation in VARIATIONS:
            options = {k: v for k, v in variation.items() if k != "aspect"}
            options["center"] = tuple(options["center"])
            for _ in range(4):
                hands.append(make_hand(pose, aspect=ASPECT, noise=0.02, rng=rng,
                                       pinch=float(rng.uniform(0.0, 1.0)), **options))
    js = run_js({"kind": "features", "aspect": ASPECT, "hands": [as_json_hand(h) for h in hands]})
    config = GestureConfig()
    for i, (hand, got) in enumerate(zip(hands, js, strict=True)):
        pose = features(hand, ASPECT)
        expected = pose_dict(pose) | {"intent": intent(pose, config)}
        assert_close(expected, got, f"hand {i}")


# ---- a scripted session: every gesture, a second hand, a lost hand, a too-short pinch ----------

def _segment(frames, pose, start, end=None, pinch=(1.0, 1.0), present=True, other=None):
    return {"frames": frames, "pose": pose, "start": start, "end": end or start, "pinch": pinch,
            "present": present, "other": other}


def _pinch(pose, at, close=4, hold=5, open_=4):
    return [_segment(close, pose, at, pinch=(0.0, 1.0)), _segment(hold, pose, at),
            _segment(open_, pose, at, pinch=(1.0, 0.0))]


def session_segments():
    a, b, c = (0.45, 0.5), (0.6, 0.4), (0.4, 0.55)
    return [
        _segment(10, "relaxed", a, present=False),
        _segment(20, "relaxed", (0.5, 0.6), a),
        _segment(40, "open", a),
        _segment(30, "relaxed", a, b),
        *_pinch("pinch_index", b),  # click
        _segment(10, "relaxed", b),
        *_pinch("pinch_index", b, close=3, hold=3, open_=3),  # double click
        *_pinch("pinch_index", b, close=3, hold=3, open_=3),
        _segment(20, "relaxed", b),
        _segment(4, "pinch_index", b, pinch=(0.0, 1.0)),  # drag and drop
        _segment(4, "pinch_index", b),
        _segment(25, "pinch_index", b, c),
        _segment(4, "pinch_index", c, pinch=(1.0, 0.0)),
        _segment(10, "relaxed", c),
        *_pinch("pinch_middle", c),  # right click
        _segment(10, "relaxed", c),
        _segment(10, "two_fingers", c),  # scroll
        _segment(30, "two_fingers", c, (0.4, 0.70)),
        _segment(20, "two_fingers", (0.4, 0.70), (0.55, 0.45)),
        _segment(10, "relaxed", (0.55, 0.45)),
        _segment(20, "fist", (0.55, 0.45), (0.35, 0.5)),  # clutch
        _segment(10, "relaxed", (0.35, 0.5)),
        _segment(30, "relaxed", (0.35, 0.5), other=("pinch_index", (0.75, 0.45))),  # someone else's hand
        _segment(4, "pinch_index", (0.35, 0.5), pinch=(0.0, 1.0)),  # hand lost while pressed
        _segment(4, "pinch_index", (0.35, 0.5)),
        _segment(12, "relaxed", (0.35, 0.5), present=False),
        _segment(10, "relaxed", (0.35, 0.5)),
        _segment(120, "relaxed", (0.35, 0.5), present=False),  # gone for 4 s: back to standby
        _segment(40, "open", (0.5, 0.5)),
        _segment(10, "relaxed", (0.5, 0.5)),
        _segment(1, "pinch_index", (0.5, 0.5)),  # 33 ms pinch: ignored
        _segment(1, "pinch_index", (0.5, 0.5)),
        _segment(10, "relaxed", (0.5, 0.5)),
    ]


def session_frames():
    rng = np.random.default_rng(3)
    frames = []
    t = 0.0
    for seg in session_segments():
        for k in range(seg["frames"]):
            u = k / max(seg["frames"] - 1, 1)
            center = tuple(s + (e - s) * u for s, e in zip(seg["start"], seg["end"], strict=True))
            pinch = seg["pinch"][0] + (seg["pinch"][1] - seg["pinch"][0]) * u
            hands = []
            if seg["present"]:
                hands.append(make_hand(seg["pose"], center=center, size=0.18, angle_deg=-8.0, person_hand="right",
                                       aspect=ASPECT, noise=0.004, rng=rng, pinch=pinch))
            if seg["other"]:
                other_pose, other_center = seg["other"]
                hands.append(make_hand(other_pose, center=other_center, size=0.15, angle_deg=12.0,
                                       person_hand="left", aspect=ASPECT, noise=0.004, rng=rng, pinch=1.0))
            frames.append((t, hands))
            t += 1 / FPS
    return frames


def run_python_session(frames, pointer_mode: str, scroll_smooth: bool, pointer_landmark: str):
    desktop = Rect(*DESKTOP)
    engagement = EngagementDetector()
    lock = HandLock()
    gestures = GestureMachine(GestureConfig(scroll_smooth=scroll_smooth))
    pointer = Pointer(ActiveZone(), OneEuroFilter2D(), mode=pointer_mode, rollback_s=0.1)
    dwell = DwellClicker()
    active = False
    out = []

    def frame_dict(f):
        return {"state": f.state.value, "freeze": f.freeze, "rollback": f.rollback, "events": list(f.events),
                "actions": [[a.action.value, a.amount] for a in f.actions]}

    for t, hands in frames:
        candidates = [(hand, features(hand, ASPECT)) for hand in hands]
        row: dict = {"active": active}
        if not active:
            candidate = preferred(candidates, "any")
            engaged = engagement.update(candidate[1] if candidate else None, t, ASPECT)
            row["engaged"] = engaged
            row["progress"] = engagement.progress(t)
            if engaged and candidate:
                lock.engage(candidate, t)
                active = True
                gestures.reset()
                dwell.reset()
                pointer.reset(cursor=(0, 0))
            out.append(row)
            continue
        selected = lock.select(candidates, t, ASPECT)
        row["selected"] = None if selected is None else next(i for i, c in enumerate(candidates) if c[0] is selected[0])
        if selected is None:
            row["gesture"] = frame_dict(gestures.hand_missing(t))
            if lock.missing_for(t) > 3.0:
                active = False
                row["lost"] = True
                engagement.reset()
                row["released"] = [[a.action.value, a.amount] for a in gestures.reset()]
                lock.release()
            out.append(row)
            continue
        hand, pose = selected
        g = gestures.update(pose, t, ASPECT)
        row["gesture"] = frame_dict(g)
        x, y = reference_point(hand, pose, pointer_landmark)
        target = pointer.update(x, y, t, desktop, [desktop], freeze=g.freeze, rollback=g.rollback)
        row["cursor"] = list(target)
        row["dwell"] = dwell.update(target, t, g.state is State.POINT and not g.freeze)
        out.append(row)
    return {"frames": out, "counts": gestures.counts}


@pytest.mark.parametrize(("pointer_mode", "scroll_smooth", "pointer_landmark"), [
    ("absolute", True, "palm_center"),
    ("relative", False, "palm_center"),
    ("absolute", True, "index_mcp"),
])
def test_a_whole_session_is_the_same(pointer_mode, scroll_smooth, pointer_landmark):
    frames = session_frames()
    expected = run_python_session(frames, pointer_mode, scroll_smooth, pointer_landmark)
    got = run_js({
        "kind": "session", "aspect": ASPECT, "desktop": list(DESKTOP), "pointer_mode": pointer_mode,
        "scroll_smooth": scroll_smooth, "pointer_landmark": pointer_landmark,
        "frames": [{"t": t, "hands": [as_json_hand(h) for h in hands]} for t, hands in frames],
    })
    for i, (p, j) in enumerate(zip(expected["frames"], got["frames"], strict=True)):
        assert_close(p, j, f"frame {i}")
    assert expected["counts"] == got["counts"]
    # The session really exercises every gesture (otherwise this test would prove little).
    counts = expected["counts"]
    assert counts["click"] >= 3 and counts["double_click"] == 1 and counts["drag"] == 1
    assert counts["right_click"] == 1 and counts["scroll"] == 1 and counts["clutch"] == 1 and counts["ignored"] >= 1
    assert any(row.get("lost") for row in expected["frames"])
    assert any(row.get("gesture", {}).get("events") == ["lost"] for row in expected["frames"])


def test_power_machine_is_the_same():
    ops = [
        ("engaged", None, 0.0), ("activate", None, 0.0), ("activate", None, 0.1), ("engaged", None, 1.0),
        ("pointer_taken", Reason.PHYSICAL_MOUSE.value, 2.0), ("tick", None, 20.0), ("engaged", None, 21.0),
        ("hand_lost", None, 22.0), ("engaged", None, 23.0), ("pointer_taken", Reason.ELEVATED_WINDOW.value, 24.0),
        ("tick", None, 53.9), ("tick", None, 54.0), ("toggle", None, 55.0), ("deactivate", Reason.ERROR.value, 56.0),
        ("toggle", None, 57.0),
    ]
    got = run_js({"kind": "power", "pause_timeout_s": 30.0, "ops": [list(op) for op in ops]})
    machine = PowerMachine(30.0)
    for (op, arg, now), js in zip(ops, got, strict=True):
        if op == "pointer_taken":
            transition = machine.pointer_taken(Reason(arg), now)
        elif op == "tick":
            transition = machine.tick(now)
        elif op == "deactivate":
            transition = machine.deactivate(Reason(arg))
        else:
            transition = getattr(machine, op)()
        expected = {
            "state": machine.state.value, "reason": machine.reason.value, "remaining": machine.pause_remaining(now),
            "transition": transition and [transition.previous.value, transition.state.value, transition.reason.value,
                                          transition.camera_started, transition.camera_stopped,
                                          transition.left_active],
        }
        assert_close(expected, js, op)
