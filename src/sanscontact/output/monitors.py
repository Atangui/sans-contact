"""Screens of the virtual desktop, in physical pixels.

The process declares itself PER_MONITOR_AWARE_V2 before creating any window,
so coordinates are never virtualised by Windows' DPI scaling.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from sanscontact import _win32 as w
from sanscontact.geometry import Rect, union


@dataclass(frozen=True)
class Monitor:
    name: str
    rect: Rect
    work: Rect
    dpi: int
    primary: bool

    @property
    def scale_percent(self) -> int:
        return round(self.dpi * 100 / 96)


def enable_per_monitor_dpi_awareness() -> bool:
    """True if the process is now PER_MONITOR_AWARE_V2 (False if it was already set otherwise)."""
    return bool(w.SetProcessDpiAwarenessContext(w.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))


def list_monitors() -> list[Monitor]:
    monitors: list[Monitor] = []

    def callback(hmonitor, _hdc, _rect, _data):
        info = w.MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(w.MONITORINFOEXW)
        if w.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            dpi_x, dpi_y = ctypes.c_uint(96), ctypes.c_uint(96)
            if w.GetDpiForMonitor(hmonitor, w.MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
                dpi_x.value = 96
            r, k = info.rcMonitor, info.rcWork
            monitors.append(Monitor(
                name=info.szDevice,
                rect=Rect(r.left, r.top, r.right, r.bottom),
                work=Rect(k.left, k.top, k.right, k.bottom),
                dpi=dpi_x.value,
                primary=bool(info.dwFlags & w.MONITORINFOF_PRIMARY),
            ))
        return True

    w.EnumDisplayMonitors(None, None, w.MONITORENUMPROC(callback), 0)
    return monitors


def virtual_desktop(monitors: list[Monitor] | None = None) -> Rect:
    monitors = monitors if monitors is not None else list_monitors()
    if monitors:
        return union([m.rect for m in monitors])
    x, y = w.GetSystemMetrics(w.SM_XVIRTUALSCREEN), w.GetSystemMetrics(w.SM_YVIRTUALSCREEN)
    return Rect(x, y, x + w.GetSystemMetrics(w.SM_CXVIRTUALSCREEN), y + w.GetSystemMetrics(w.SM_CYVIRTUALSCREEN))


def primary(monitors: list[Monitor]) -> Monitor | None:
    return next((m for m in monitors if m.primary), monitors[0] if monitors else None)
