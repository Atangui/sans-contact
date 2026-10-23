import json
import string
from pathlib import Path

import numpy as np
import pytest

from sanscontact.capture.devices import CameraDevice, find_camera, is_infrared
from sanscontact.power import PowerState, Reason
from sanscontact.ui.icons import render_iris, to_bgra
from sanscontact.ui.native import parse_hotkey
from sanscontact.ui.strings import hotkey_label, t

STRINGS = Path(__file__).resolve().parents[1] / "src" / "sanscontact" / "ui" / "strings.fr.json"


def test_every_state_and_reason_has_a_french_text():
    table = json.loads(STRINGS.read_text(encoding="utf-8"))
    for state in PowerState:
        assert f"state.{state.value}" in table and f"hint.{state.value}" in table
    for reason in Reason:
        assert f"reason.{reason.value}" in table


def test_all_placeholders_are_known():
    table = json.loads(STRINGS.read_text(encoding="utf-8"))
    allowed = {"app", "state", "detail", "net", "hotkey", "seconds", "camera", "width", "height", "fps"}
    for key, text in table.items():
        fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
        assert fields <= allowed, key


def test_consent_text_explains_the_three_points():
    body = t("consent.body", camera="Cam", width=640, height=480, hotkey="Ctrl + Alt")
    for expected in ("filme", "calculé", "jamais conservé", "arrêter", "supprimer", "Windows Hello"):
        assert expected in body
    assert len(t("tray.tooltip", state="Actif", detail="x" * 40, net=0)) < 128


def test_hotkeys():
    assert parse_hotkey("Ctrl+Alt+Shift+Space") == (0x2 | 0x1 | 0x4, 0x20)
    assert parse_hotkey("ctrl + alt + s") == (0x3, ord("S"))
    assert parse_hotkey("Ctrl+F9") == (0x2, 0x78)
    for bad in ("Space", "Ctrl+Alt", "Ctrl+Nope"):
        with pytest.raises(ValueError):
            parse_hotkey(bad)
    assert hotkey_label("Ctrl+Alt+Shift+Space") == "Ctrl + Alt + Maj + Espace"


@pytest.mark.parametrize("name, infrared", [
    ("HP IR Camera", True), ("Integrated IR Camera", True), ("Windows Hello Face Camera", True),
    ("Caméra infrarouge", True), ("Intel RealSense Depth Camera", True), ("HP 5MP Camera", False),
    ("Integrated Camera", False), ("IRIS webcam", False), ("Logitech BRIO", False),
])
def test_infrared_cameras_are_recognised(name, infrared):
    assert is_infrared(name) is infrared


def test_camera_choice_is_explicit_when_several(monkeypatch):
    cams = [CameraDevice("msmf", 0, "A", False), CameraDevice("msmf", 1, "IR", True)]
    monkeypatch.setattr("sanscontact.capture.devices.list_cameras", lambda backend: cams)
    assert find_camera("msmf", None).name == "A"  # the only eligible one
    assert find_camera("msmf", "IR") is None  # never the infrared one, even if named
    cams.append(CameraDevice("msmf", 2, "B", False))
    assert find_camera("msmf", None) is None  # two eligible: the person must choose
    assert find_camera("msmf", "B").index == 2


@pytest.mark.parametrize("size", [16, 20, 24, 32, 48])
def test_icons_render_at_every_size(size):
    images = {s: render_iris(s, size) for s in PowerState}
    for img in images.values():
        assert img.shape == (size, size, 4) and img.dtype == np.uint8
        assert img[0, 0, 3] == 0 and img[size // 2, size // 2, 3] == 255
    # every state looks different (shape and colour)
    states = list(images.values())
    for i in range(len(states)):
        for j in range(i + 1, len(states)):
            assert np.abs(states[i].astype(int) - states[j].astype(int)).sum() > 0


def test_premultiplied_conversion():
    rgba = np.array([[[200, 100, 50, 128]]], dtype=np.uint8)
    assert to_bgra(rgba, premultiplied=False).tolist() == [[[50, 100, 200, 128]]]
    assert to_bgra(rgba, premultiplied=True).tolist() == [[[25, 50, 100, 128]]]
