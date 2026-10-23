"""Application wiring: controller thread, control loop, native host.

Threads:
- native     Win32 message loop (shortcut, notification icon, session, power)
- controller the only one that changes the power state and starts/stops the camera
- capture    reads the webcam (newest frame only)
- inference  turns the newest frame into landmarks
- control    interprets landmarks and moves the cursor
"""

from __future__ import annotations

import argparse
import ctypes
import json
import queue
import sys
import threading
import time
from pathlib import Path

from sanscontact import _win32 as w
from sanscontact.bench.metrics import PipelineMetrics, ProcessUsage
from sanscontact.branding import APP_NAME, VERSION
from sanscontact.capture.camera import CameraSpec
from sanscontact.capture.devices import find_camera, list_cameras
from sanscontact.config import consent
from sanscontact.config import settings as settings_store
from sanscontact.config.paths import data_dir
from sanscontact.config.settings import Settings
from sanscontact.config.storage import delete_all_data
from sanscontact.interpretation.dwell import DwellClicker
from sanscontact.interpretation.engagement import EngagementDetector
from sanscontact.interpretation.gestures import Action, GestureConfig, GestureMachine, MouseAction, State
from sanscontact.interpretation.hand_pose import features
from sanscontact.interpretation.lock import HandLock, preferred
from sanscontact.interpretation.one_euro import OneEuroFilter2D
from sanscontact.interpretation.pointer import ActiveZone, Pointer, reference_point
from sanscontact.output.monitors import enable_per_monitor_dpi_awareness, list_monitors, virtual_desktop
from sanscontact.output.mouse import MouseOutput
from sanscontact.output.uipi import ElevationProbe
from sanscontact.perception.engines import EngineUnavailable, hand_engine_factory
from sanscontact.perception.models import ModelError
from sanscontact.perception.source import EngineFactory, PointerSource
from sanscontact.perception.webcam import WebcamHandSource
from sanscontact.power import PAUSE_REASONS, PowerMachine, PowerState, Reason, Transition
from sanscontact.privacy import network_guard, safe_log
from sanscontact.privacy.endpoints import EndpointWatch
from sanscontact.ui import dialogs
from sanscontact.ui.native import NativeHost, TrayView
from sanscontact.ui.strings import hotkey_label, t

TICK_S = 0.25
METRICS_LOG_S = 30.0
LOW_FPS = 15.0
UIPI_CHECK_S = 0.5

# Reasons worth a notification balloon, with the message key to show.
_NOTIFY = {
    Reason.CAMERA_BUSY: "msg.camera_busy",
    Reason.CAMERA_LOST: "msg.camera_lost",
    Reason.ELEVATED_WINDOW: "msg.elevated_window",
}


def gesture_config(settings: Settings, double_click_s: float) -> GestureConfig:
    return GestureConfig(
        press=settings.pinch_press,
        release=settings.pinch_release,
        min_press_s=settings.min_press_ms / 1000,
        drag_start=settings.drag_start,
        double_click_s=double_click_s,
        scroll_dead_zone=settings.scroll_dead_zone,
        scroll_speed=settings.scroll_speed,
        scroll_smooth=settings.scroll_mode == "smooth",
        scroll_invert=settings.scroll_invert,
    )


class ControlWorker(threading.Thread):
    """Interprets the newest observation and drives the cursor while ACTIVE."""

    def __init__(self, controller: Controller, source: PointerSource, settings: Settings) -> None:
        super().__init__(name="control", daemon=True)
        self.c = controller
        self.source = source
        self.s = settings
        self._stop = threading.Event()
        self.lock = HandLock()
        self.engagement = EngagementDetector(hold_s=settings.engagement_hold_s)
        self.pointer = Pointer(
            ActiveZone.from_list(settings.active_zone),
            OneEuroFilter2D(settings.one_euro_min_cutoff, settings.one_euro_beta, settings.one_euro_d_cutoff),
            mode=settings.pointer_mode, relative_gain=settings.relative_gain,
            relative_accel=settings.relative_accel, rollback_s=settings.click_rollback_ms / 1000,
        )
        self.gestures = GestureMachine(gesture_config(settings, controller.double_click_s))
        self.dwell = DwellClicker(settings.dwell_ms / 1000, settings.dwell_radius_px)
        self._event_sent = False
        self._last_uipi_check = 0.0

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        last_seq = 0
        previous = None
        while not self._stop.is_set():
            observation = self.source.latest(last_seq, timeout=0.1)
            now = time.monotonic()
            state = self.c.machine.state
            if state is not previous:
                self._on_state(state)
                previous = state
            if observation is None:
                self._check_lost(state, now)
                continue
            last_seq = observation.seq
            self._step(state, observation, now)

    def _on_state(self, state: PowerState) -> None:
        self._event_sent = False
        self.engagement.reset()
        self.gestures.reset()  # buttons are released by the controller when leaving ACTIVE
        self.dwell.reset()
        if state is PowerState.ACTIVE:
            self.pointer.reset(cursor=self.c.mouse.current_position())
        else:
            self.lock.release()
        self.c.gesture_state = self.gestures.state

    def _check_lost(self, state: PowerState, now: float) -> None:
        lost = self.lock.missing_for(now) > self.s.disengage_after_s
        if state is PowerState.ACTIVE and not self._event_sent and lost:
            self._event_sent = True
            self.c.post("hand_lost")

    def _step(self, state: PowerState, observation, now: float) -> None:
        t0 = time.perf_counter_ns()
        candidates = [(hand, features(hand, observation.aspect)) for hand in observation.hands]
        self.c.metrics.count_frame(bool(candidates))
        if state in (PowerState.STANDBY, PowerState.PAUSED):
            candidate = preferred(candidates, self.s.hand)
            if self.engagement.update(candidate[1] if candidate else None, now, observation.aspect) and candidate:
                self.lock.engage(candidate, now)
                self.c.metrics.engagements += 1
                self.c.post("engaged")
            return
        if state is not PowerState.ACTIVE or self._event_sent:
            return
        selected = self.lock.select(candidates, now, observation.aspect)
        del candidates  # any other hand is dropped here
        if selected is None:
            frame = self.gestures.hand_missing(now)
            self.c.gesture_state = frame.state
            if frame.actions:
                with self.c.output_lock:
                    if self.c.machine.state is PowerState.ACTIVE:
                        self._execute(frame.actions)
            self._check_lost(state, now)
            return
        hand, pose = selected
        frame = self.gestures.update(pose, now, observation.aspect)
        self.c.gesture_state = frame.state
        self.c.metrics.count_gestures(frame.events)
        t1 = time.perf_counter_ns()
        x, y = reference_point(hand, pose, self.s.pointer_landmark)
        px, py = self.pointer.update(x, y, observation.t_capture_ns / 1e9, self.c.desktop, self.c.screens,
                                     freeze=frame.freeze, rollback=frame.rollback)
        actions = frame.actions
        dwell_allowed = self.s.dwell_click and frame.state is State.POINT and not frame.freeze
        if self.dwell.update((px, py), now, dwell_allowed):
            actions += (MouseAction(Action.LEFT_DOWN), MouseAction(Action.LEFT_UP))
            self.c.metrics.count_gestures(("dwell_click",))
        t2 = time.perf_counter_ns()
        with self.c.output_lock:
            if self.c.machine.state is not PowerState.ACTIVE:
                return
            moved = self.c.mouse.moved_externally(self.s.physical_mouse_tolerance_px)
            reason = None
            if moved is None:
                reason = Reason.SECURE_DESKTOP
            elif moved or now - self._last_uipi_check >= UIPI_CHECK_S:
                self._last_uipi_check = now
                if self.c.elevation.blocked_at(px, py):
                    reason = Reason.ELEVATED_WINDOW
                elif moved:
                    reason = Reason.PHYSICAL_MOUSE
            if reason is not None:
                self._event_sent = True
                self.c.post("pointer_taken", reason)
                return
            if self.c.mouse.last_target != (px, py):
                self.c.mouse.move_to(px, py)
            self._execute(actions)
        t3 = time.perf_counter_ns()
        m = self.c.metrics
        for stage, value in observation.timings_ns.items():
            m.add_ms(stage, value / 1e6)
        m.add_ms("interpret", (t1 - t0) / 1e6)
        m.add_ms("smooth", (t2 - t1) / 1e6)
        m.add_ms("inject", (t3 - t2) / 1e6)
        m.add_ms("total", (time.perf_counter_ns() - observation.t_capture_ns) / 1e6)

    def _execute(self, actions) -> None:
        """Send gesture actions. Called with the output lock held and the state ACTIVE."""
        mouse = self.c.mouse
        for item in actions:
            if item.action is Action.LEFT_DOWN:
                mouse.press("left")
            elif item.action is Action.LEFT_UP:
                mouse.release("left")
            elif item.action is Action.RIGHT_DOWN:
                mouse.press("right")
            elif item.action is Action.RIGHT_UP:
                mouse.release("right")
            elif item.action is Action.WHEEL:
                mouse.wheel(item.amount)
            elif item.action is Action.HWHEEL:
                mouse.wheel(item.amount, horizontal=True)


def _webcam_source(spec: CameraSpec, factory: EngineFactory, on_failure) -> PointerSource:
    return WebcamHandSource(spec, factory, on_failure=on_failure)


class Controller:
    def __init__(self, directory: Path, settings: Settings, engine_provider=hand_engine_factory,
                 source_factory=_webcam_source, mouse: MouseOutput | None = None,
                 elevation: ElevationProbe | None = None, camera_finder=find_camera) -> None:
        self.dir = directory
        self.settings = settings
        self._engine_provider = engine_provider
        self._source_factory = source_factory
        self._find_camera = camera_finder
        self.commands: queue.Queue[tuple[str, object]] = queue.Queue()
        self.machine = PowerMachine(settings.pause_timeout_s)
        self.output_lock = threading.Lock()
        self.mouse = mouse or MouseOutput()
        self.elevation = elevation or ElevationProbe()
        self.metrics = PipelineMetrics()
        self.usage = ProcessUsage()
        self.endpoints = EndpointWatch()
        self.native: NativeHost | None = None
        self.source: PointerSource | None = None
        self.control: ControlWorker | None = None
        self.camera_name: str | None = None
        self.detail = t("reason.startup")
        self.hotkey_ok: bool | None = None
        # Windows' own double-click time (read, never changed).
        self.double_click_s = (w.GetDoubleClickTime() or 500) / 1000
        self.gesture_state = State.POINT
        self._running = True
        self._dialog_open = False
        self._low_fps_warned = False
        self.screens = []
        self.desktop = None
        self._refresh_screens()
        self.log = safe_log.get_logger()

    # ---- commands -------------------------------------------------------------------------
    def post(self, name: str, payload: object = None) -> None:
        self.commands.put((name, payload))

    def run(self, stop_after_s: float | None = None) -> None:
        started = time.monotonic()
        next_metrics = started + METRICS_LOG_S
        self._publish()
        while self._running:
            try:
                name, payload = self.commands.get(timeout=TICK_S)
            except queue.Empty:
                name, payload = None, None
            if name is not None:
                self._handle(name, payload)
            now = time.monotonic()
            self._apply(self._locked(lambda now=now: self.machine.tick(now)))
            before = self.network_count()
            self.endpoints.poll()
            if self.network_count() != before:
                self.log.warning("network activity observed: %d", self.network_count())
                self._publish()
            if self.machine.state is PowerState.PAUSED:
                self._publish()
            if now >= next_metrics:
                next_metrics = now + METRICS_LOG_S
                self._log_metrics()
            if stop_after_s is not None and now - started >= stop_after_s:
                self._running = False

    def _handle(self, name: str, payload: object) -> None:
        if name == "toggle":
            if self._dialog_open:
                return
            if self.machine.state is PowerState.OFF:
                self._activate()
            else:
                self._apply(self._locked(lambda: self.machine.deactivate(Reason.USER)))
        elif name == "engaged":
            self._apply(self._locked(self.machine.engaged))
        elif name == "hand_lost":
            self._apply(self._locked(self.machine.hand_lost))
        elif name == "pointer_taken" and payload in PAUSE_REASONS:
            now = time.monotonic()
            self._apply(self._locked(lambda: self.machine.pointer_taken(payload, now)))
        elif name == "camera_failed":
            reason = Reason(payload) if payload in Reason._value2member_map_ else Reason.ERROR
            self._apply(self._locked(lambda: self.machine.deactivate(reason)))
        elif name == "system_stop" and isinstance(payload, Reason):
            self._apply(self._locked(lambda: self.machine.deactivate(payload)))
        elif name == "display_off":
            if self.settings.release_on_display_off:
                self._apply(self._locked(lambda: self.machine.deactivate(Reason.DISPLAY_OFF)))
        elif name == "display_changed":
            self._refresh_screens()
        elif name == "select_camera" and isinstance(payload, str):
            self._select_camera(payload)
        elif name == "delete_data":
            self._delete_data()
        elif name == "hotkey_status":
            self.hotkey_ok = bool(payload)
            if not payload:
                self._notify(t("msg.hotkey_failed", hotkey=hotkey_label(self.settings.hotkey)), warning=True)
        elif name == "crash":
            self._apply(self._locked(lambda: self.machine.deactivate(Reason.ERROR)))
        elif name == "quit":
            self._running = False

    def _locked(self, change) -> Transition | None:
        with self.output_lock:
            return change()

    # ---- activation -----------------------------------------------------------------------
    def _activate(self) -> None:
        camera = self._find_camera(self.settings.camera_backend, self.settings.camera_name)
        if camera is None:
            several = len([c for c in list_cameras(self.settings.camera_backend) if c.eligible]) > 1
            self.detail = t("reason.no_camera")
            self._notify(t("msg.choose_camera" if several else "msg.no_camera"), warning=True)
            self._publish()
            return
        try:
            factory = self._engine_provider(self.settings)
        except EngineUnavailable:
            self._notify(t("msg.engine_missing"), warning=True)
            return
        except ModelError:
            self._notify(t("msg.model_missing"), warning=True)
            return
        if not consent.is_accepted(self.dir):
            self._dialog_open = True
            try:
                accepted = dialogs.ask_consent(camera.name, self.settings.frame_width, self.settings.frame_height,
                                               self.settings.hotkey)
            finally:
                self._dialog_open = False
                self._drain_toggles()
            if not accepted:
                self.detail = t("reason.consent_declined")
                self._publish()
                return
            consent.accept(self.dir)
        self.camera_name = camera.name
        spec = CameraSpec(camera.backend, camera.index, camera.name, self.settings.frame_width,
                          self.settings.frame_height, self.settings.frame_rate)
        transition = self._locked(self.machine.activate)
        if transition is not None:
            self._start_pipeline(spec, factory)
            self._apply(transition)

    def _drain_toggles(self) -> None:
        kept = []
        while True:
            try:
                item = self.commands.get_nowait()
            except queue.Empty:
                break
            if item[0] != "toggle":
                kept.append(item)
        for item in kept:
            self.commands.put(item)

    def _start_pipeline(self, spec: CameraSpec, factory: EngineFactory) -> None:
        self._refresh_screens()
        self.metrics.reset()
        self._low_fps_warned = False
        self.source = self._source_factory(spec, factory, lambda r: self.post("camera_failed", r))
        self.source.start()
        self.control = ControlWorker(self, self.source, self.settings)
        self.control.start()

    def _stop_pipeline(self) -> None:
        if self.control is not None:
            self.control.stop()
        if self.source is not None:
            self.source.stop()  # releases the camera now
        if self.control is not None:
            self.control.join(timeout=5.0)
        self.control = None
        self.source = None

    def _apply(self, transition: Transition | None) -> None:
        if transition is None:
            return
        if transition.left_active:
            with self.output_lock:
                self.mouse.release_all()
                self.mouse.forget_position()
        if transition.state is PowerState.ACTIVE:
            with self.output_lock:
                self.mouse.forget_position()
        if transition.camera_stopped:
            self._stop_pipeline()
            with self.output_lock:
                self.mouse.release_all()
        self.detail = t(f"reason.{transition.reason.value}") or t(f"hint.{transition.state.value}")
        self.log.info("state %s -> %s (%s)", transition.previous.value, transition.state.value,
                      transition.reason.value)
        if transition.reason in _NOTIFY:
            self._notify(t(_NOTIFY[transition.reason]), warning=True)
        self._publish()

    # ---- other commands -------------------------------------------------------------------
    def _select_camera(self, name: str) -> None:
        self.settings.camera_name = name
        settings_store.save(self.dir, self.settings)
        if self.machine.camera_on:
            self._apply(self._locked(lambda: self.machine.deactivate(Reason.USER)))
        self._publish()

    def _delete_data(self) -> None:
        self._dialog_open = True
        try:
            confirmed = dialogs.confirm_delete()
        finally:
            self._dialog_open = False
            self._drain_toggles()
        if not confirmed:
            return
        self._apply(self._locked(lambda: self.machine.deactivate(Reason.DATA_DELETED)))
        safe_log.close()
        deleted = delete_all_data(self.dir)
        self.settings = Settings()
        self.detail = t("reason.data_deleted")
        self._notify(t("delete.done" if deleted else "delete.nothing"))
        self._publish()

    def shutdown(self) -> None:
        self._apply(self._locked(lambda: self.machine.deactivate(Reason.EXIT)))
        with self.output_lock:
            self.mouse.release_all()

    # ---- views ----------------------------------------------------------------------------
    def network_count(self) -> int:
        return network_guard.attempts() + self.endpoints.count

    def _refresh_screens(self) -> None:
        monitors = list_monitors()
        self.screens = [m.rect for m in monitors]
        self.desktop = virtual_desktop(monitors)
        self.mouse.set_desktop(self.desktop)

    def _notify(self, text: str, warning: bool = False) -> None:
        self.log.info("notice: %s", "warning" if warning else "info")
        if self.native is not None:
            self.native.notify(text, warning)

    def _publish(self) -> None:
        if self.native is None:
            return
        state = self.machine.state
        detail = self.detail
        remaining = self.machine.pause_remaining(time.monotonic())
        if remaining is not None:
            detail = f"{t('reason.' + self.machine.reason.value)} {t('hint.paused', seconds=max(0, int(remaining)))}"
        try:
            cameras = list_cameras(self.settings.camera_backend)
        except OSError:
            cameras = []
        self.native.update(TrayView(
            state=state,
            tooltip=t("tray.tooltip", state=t(f"state.{state.value}"), detail=detail, net=self.network_count()),
            cameras=tuple(c.name for c in cameras if c.eligible),
            selected_camera=self.settings.camera_name or self.camera_name,
            ir_excluded=any(c.infrared for c in cameras),
            hotkey_label=hotkey_label(self.settings.hotkey),
        ))

    def _log_metrics(self) -> None:
        source = self.source
        fps = source.fps if source is not None else 0.0
        mean, p95, _ = self.metrics.stages["total"].snapshot()
        detect_mean, _, _ = self.metrics.stages["detect"].snapshot()
        gestures = " ".join(f"{k}={v}" for k, v in sorted(self.metrics.gestures.items())) or "none"
        self.log.info(
            "metrics state=%s fps=%.1f latency_ms=%.1f/p95 %.1f detect_ms=%.1f hands=%.0f%% engagements=%d "
            "gestures[%s] cpu=%.0f%% mem_mb=%.0f net=%d",
            self.machine.state.value, fps, mean, p95, detect_mean, 100 * self.metrics.hand_ratio(),
            self.metrics.engagements, gestures, self.usage.cpu_percent(), self.usage.memory_mb(),
            self.network_count(),
        )
        if source is not None and self.machine.camera_on and 0 < fps < LOW_FPS and not self._low_fps_warned:
            self._low_fps_warned = True
            self._notify(t("msg.low_fps", fps=round(fps)), warning=True)


class SingleInstance:
    def __init__(self) -> None:
        self.handle = w.CreateMutexW(None, False, f"Local\\{APP_NAME}.SingleInstance")
        self.already_running = ctypes.get_last_error() == w.ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self.handle:
            w.CloseHandle(self.handle)
            self.handle = None


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME.lower(), description=f"{APP_NAME} {VERSION}")
    parser.add_argument("--list-cameras", action="store_true", help="list cameras by name and exit")
    parser.add_argument("--probe-camera", action="store_true",
                        help="compare MSMF and DirectShow (opening time, real fps) and exit")
    parser.add_argument("--selftest", type=float, metavar="SECONDS",
                        help="start without the camera, check shortcut and icon, quit after SECONDS")
    parser.add_argument("--verbose", action="store_true", help="also print the technical log to the console")
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = _parse(argv)
    enable_per_monitor_dpi_awareness()
    directory = data_dir()
    settings = settings_store.load(directory)

    if args.list_cameras:
        for backend in ("msmf", "dshow"):
            for camera in list_cameras(backend):
                status = "exclue (infrarouge)" if camera.infrared else "utilisable"
                print(f"{backend:5s} #{camera.index}  {camera.name}  [{status}]")
        return 0
    if args.probe_camera:
        from sanscontact.capture.probe import best, probe

        results = [probe(b, settings.camera_name, settings.frame_width, settings.frame_height, settings.frame_rate)
                   for b in ("msmf", "dshow")]
        winner = best(results)
        print(json.dumps({"results": [r.__dict__ for r in results], "best": winner.backend if winner else None},
                         indent=2, ensure_ascii=False))
        return 0

    safe_log.setup(directory, to_file=settings.metrics_log and args.selftest is None, to_console=args.verbose)
    log = safe_log.get_logger()
    log.info("%s %s starting (python %s)", APP_NAME, VERSION, sys.version.split()[0])
    instance = SingleInstance()
    if instance.already_running:
        dialogs.info(t("msg.already_running"))
        instance.close()
        return 1
    controller = Controller(directory, settings)
    native = NativeHost(controller.post, settings.hotkey)
    controller.native = native
    safe_log.install_excepthooks(lambda exc: controller.post("crash"))
    native.start()
    native.wait_ready()
    try:
        controller.run(stop_after_s=args.selftest)
    finally:
        controller.shutdown()
        native.stop()
        instance.close()
        if args.selftest is not None:
            print(json.dumps({
                "hotkey_registered": native.hotkey_ok,
                "tray_icon": native.tray_shown,
                "state": controller.machine.state.value,
                "network_attempts": network_guard.attempts(),
                "network_endpoints": controller.endpoints.count,
            }))
        log.info("%s stopped", APP_NAME)
        safe_log.close()
    return 0
