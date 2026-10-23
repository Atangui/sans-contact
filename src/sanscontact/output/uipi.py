"""Detect windows that Windows protects from simulated input (UIPI).

A program run as administrator runs at a higher integrity level; Windows then
silently drops our simulated mouse events. We detect it to tell the person,
and never suggest running SansContact as administrator to get around it.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from sanscontact import _win32 as w

UNKNOWN = -1


def _integrity_of_token(token: int) -> int:
    needed = wintypes.DWORD(0)
    w.GetTokenInformation(token, w.TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(needed))
    if not needed.value:
        return UNKNOWN
    buffer = ctypes.create_string_buffer(needed.value)
    if not w.GetTokenInformation(token, w.TOKEN_INTEGRITY_LEVEL, buffer, needed, ctypes.byref(needed)):
        return UNKNOWN
    sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_MANDATORY_LABEL.Label.Sid
    count = w.GetSidSubAuthorityCount(sid)[0]
    return int(w.GetSidSubAuthority(sid, count - 1)[0])


def process_integrity(pid: int) -> int:
    """Integrity level RID (0x2000 medium, 0x3000 high...), or UNKNOWN."""
    process = w.OpenProcess(w.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return UNKNOWN
    try:
        token = w.HANDLE()
        if not w.OpenProcessToken(process, w.TOKEN_QUERY, ctypes.byref(token)):
            # Access to the token of an elevated process is usually denied.
            return 0x3000 if ctypes.get_last_error() == w.ERROR_ACCESS_DENIED else UNKNOWN
        try:
            return _integrity_of_token(token)
        finally:
            w.CloseHandle(token)
    finally:
        w.CloseHandle(process)


def own_integrity() -> int:
    token = w.HANDLE()
    if not w.OpenProcessToken(w.GetCurrentProcess(), w.TOKEN_QUERY, ctypes.byref(token)):
        return UNKNOWN
    try:
        return _integrity_of_token(token)
    finally:
        w.CloseHandle(token)


def _window_pid(hwnd) -> int:
    if not hwnd:
        return 0
    root = w.GetAncestor(hwnd, w.GA_ROOT) or hwnd
    pid = wintypes.DWORD(0)
    w.GetWindowThreadProcessId(root, ctypes.byref(pid))
    return pid.value


class ElevationProbe:
    """Caches integrity levels per process id; cheap enough to call several times a second."""

    def __init__(self) -> None:
        self.own = own_integrity()
        self._cache: dict[int, int] = {}

    def _level(self, pid: int) -> int:
        if pid not in self._cache:
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[pid] = process_integrity(pid)
        return self._cache[pid]

    def blocked_at(self, x: int, y: int) -> bool:
        """True if the foreground window or the window under (x, y) refuses our input."""
        if self.own == UNKNOWN:
            return False
        pids = {_window_pid(w.GetForegroundWindow()), _window_pid(w.WindowFromPoint(wintypes.POINT(x, y)))}
        pids.discard(0)
        return any(self._level(pid) > self.own for pid in pids)
