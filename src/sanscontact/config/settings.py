"""User settings: numeric parameters only, stored as readable JSON.

Nothing here describes the person: no image, no sample, no position history.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

SETTINGS_FILE = "settings.json"

_CHOICES = {
    "camera_backend": ("msmf", "dshow"),
    "hand": ("any", "left", "right"),
    "pointer_landmark": ("palm_center", "index_mcp"),
}
_RANGES = {
    "frame_width": (160, 1920),
    "frame_height": (120, 1080),
    "frame_rate": (5, 60),
    "num_hands": (1, 2),
    "opencv_threads": (1, 16),
    "one_euro_min_cutoff": (0.01, 10.0),
    "one_euro_beta": (0.0, 1.0),
    "one_euro_d_cutoff": (0.1, 10.0),
    "engagement_hold_s": (0.3, 3.0),
    "disengage_after_s": (1.0, 15.0),
    "pause_timeout_s": (5.0, 600.0),
    "physical_mouse_tolerance_px": (1, 50),
}


@dataclass
class Settings:
    version: int = 1
    camera_name: str | None = None
    # MSMF is listed but not shipped in the OpenCV 5.0 PyPI build: DirectShow is the measured choice.
    camera_backend: str = "dshow"
    frame_width: int = 640
    frame_height: int = 480
    frame_rate: int = 30
    num_hands: int = 1
    opencv_threads: int = 4
    hand: str = "any"
    pointer_landmark: str = "palm_center"
    active_zone: list[float] = field(default_factory=lambda: [0.2, 0.15, 0.8, 0.75])
    one_euro_min_cutoff: float = 1.0
    one_euro_beta: float = 0.015
    one_euro_d_cutoff: float = 1.0
    engagement_hold_s: float = 1.0
    disengage_after_s: float = 3.0
    pause_timeout_s: float = 30.0
    physical_mouse_tolerance_px: int = 3
    # Ctrl+Alt+Space (the mock-up's shortcut) is often taken by other software.
    hotkey: str = "Ctrl+Alt+Shift+Space"
    release_on_display_off: bool = True
    metrics_log: bool = True

    def validated(self) -> Settings:
        """Return a copy with every value brought back into its allowed range."""
        data = asdict(self)
        defaults = Settings()
        for name, allowed in _CHOICES.items():
            if data[name] not in allowed:
                data[name] = getattr(defaults, name)
        for name, (low, high) in _RANGES.items():
            kind = type(getattr(defaults, name))
            try:
                value = kind(data[name])
            except (TypeError, ValueError):
                value = getattr(defaults, name)
            data[name] = min(max(value, kind(low)), kind(high))
        data["active_zone"] = _valid_zone(data["active_zone"], defaults.active_zone)
        if data["camera_name"] is not None and not isinstance(data["camera_name"], str):
            data["camera_name"] = None
        if not isinstance(data["hotkey"], str) or not data["hotkey"].strip():
            data["hotkey"] = defaults.hotkey
        for name in ("release_on_display_off", "metrics_log"):
            data[name] = bool(data[name])
        return Settings(**data)


def _valid_zone(zone, default: list[float]) -> list[float]:
    try:
        x0, y0, x1, y1 = (float(v) for v in zone)
    except (TypeError, ValueError):
        return list(default)
    x0, x1 = sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
    y0, y1 = sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))
    if x1 - x0 < 0.1 or y1 - y0 < 0.1:
        return list(default)
    return [x0, y0, x1, y1]


def load(directory: Path) -> Settings:
    path = directory / SETTINGS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known}).validated()


def save(directory: Path, settings: Settings) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SETTINGS_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings.validated()), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
