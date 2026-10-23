"""The whole control logic, end to end, with synthetic hands, a fake camera and a fake mouse."""

import queue
import threading
import time

import pytest

from sanscontact import app as app_module
from sanscontact.capture.devices import CameraDevice
from sanscontact.config import consent
from sanscontact.config.settings import Settings
from sanscontact.geometry import Rect
from sanscontact.output.monitors import Monitor
from sanscontact.output.mouse import MouseOutput, from_absolute
from sanscontact.perception.engines import EngineUnavailable
from sanscontact.perception.source import PointerSource
from sanscontact.perception.types import Observation
from sanscontact.power import PowerState, Reason
from tests.synthetic.hand_model import make_hand

DESK = Rect(0, 0, 1920, 1200)


class FakeSource(PointerSource):
    kind = "fake"

    def __init__(self):
        self.items: queue.Queue = queue.Queue()
        self.seq = 0
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def push(self, hand):
        self.seq += 1
        self.items.put(Observation(self.seq, time.perf_counter_ns(), 4 / 3, (hand,) if hand else ()))

    def latest(self, after_seq, timeout):
        try:
            return self.items.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def fps(self):
        return 30.0


class FakeDesk:
    def __init__(self):
        self.cursor = (5, 5)
        self.moves = 0

    def send(self, events):
        for e in events:
            if e.mi.dwFlags & 0x8000:
                self.cursor = from_absolute(e.mi.dx, e.mi.dy, DESK)
                self.moves += 1
        return len(events)

    def read(self):
        return self.cursor


class FakeElevation:
    blocked = False

    def blocked_at(self, x, y):
        return self.blocked


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "list_monitors", lambda: [Monitor("D1", DESK, DESK, 96, True)])
    consent.accept(tmp_path)
    settings = Settings(engagement_hold_s=0.3, disengage_after_s=0.6)
    settings.pause_timeout_s = 0.6  # below the user minimum, for a fast test
    desk = FakeDesk()
    sources = []

    def source_factory(spec, factory, on_failure):
        sources.append(FakeSource())
        return sources[-1]

    controller = app_module.Controller(
        tmp_path, settings,
        engine_provider=lambda s: (lambda: None),
        source_factory=source_factory,
        mouse=MouseOutput(send=desk.send, read_cursor=desk.read),
        elevation=FakeElevation(),
        camera_finder=lambda backend, name: CameraDevice("msmf", 0, "Fake camera", False),
    )
    thread = threading.Thread(target=controller.run, daemon=True)
    thread.start()
    yield controller, desk, sources
    controller.post("quit")
    thread.join(timeout=5)
    controller.shutdown()


def wait_for(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def stream(source, hand, seconds, fps=30):
    for _ in range(int(seconds * fps)):
        source.push(hand)
        time.sleep(1 / fps)


def engage(controller, sources):
    controller.post("toggle", "test")
    assert wait_for(lambda: controller.machine.state is PowerState.STANDBY and sources)
    stream(sources[-1], make_hand("open"), 0.6)
    assert wait_for(lambda: controller.machine.state is PowerState.ACTIVE)


def test_activation_engagement_and_mirrored_pointing(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    stream(sources[-1], make_hand("relaxed", center=(0.5, 0.45)), 0.5)
    assert desk.moves > 0
    assert abs(desk.cursor[0] - 960) < 80 and abs(desk.cursor[1] - 600) < 80
    stream(sources[-1], make_hand("relaxed", center=(0.3, 0.45)), 0.7)  # hand on the image left...
    assert desk.cursor[0] > 1300  # ...cursor on the right: the image is mirrored


def test_physical_mouse_pauses_then_camera_is_released(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    stream(sources[-1], make_hand("relaxed"), 0.2)
    desk.cursor = (desk.cursor[0] + 300, desk.cursor[1])
    sources[-1].push(make_hand("relaxed"))
    assert wait_for(lambda: controller.machine.state is PowerState.PAUSED)
    assert controller.machine.reason is Reason.PHYSICAL_MOUSE
    moves = desk.moves
    stream(sources[-1], make_hand("relaxed"), 0.2)
    assert desk.moves == moves  # the cursor is free during the pause
    assert wait_for(lambda: controller.machine.state is PowerState.OFF, timeout=2.0)
    assert controller.machine.reason is Reason.PAUSE_TIMEOUT and sources[-1].stopped


def test_hand_leaving_the_field_disengages(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    assert wait_for(lambda: controller.machine.state is PowerState.STANDBY, timeout=2.0)
    assert controller.machine.reason is Reason.HAND_LOST


def test_another_hand_cannot_take_control(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    stream(sources[-1], make_hand("relaxed", center=(0.5, 0.45)), 0.3)
    position = desk.cursor
    stream(sources[-1], make_hand("relaxed", center=(0.85, 0.2), person_hand="right"), 0.3)
    assert desk.cursor == position  # the stranger's hand moved nothing


def test_elevated_window_pauses_with_its_own_reason(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    controller.elevation.blocked = True
    stream(sources[-1], make_hand("relaxed"), 0.8)
    assert wait_for(lambda: controller.machine.state is PowerState.PAUSED)
    assert controller.machine.reason is Reason.ELEVATED_WINDOW


def test_session_lock_releases_the_camera_immediately(rig):
    controller, desk, sources = rig
    engage(controller, sources)
    controller.post("system_stop", Reason.SESSION_LOCKED)
    assert wait_for(lambda: controller.machine.state is PowerState.OFF)
    assert sources[-1].stopped


def test_toggle_twice_turns_off(rig):
    controller, desk, sources = rig
    controller.post("toggle")
    assert wait_for(lambda: controller.machine.state is PowerState.STANDBY)
    controller.post("toggle")
    assert wait_for(lambda: controller.machine.state is PowerState.OFF)
    assert sources[-1].stopped


def test_no_camera_without_consent(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module.dialogs, "ask_consent", lambda *a: False)
    started = []
    controller = app_module.Controller(
        tmp_path, Settings(), engine_provider=lambda s: (lambda: None),
        source_factory=lambda *a: started.append(1) or FakeSource(),
        mouse=MouseOutput(send=lambda e: len(e), read_cursor=lambda: (0, 0)), elevation=FakeElevation(),
        camera_finder=lambda b, n: CameraDevice("msmf", 0, "Fake camera", False),
    )
    controller._handle("toggle", None)
    assert controller.machine.state is PowerState.OFF and not started
    assert not consent.is_accepted(tmp_path)
    monkeypatch.setattr(app_module.dialogs, "ask_consent", lambda *a: True)
    controller._handle("toggle", None)
    assert controller.machine.state is PowerState.STANDBY and started == [1]
    assert consent.is_accepted(tmp_path)
    controller.shutdown()


def test_no_engine_means_no_camera(tmp_path):
    def unavailable(settings):
        raise EngineUnavailable("none")

    controller = app_module.Controller(
        tmp_path, Settings(), engine_provider=unavailable, source_factory=lambda *a: pytest.fail("camera started"),
        mouse=MouseOutput(send=lambda e: len(e), read_cursor=lambda: (0, 0)), elevation=FakeElevation(),
        camera_finder=lambda b, n: CameraDevice("msmf", 0, "Fake camera", False),
    )
    controller._handle("toggle", None)
    assert controller.machine.state is PowerState.OFF
