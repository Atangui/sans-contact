"""Every user-facing text lives in one JSON file per language (French for now)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from sanscontact.branding import APP_NAME

_DIR = Path(__file__).resolve().parent


@cache
def _table(language: str) -> dict[str, str]:
    return json.loads((_DIR / f"strings.{language}.json").read_text(encoding="utf-8"))


def t(key: str, language: str = "fr", **values: object) -> str:
    text = _table(language).get(key, key)
    return text.format(app=APP_NAME, **values) if ("{" in text) else text


def hotkey_label(hotkey: str, language: str = "fr") -> str:
    """'Ctrl+Alt+Space' -> 'Ctrl + Alt + Espace' for display."""
    names = {"fr": {"Space": "Espace", "Shift": "Maj", "Win": "Windows"}}.get(language, {})
    return " + ".join(names.get(part.strip(), part.strip()) for part in hotkey.split("+"))
