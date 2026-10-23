"""Record that the person accepted the explanation shown before the first activation.

Only the version of the accepted text is stored, never a date.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONSENT_FILE = "consent.json"
# Bump when the consent text changes: the person is asked again.
CONSENT_VERSION = 1


def is_accepted(directory: Path) -> bool:
    try:
        data = json.loads((directory / CONSENT_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and data.get("version") == CONSENT_VERSION


def accept(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CONSENT_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": CONSENT_VERSION}), encoding="utf-8")
    os.replace(tmp, path)
