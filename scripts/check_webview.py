"""Check pywebview + WebView2 on this machine: opens a hidden window, lists our open ports.

The window loads an inline HTML string (no file, no server) and is never shown.
Run with ``--guard`` to check it also works with the network kill switch installed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

if "--guard" in sys.argv:
    from sanscontact.privacy import network_guard

    network_guard.install()

import webview  # noqa: E402

from sanscontact.privacy import network_guard  # noqa: E402
from sanscontact.privacy.endpoints import endpoints  # noqa: E402

result: dict = {}


def probe(window) -> None:
    time.sleep(2.0)
    try:
        result["page_title"] = window.evaluate_js("document.title")
    except Exception as exc:  # noqa: BLE001
        result["page_title_error"] = type(exc).__name__
    own = endpoints()
    result["listening_ports"] = [e.local for e in own if e.listening]
    result["endpoints"] = len(own)
    result["blocked_python_attempts"] = network_guard.attempts()
    window.destroy()


window = webview.create_window("check", html="<!doctype html><title>ok</title><p>ok</p>", hidden=True)
started = time.perf_counter()
webview.start(probe, window, private_mode=True)
result["pywebview"] = getattr(webview, "__version__", "?")
result["python"] = sys.version.split()[0]
result["guard"] = "--guard" in sys.argv
result["seconds"] = round(time.perf_counter() - started, 1)
print(json.dumps(result))
