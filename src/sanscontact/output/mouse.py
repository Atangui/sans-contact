"""Mouse injection with SendInput, absolute coordinates on the virtual desktop.

No pyautogui, no hook. The physical mouse always wins: if the cursor is not
where we put it, someone moved the real mouse and control pauses. No button is
ever left pressed: ``release_all`` is called on every pause, stop, exit and
error.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from sanscontact import _win32 as w
from sanscontact.geometry import Rect

# Tag carried by every injected event ("SCNT"), visible to debugging tools only.
EXTRA_INFO = 0x53434E54

_BUTTONS = {
    "left": (w.MOUSEEVENTF_LEFTDOWN, w.MOUSEEVENTF_LEFTUP),
    "right": (w.MOUSEEVENTF_RIGHTDOWN, w.MOUSEEVENTF_RIGHTUP),
    "middle": (w.MOUSEEVENTF_MIDDLEDOWN, w.MOUSEEVENTF_MIDDLEUP),
}


def to_absolute(x: int, y: int, desktop: Rect) -> tuple[int, int]:
    """Pixel -> 0..65535 normalised coordinate over the virtual desktop.

    Windows maps a normalised value n back to pixel floor(n * size / 65536);
    aiming at the centre of the pixel makes the round trip exact.
    """
    nx = int(((x - desktop.left) + 0.5) * 65536 / desktop.width)
    ny = int(((y - desktop.top) + 0.5) * 65536 / desktop.height)
    return min(max(nx, 0), 65535), min(max(ny, 0), 65535)


def from_absolute(nx: int, ny: int, desktop: Rect) -> tuple[int, int]:
    """Inverse mapping, as Windows applies it (used by tests)."""
    return desktop.left + (nx * desktop.width) // 65536, desktop.top + (ny * desktop.height) // 65536


def cursor_pos() -> tuple[int, int] | None:
    """Current cursor position, or None when the input desktop is not ours (UAC, lock screen)."""
    point = wintypes.POINT()
    if not w.GetCursorPos(ctypes.byref(point)):
        return None
    return point.x, point.y


class MouseOutput:
    def __init__(self, send=None, read_cursor=cursor_pos) -> None:
        self._send = send or _send_inputs
        self._read_cursor = read_cursor
        self._lock = threading.Lock()
        self.pressed: set[str] = set()
        self.last_target: tuple[int, int] | None = None
        self.desktop: Rect | None = None

    def set_desktop(self, desktop: Rect) -> None:
        self.desktop = desktop

    def forget_position(self) -> None:
        self.last_target = None

    def current_position(self) -> tuple[int, int] | None:
        return self._read_cursor()

    def moved_externally(self, tolerance: int) -> bool | None:
        """True if the real mouse moved since our last move; None if the cursor cannot be read."""
        position = self._read_cursor()
        if position is None:
            return None
        if self.last_target is None:
            return False
        return max(abs(position[0] - self.last_target[0]), abs(position[1] - self.last_target[1])) > tolerance

    def move_to(self, x: int, y: int) -> bool:
        if self.desktop is None:
            raise RuntimeError("desktop geometry unknown")
        nx, ny = to_absolute(x, y, self.desktop)
        flags = w.MOUSEEVENTF_MOVE | w.MOUSEEVENTF_ABSOLUTE | w.MOUSEEVENTF_VIRTUALDESK
        with self._lock:
            ok = self._send([_mouse_input(nx, ny, flags)]) == 1
            if ok:
                self.last_target = (x, y)
        return ok

    def press(self, button: str) -> bool:
        down, _up = _BUTTONS[button]
        with self._lock:
            ok = self._send([_mouse_input(0, 0, down)]) == 1
            if ok:
                self.pressed.add(button)
        return ok

    def release(self, button: str) -> bool:
        _down, up = _BUTTONS[button]
        with self._lock:
            ok = self._send([_mouse_input(0, 0, up)]) == 1
            self.pressed.discard(button)
        return ok

    def wheel(self, amount: int, horizontal: bool = False) -> bool:
        """Scroll by ``amount`` (WHEEL_DELTA = 120 is one notch; smaller values scroll smoothly).

        Vertical: positive scrolls up. Horizontal: positive scrolls right.
        """
        if not amount:
            return True
        flags = w.MOUSEEVENTF_HWHEEL if horizontal else w.MOUSEEVENTF_WHEEL
        event = _mouse_input(0, 0, flags)
        event.mi.mouseData = amount & 0xFFFFFFFF  # signed value in a DWORD field
        with self._lock:
            return self._send([event]) == 1

    def release_all(self) -> None:
        """Release every button this application pressed (and only those)."""
        with self._lock:
            pressed = sorted(self.pressed)
            if pressed:
                self._send([_mouse_input(0, 0, _BUTTONS[b][1]) for b in pressed])
            self.pressed.clear()


def _mouse_input(dx: int, dy: int, flags: int) -> w.INPUT:
    event = w.INPUT()
    event.type = w.INPUT_MOUSE
    event.mi = w.MOUSEINPUT(dx, dy, 0, flags, 0, EXTRA_INFO)
    return event


def _send_inputs(events: list[w.INPUT]) -> int:
    array = (w.INPUT * len(events))(*events)
    return w.SendInput(len(events), array, ctypes.sizeof(w.INPUT))
