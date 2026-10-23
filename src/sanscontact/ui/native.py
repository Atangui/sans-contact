"""Native Windows thread: one hidden window and one message loop for

- the global shortcut (RegisterHotKey: never a keyboard hook),
- the notification-area icon (left click toggles, right click opens the menu),
- session lock / user switch (WTSRegisterSessionNotification),
- sleep and display-off notifications,
- the small "camera on" indicator, always on top and click-through.

It never decides anything: it forwards events to the controller with ``post``
and shows the state it is given with ``update``.
"""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field

from sanscontact import _win32 as w
from sanscontact.branding import APP_NAME
from sanscontact.power import PowerState, Reason
from sanscontact.privacy.safe_log import get_logger
from sanscontact.ui import icons
from sanscontact.ui.strings import t

WM_TRAY = w.WM_APP + 1
WM_APP_UPDATE = w.WM_APP + 2
WM_APP_NOTIFY = w.WM_APP + 3
HOTKEY_ID = 1
TRAY_ID = 1

CMD_TOGGLE = 1
CMD_DELETE = 2
CMD_QUIT = 3
CMD_CAMERA_BASE = 100

INDICATOR_SIZE_DIP = 28
INDICATOR_MARGIN_DIP = 12

_KEYS = {"space": 0x20, "enter": 0x0D, "pause": 0x13, "home": 0x24, "end": 0x23}
_MODIFIERS = {"ctrl": w.MOD_CONTROL, "control": w.MOD_CONTROL, "alt": w.MOD_ALT, "shift": w.MOD_SHIFT,
              "win": w.MOD_WIN}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+Space' -> (MOD_CONTROL | MOD_ALT, VK_SPACE)."""
    modifiers = 0
    key = None
    for part in (p.strip().lower() for p in text.split("+")):
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif part in _KEYS:
            key = _KEYS[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1
        else:
            raise ValueError(f"unknown key in shortcut: {part!r}")
    if key is None or modifiers == 0:
        raise ValueError("a shortcut needs at least one modifier and one key")
    return modifiers, key


@dataclass(frozen=True)
class TrayView:
    state: PowerState = PowerState.OFF
    tooltip: str = APP_NAME
    cameras: tuple[str, ...] = ()
    selected_camera: str | None = None
    ir_excluded: bool = False
    hotkey_label: str = ""
    extra: dict = field(default_factory=dict)


class NativeHost(threading.Thread):
    def __init__(self, post: Callable[[str, object], None], hotkey: str) -> None:
        super().__init__(name="native", daemon=True)
        self._post = post
        self._hotkey = hotkey
        self._lock = threading.Lock()
        self._view = TrayView()
        self._notes: list[tuple[str, bool]] = []
        self._ready = threading.Event()
        self.hwnd = None
        self.hotkey_ok: bool | None = None
        self.tray_ok = False
        self.tray_shown = False
        self._icons: dict[PowerState, int] = {}
        self._shown_state: PowerState | None = None
        self._indicator = None
        self._indicator_state: PowerState | None = None
        self._power_notify = None
        self._wndproc = w.WNDPROC(self._dispatch)
        self._indicator_proc = w.WNDPROC(self._indicator_dispatch)
        self._taskbar_created = 0

    # ---- called from other threads ------------------------------------------------------
    def wait_ready(self, timeout: float = 10.0) -> bool:
        return self._ready.wait(timeout)

    def update(self, view: TrayView) -> None:
        with self._lock:
            self._view = view
        if self.hwnd:
            w.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def notify(self, text: str, warning: bool = False) -> None:
        with self._lock:
            self._notes.append((text, warning))
        if self.hwnd:
            w.PostMessageW(self.hwnd, WM_APP_NOTIFY, 0, 0)

    def stop(self) -> None:
        if self.hwnd:
            w.PostMessageW(self.hwnd, w.WM_CLOSE, 0, 0)
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=5.0)

    # ---- thread body ---------------------------------------------------------------------
    def run(self) -> None:
        instance = w.GetModuleHandleW(None)
        main_class = f"{APP_NAME}.Host"
        indicator_class = f"{APP_NAME}.Indicator"
        try:
            self._register_class(main_class, self._wndproc, instance)
            self._register_class(indicator_class, self._indicator_proc, instance)
            self.hwnd = w.CreateWindowExW(w.WS_EX_TOOLWINDOW, main_class, APP_NAME, w.WS_POPUP,
                                          0, 0, 0, 0, None, None, instance, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._taskbar_created = w.RegisterWindowMessageW("TaskbarCreated")
            self._register_hotkey()
            w.WTSRegisterSessionNotification(self.hwnd, w.NOTIFY_FOR_THIS_SESSION)
            self._power_notify = w.RegisterPowerSettingNotification(
                self.hwnd, ctypes.byref(w.GUID_CONSOLE_DISPLAY_STATE), w.DEVICE_NOTIFY_WINDOW_HANDLE)
            self._load_icons()
            self.tray_ok = self._tray(w.NIM_ADD)
            self._indicator = w.CreateWindowExW(
                w.WS_EX_LAYERED | w.WS_EX_TRANSPARENT | w.WS_EX_TOPMOST | w.WS_EX_TOOLWINDOW | w.WS_EX_NOACTIVATE,
                indicator_class, APP_NAME, w.WS_POPUP, 0, 0, 0, 0, None, None, instance, None)
            self._apply_view()
            self._ready.set()
            message = wintypes.MSG()
            while w.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                w.TranslateMessage(ctypes.byref(message))
                w.DispatchMessageW(ctypes.byref(message))
        finally:
            self._ready.set()
            self._cleanup(instance, main_class, indicator_class)

    def _register_class(self, name: str, proc, instance) -> None:
        cls = w.WNDCLASSEXW()
        cls.cbSize = ctypes.sizeof(w.WNDCLASSEXW)
        cls.lpfnWndProc = proc
        cls.hInstance = instance
        cls.lpszClassName = name
        if not w.RegisterClassExW(ctypes.byref(cls)):
            raise ctypes.WinError(ctypes.get_last_error())

    def _register_hotkey(self) -> None:
        try:
            modifiers, key = parse_hotkey(self._hotkey)
        except ValueError:
            self.hotkey_ok = False
        else:
            self.hotkey_ok = bool(w.RegisterHotKey(self.hwnd, HOTKEY_ID, modifiers | w.MOD_NOREPEAT, key))
        self._post("hotkey_status", self.hotkey_ok)

    def _release_window_resources(self) -> None:
        """Called while the main window still exists (WM_DESTROY, or on a failed start)."""
        if self.tray_ok:
            self._tray(w.NIM_DELETE)
            self.tray_ok = False
        w.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        w.WTSUnRegisterSessionNotification(self.hwnd)
        if self._power_notify:
            w.UnregisterPowerSettingNotification(self._power_notify)
            self._power_notify = None
        if self._indicator:
            w.DestroyWindow(self._indicator)
            self._indicator = None

    def _cleanup(self, instance, main_class: str, indicator_class: str) -> None:
        if self.hwnd:  # the loop ended without WM_DESTROY (start-up failure)
            self._release_window_resources()
            w.DestroyWindow(self.hwnd)
        self.hwnd = None
        for icon in self._icons.values():
            w.DestroyIcon(icon)
        self._icons.clear()
        w.UnregisterClassW(main_class, instance)
        w.UnregisterClassW(indicator_class, instance)

    # ---- icons, tooltip, indicator -------------------------------------------------------
    def _load_icons(self) -> None:
        dpi = w.GetDpiForSystem() or 96
        size = w.GetSystemMetricsForDpi(w.SM_CXSMICON, dpi) or 16
        for state in PowerState:
            self._icons[state] = icons.make_hicon(state, size)

    def _tray(self, action: int, info: tuple[str, bool] | None = None) -> bool:
        with self._lock:
            view = self._view
        data = w.NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(w.NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = TRAY_ID
        if action == w.NIM_DELETE:
            return bool(w.Shell_NotifyIconW(action, ctypes.byref(data)))
        data.uFlags = w.NIF_MESSAGE | w.NIF_ICON | w.NIF_TIP | w.NIF_SHOWTIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._icons.get(view.state)
        data.szTip = view.tooltip[:127]
        if info is not None:
            data.uFlags |= w.NIF_INFO
            data.szInfoTitle = APP_NAME
            data.szInfo = info[0][:255]
            data.dwInfoFlags = (w.NIIF_WARNING if info[1] else w.NIIF_INFO) | w.NIIF_RESPECT_QUIET_TIME
        ok = bool(w.Shell_NotifyIconW(action, ctypes.byref(data)))
        if ok and action == w.NIM_ADD:
            self.tray_shown = True
            data.uVersion = w.NOTIFYICON_VERSION_4
            w.Shell_NotifyIconW(w.NIM_SETVERSION, ctypes.byref(data))
        return ok

    def _apply_view(self) -> None:
        with self._lock:
            state = self._view.state
        if self.tray_ok:
            self._tray(w.NIM_MODIFY)
        else:
            self.tray_ok = self._tray(w.NIM_ADD)
        self._shown_state = state
        self._show_indicator(state)

    def _show_indicator(self, state: PowerState) -> None:
        if not self._indicator:
            return
        if state is PowerState.OFF:
            w.ShowWindow(self._indicator, w.SW_HIDE)
            self._indicator_state = state
            return
        if state is not self._indicator_state:
            self._paint_indicator(state)
        w.SetWindowPos(self._indicator, w.HWND_TOPMOST, 0, 0, 0, 0,
                       w.SWP_NOMOVE | w.SWP_NOSIZE | w.SWP_NOACTIVATE | w.SWP_SHOWWINDOW)
        self._indicator_state = state

    def _paint_indicator(self, state: PowerState) -> None:
        from sanscontact.output.monitors import list_monitors, primary

        main = primary(list_monitors())
        dpi = main.dpi if main else 96
        size = round(INDICATOR_SIZE_DIP * dpi / 96)
        margin = round(INDICATOR_MARGIN_DIP * dpi / 96)
        if main:
            x, y = main.work.right - size - margin, main.work.bottom - size - margin
        else:
            x, y = margin, margin
        bitmap = icons.make_layered_bitmap(state, size)
        screen_dc = w.GetDC(None)
        memory_dc = w.CreateCompatibleDC(screen_dc)
        previous = w.SelectObject(memory_dc, bitmap)
        try:
            blend = w.BLENDFUNCTION(w.AC_SRC_OVER, 0, 255, w.AC_SRC_ALPHA)
            w.UpdateLayeredWindow(self._indicator, screen_dc, ctypes.byref(wintypes.POINT(x, y)),
                                  ctypes.byref(wintypes.SIZE(size, size)), memory_dc,
                                  ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), w.ULW_ALPHA)
        finally:
            w.SelectObject(memory_dc, previous)
            w.DeleteDC(memory_dc)
            w.ReleaseDC(None, screen_dc)
            w.DeleteObject(bitmap)

    def _show_notes(self) -> None:
        with self._lock:
            notes, self._notes = self._notes, []
        for note in notes[-3:]:
            self._tray(w.NIM_MODIFY, note)

    # ---- context menu --------------------------------------------------------------------
    def _show_menu(self, x: int, y: int) -> None:
        with self._lock:
            view = self._view
        menu = w.CreatePopupMenu()
        cameras_menu = w.CreatePopupMenu()
        try:
            w.AppendMenuW(menu, w.MF_STRING | w.MF_GRAYED, 0, f"{APP_NAME} — {t('state.' + view.state.value)}")
            label = t("menu.activate" if view.state is PowerState.OFF else "menu.deactivate",
                      hotkey=view.hotkey_label)
            w.AppendMenuW(menu, w.MF_STRING, CMD_TOGGLE, label)
            if view.cameras:
                for i, name in enumerate(view.cameras):
                    flags = w.MF_STRING | (w.MF_CHECKED if name == view.selected_camera else 0)
                    w.AppendMenuW(cameras_menu, flags, CMD_CAMERA_BASE + i, name)
            else:
                w.AppendMenuW(cameras_menu, w.MF_STRING | w.MF_GRAYED, 0, t("menu.camera_none"))
            if view.ir_excluded:
                w.AppendMenuW(cameras_menu, w.MF_SEPARATOR, 0, None)
                w.AppendMenuW(cameras_menu, w.MF_STRING | w.MF_GRAYED, 0, t("menu.camera_ir_excluded"))
            w.AppendMenuW(menu, w.MF_POPUP, cameras_menu, t("menu.camera"))
            w.AppendMenuW(menu, w.MF_SEPARATOR, 0, None)
            w.AppendMenuW(menu, w.MF_STRING, CMD_DELETE, t("menu.delete_data"))
            w.AppendMenuW(menu, w.MF_STRING, CMD_QUIT, t("menu.quit"))
            w.SetForegroundWindow(self.hwnd)
            command = w.TrackPopupMenuEx(menu, w.TPM_RETURNCMD | w.TPM_RIGHTBUTTON | w.TPM_NONOTIFY,
                                         x, y, self.hwnd, None)
            w.PostMessageW(self.hwnd, w.WM_NULL, 0, 0)
        finally:
            w.DestroyMenu(menu)  # also destroys the attached sub-menu
        if command == CMD_TOGGLE:
            self._post("toggle", "tray")
        elif command == CMD_DELETE:
            self._post("delete_data", None)
        elif command == CMD_QUIT:
            self._post("quit", None)
        elif command >= CMD_CAMERA_BASE and command - CMD_CAMERA_BASE < len(view.cameras):
            self._post("select_camera", view.cameras[command - CMD_CAMERA_BASE])

    # ---- window procedures ---------------------------------------------------------------
    def _dispatch(self, hwnd, message, wparam, lparam):
        try:
            handled = self._handle(hwnd, message, wparam, lparam)
            if handled is not None:
                return handled
        except Exception as exc:  # noqa: BLE001 - never let an error cross into Windows
            get_logger().error("native message %#x failed: %s", message, type(exc).__name__)
        return w.DefWindowProcW(hwnd, message, wparam, lparam)

    def _handle(self, hwnd, message, wparam, lparam):
        if message == w.WM_HOTKEY and wparam == HOTKEY_ID:
            self._post("toggle", "hotkey")
            return 0
        if message == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (w.NIN_SELECT, w.NIN_KEYSELECT):
                self._post("toggle", "tray")
            elif event == w.WM_CONTEXTMENU:
                x = ctypes.c_short(wparam & 0xFFFF).value
                y = ctypes.c_short((wparam >> 16) & 0xFFFF).value
                self._show_menu(x, y)
            return 0
        if message == w.WM_WTSSESSION_CHANGE:
            if wparam == w.WTS_SESSION_LOCK:
                self._post("system_stop", Reason.SESSION_LOCKED)
            elif wparam in (w.WTS_CONSOLE_DISCONNECT, w.WTS_REMOTE_DISCONNECT, w.WTS_SESSION_LOGOFF):
                self._post("system_stop", Reason.SESSION_CHANGED)
            return 0
        if message == w.WM_POWERBROADCAST:
            if wparam == w.PBT_APMSUSPEND:
                self._post("system_stop", Reason.SUSPEND)
            elif wparam == w.PBT_POWERSETTINGCHANGE and lparam:
                setting = w.POWERBROADCAST_SETTING.from_address(lparam)
                if bytes(setting.PowerSetting) == bytes(w.GUID_CONSOLE_DISPLAY_STATE) and setting.Data[0] == 0:
                    self._post("display_off", None)
            return 1
        if message == w.WM_DISPLAYCHANGE:
            self._indicator_state = None
            self._post("display_changed", None)
            self._show_indicator(self._shown_state or PowerState.OFF)
            return 0
        if message == WM_APP_UPDATE:
            self._apply_view()
            return 0
        if message == WM_APP_NOTIFY:
            self._show_notes()
            return 0
        if self._taskbar_created and message == self._taskbar_created:
            self.tray_ok = self._tray(w.NIM_ADD)
            return 0
        if message == w.WM_CLOSE:
            w.DestroyWindow(hwnd)
            return 0
        if message == w.WM_DESTROY:
            self._release_window_resources()
            self.hwnd = None
            w.PostQuitMessage(0)
            return 0
        return None

    def _indicator_dispatch(self, hwnd, message, wparam, lparam):
        return w.DefWindowProcW(hwnd, message, wparam, lparam)
