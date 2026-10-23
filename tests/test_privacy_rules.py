"""Rules of section 3, checked on the source code and on synthetic runs."""

import ast
import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from sanscontact.capture.camera import CameraSpec
from sanscontact.capture.slot import FrameSlot, LatestSlot
from sanscontact.capture.worker import CaptureWorker
from sanscontact.perception.source import HandLandmarkEngine
from sanscontact.perception.webcam import InferenceWorker
from sanscontact.privacy import network_guard
from sanscontact.privacy.safe_log import format_exception
from tests.synthetic.hand_model import make_hand

SRC = Path(__file__).resolve().parents[1] / "src" / "sanscontact"
SOURCES = sorted(SRC.rglob("*.py"))

NETWORK_MODULES = {"socket", "_socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp", "asyncio",
                   "socketserver", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "websocket", "websockets", "webbrowser", "selectors"}
NETWORK_ALLOWED = {"privacy/network_guard.py"}  # it imports socket to disable it
IMAGE_WRITERS = {"imwrite", "imencode", "VideoWriter", "imshow", "namedWindow", "ImageGrab", "BitBlt",
                 "PrintWindow", "savez", "savez_compressed", "tofile"}


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


@pytest.mark.parametrize("path", SOURCES, ids=_rel)
def test_runtime_code_imports_no_network_library(path):
    if _rel(path) in NETWORK_ALLOWED:
        return
    found = set(_imports(ast.parse(path.read_text(encoding="utf-8")))) & NETWORK_MODULES
    assert not found, f"{_rel(path)} imports {found}"


@pytest.mark.parametrize("path", SOURCES, ids=_rel)
def test_runtime_code_never_writes_or_shows_images(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (names & IMAGE_WRITERS), f"{_rel(path)} uses {names & IMAGE_WRITERS}"


@pytest.mark.parametrize("path", SOURCES, ids=_rel)
def test_tracebacks_never_show_locals(path):
    text = path.read_text(encoding="utf-8")
    assert "show_locals" not in text and "capture_locals=True" not in text


def test_formatted_errors_contain_no_local_values():
    secret = "visible-only-as-a-local"

    def failing():
        local_value = secret  # noqa: F841
        raise RuntimeError("boom")

    try:
        failing()
    except RuntimeError as exc:
        text = format_exception(exc)
    assert "boom" in text and secret not in text


def test_guard_blocks_every_way_to_the_network(blocked_network):
    import _socket

    attempts = [
        lambda: socket.socket(),
        lambda: socket.create_connection(("example.org", 443), timeout=1),
        lambda: socket.getaddrinfo("example.org", 443),
        lambda: socket.gethostbyname("example.org"),
        lambda: _socket.socket(),
        lambda: socket.socketpair(),
    ]
    for attempt in attempts:
        with pytest.raises(OSError):
            attempt()
    assert network_guard.attempts() == len(attempts)


def test_guard_can_be_removed_for_tests_only(blocked_network):
    network_guard.uninstall()
    s = socket.socket()
    s.close()
    network_guard.install()
    with pytest.raises(network_guard.NetworkDisabledError):
        socket.socket()


class SyntheticEngine(HandLandmarkEngine):
    """Returns a synthetic hand; never looks at the pixels."""

    def __init__(self):
        self.calls = 0
        self.closed = False

    def detect(self, rgb, timestamp_ms):
        self.calls += 1
        return [make_hand("open")]

    def close(self):
        self.closed = True


def test_pipeline_processes_frames_with_the_network_blocked(blocked_network, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frames, results = FrameSlot(), LatestSlot()
    engine = SyntheticEngine()
    worker = InferenceWorker(frames, results, lambda: engine, on_failure=lambda reason: None)
    worker.start()
    rng = np.random.default_rng(0)
    for _ in range(20):
        frames.publish(rng.integers(0, 255, (48, 64, 3), dtype=np.uint8), time.perf_counter_ns())
        time.sleep(0.005)
    observation = None
    for _ in range(50):
        taken = results.take(0, timeout=0.1)
        if taken:
            observation = taken[0]
            break
    frames.close()
    worker.join(timeout=5)
    assert observation is not None and len(observation.hands) == 1
    assert engine.calls > 0 and engine.closed
    assert network_guard.attempts() == 0
    assert list(tmp_path.iterdir()) == []  # nothing written


class FakeCapture:
    def __init__(self, frames=5, fail_after=None):
        self.frames = frames
        self.fail_after = fail_after
        self.count = 0
        self.released = False
        self.last_buffer = None

    def read(self, buffer=None):
        self.count += 1
        if self.fail_after is not None and self.count > self.fail_after:
            return False, buffer
        if buffer is None:
            buffer = np.zeros((48, 64, 3), dtype=np.uint8)
        buffer[:] = 200
        self.last_buffer = buffer
        time.sleep(0.002)
        return True, buffer

    def get(self, prop):
        return 64 if prop == 3 else 48

    def release(self):
        self.released = True


def test_capture_releases_the_camera_and_zeroes_its_buffer():
    cap = FakeCapture()
    slot = FrameSlot()
    worker = CaptureWorker(CameraSpec("msmf", 0, "Fake"), slot, on_failure=lambda r: None, opener=lambda spec: cap)
    worker.start()
    time.sleep(0.1)
    worker.stop()
    worker.join(timeout=2)
    assert cap.released and worker.frames > 0
    assert not cap.last_buffer.any()
    assert slot.closed


def test_capture_reports_a_busy_camera():
    reasons = []
    worker = CaptureWorker(CameraSpec("msmf", 0, "Fake"), FrameSlot(), on_failure=reasons.append,
                           opener=lambda spec: None)
    worker.start()
    worker.join(timeout=2)
    assert reasons == ["camera_busy"]


def test_capture_gives_up_on_a_lost_camera(monkeypatch):
    monkeypatch.setattr("sanscontact.capture.worker.RECONNECT_WINDOW_S", 0.2)
    caps = [FakeCapture(fail_after=3)]
    reasons = []

    def opener(spec):
        return caps.pop(0) if caps else None

    worker = CaptureWorker(CameraSpec("msmf", 0, "Fake"), FrameSlot(), on_failure=reasons.append, opener=opener)
    worker.start()
    worker.join(timeout=5)
    assert reasons == ["camera_lost"]


@pytest.mark.parametrize("package", ["mediapipe", "sounddevice", "matplotlib", "certifi", "requests"])
def test_telemetry_or_network_prone_packages_are_not_installed(package):
    import importlib.util

    assert importlib.util.find_spec(package) is None, f"{package} must not be installed (docs/DECISIONS.md, D4)"


def test_opencv_build_has_no_face_recognition_module():
    import cv2

    assert not hasattr(cv2, "face")


def test_no_thread_left_behind():
    names = {t.name for t in threading.enumerate()}
    assert not names & {"capture", "inference", "control"}
