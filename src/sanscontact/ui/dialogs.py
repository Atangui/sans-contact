"""Native message boxes (phase 1). The designed screens arrive with the interface."""

from __future__ import annotations

from sanscontact import _win32 as w
from sanscontact.branding import APP_NAME
from sanscontact.ui.strings import hotkey_label, t

_BASE = w.MB_TOPMOST | w.MB_SETFOREGROUND


def ask_consent(camera: str, width: int, height: int, hotkey: str) -> bool:
    body = t("consent.body", camera=camera, width=width, height=height, hotkey=hotkey_label(hotkey))
    answer = w.MessageBoxW(None, body, t("consent.title"), _BASE | w.MB_OKCANCEL | w.MB_ICONINFORMATION
                           | w.MB_DEFBUTTON2)
    return answer == w.IDOK


def confirm_delete() -> bool:
    answer = w.MessageBoxW(None, t("delete.body"), t("delete.title"), _BASE | w.MB_YESNO | w.MB_ICONWARNING
                           | w.MB_DEFBUTTON2)
    return answer == w.IDYES


def info(text: str) -> None:
    w.MessageBoxW(None, text, APP_NAME, _BASE | w.MB_OK | w.MB_ICONINFORMATION)


def warn(text: str) -> None:
    w.MessageBoxW(None, text, APP_NAME, _BASE | w.MB_OK | w.MB_ICONWARNING)
