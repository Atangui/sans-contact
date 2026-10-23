"""The iris icon, drawn by code at any size (no image file, no image library).

Same geometry as the iris switch (100 x 100 view box): a barrel, dark blades,
and either six seams meeting at a pin (closed) or a hexagonal lens (open).
Each state differs by shape as well as colour:
off = closed iris, standby = lens outline, active = filled lens,
paused = lens with a pause sign.
"""

from __future__ import annotations

import ctypes
import math

import numpy as np

from sanscontact import _win32 as w
from sanscontact.power import PowerState

SUPERSAMPLE = 4

# Studio theme tokens (RGB). The tray must read on light and dark taskbars alike.
_BARREL = (0x1B, 0x1F, 0x27)
_BLADE = (0x26, 0x2B, 0x34)
_SEAM = (0x6B, 0x70, 0x7A)
_MUTED = (0x9A, 0x9F, 0xAB)
_AMBER = (0xFF, 0xB0, 0x3B)
_BLUE = (0x8F, 0xB3, 0xFF)

_RIM = {PowerState.OFF: _MUTED, PowerState.STANDBY: _AMBER, PowerState.ACTIVE: _AMBER, PowerState.PAUSED: _BLUE}


def _grid(size: int) -> tuple[np.ndarray, np.ndarray]:
    n = size * SUPERSAMPLE
    coords = (np.arange(n) + 0.5) * (100.0 / n)
    return np.meshgrid(coords, coords)


def _disc(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _hexagon(x, y, r, cx=50.0, cy=50.0):
    vertices = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    inside = np.ones_like(x, dtype=bool)
    for (x0, y0), (x1, y1) in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        inside &= (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0) >= 0
    return inside


def _segment(x, y, p0, p1, width):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
    return (x - (x0 + t * dx)) ** 2 + (y - (y0 + t * dy)) ** 2 <= (width / 2) ** 2


def _rotate(point, degrees, cx=50.0, cy=50.0):
    a = math.radians(degrees)
    px, py = point[0] - cx, point[1] - cy
    return cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)


def render_iris(state: PowerState, size: int) -> np.ndarray:
    """Straight-alpha RGBA image, shape (size, size, 4), uint8."""
    x, y = _grid(size)
    rgba = np.zeros(x.shape + (4,), dtype=np.float64)

    def paint(mask, color, alpha=1.0):
        a = mask.astype(np.float64) * alpha
        for c in range(3):
            rgba[..., c] = color[c] / 255.0 * a + rgba[..., c] * (1 - a)
        rgba[..., 3] = a + rgba[..., 3] * (1 - a)

    rim = _RIM[state]
    stroke = 7.0 if size <= 24 else 5.0
    paint(_disc(x, y, 50, 50, 49), rim)
    paint(_disc(x, y, 50, 50, 49 - stroke), _BARREL)
    paint(_disc(x, y, 50, 50, 41 - (stroke - 5) / 2), _BLADE)

    if state is PowerState.OFF:
        seam_width = 4.0 if size <= 24 else 2.5
        for k in range(6):
            p0 = _rotate((51.5, 52.6), 60 * k)
            p1 = _rotate((32.3, 85.87), 60 * k)
            paint(_segment(x, y, p0, p1, seam_width), _SEAM)
        paint(_hexagon(x, y, 6.0), _SEAM)
    else:
        lens_r = 22.0
        lens = _hexagon(x, y, lens_r)
        if state is PowerState.STANDBY:
            paint(lens, rim, 0.25)
            paint(lens & ~_hexagon(x, y, lens_r - 6.0), rim)
        elif state is PowerState.ACTIVE:
            paint(lens, rim)
            paint(_disc(x, y, 44, 43, 4.0), (255, 255, 255), 0.55)
        else:
            paint(lens, rim)
            for bx in (44.0, 56.0):
                paint((abs(x - bx) <= 3.2) & (abs(y - 50) <= 10.0), _BLADE)

    n = size
    s = SUPERSAMPLE
    blocks = rgba.reshape(n, s, n, s, 4)
    alpha = blocks[..., 3].mean(axis=(1, 3))
    color = (blocks[..., :3] * blocks[..., 3:4]).mean(axis=(1, 3))
    safe = np.where(alpha > 1e-6, alpha, 1.0)[..., None]
    out = np.zeros((n, n, 4), dtype=np.float64)
    out[..., :3] = color / safe
    out[..., 3] = alpha
    return np.clip(np.round(out * 255), 0, 255).astype(np.uint8)


def to_bgra(rgba: np.ndarray, premultiplied: bool) -> np.ndarray:
    bgra = rgba[..., [2, 1, 0, 3]].astype(np.float64)
    if premultiplied:
        bgra[..., :3] *= bgra[..., 3:4] / 255.0
    return np.ascontiguousarray(np.round(bgra).astype(np.uint8))


def _dib(width: int, height: int):
    header = w.BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(w.BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down rows
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = w.BI_RGB
    bits = ctypes.c_void_p()
    bitmap = w.CreateDIBSection(None, ctypes.byref(header), w.DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
    if not bitmap or not bits.value:
        raise OSError("CreateDIBSection failed")
    return bitmap, bits.value


def make_hicon(state: PowerState, size: int):
    """An HICON for the notification area. Destroy it with DestroyIcon."""
    bgra = to_bgra(render_iris(state, size), premultiplied=False)
    color, bits = _dib(size, size)
    ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
    mask_bits = (ctypes.c_ubyte * (((size + 15) // 16) * 2 * size))()
    mask = w.CreateBitmap(size, size, 1, 1, mask_bits)
    try:
        info = w.ICONINFO(True, 0, 0, mask, color)
        icon = w.CreateIconIndirect(ctypes.byref(info))
        if not icon:
            raise OSError("CreateIconIndirect failed")
        return icon
    finally:
        w.DeleteObject(color)
        w.DeleteObject(mask)


def make_layered_bitmap(state: PowerState, size: int):
    """A premultiplied 32-bit DIB for UpdateLayeredWindow. Delete it with DeleteObject."""
    bgra = to_bgra(render_iris(state, size), premultiplied=True)
    bitmap, bits = _dib(size, size)
    ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
    return bitmap
