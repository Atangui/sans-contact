"""Process-wide network kill switch for Python code.

Installed first thing at start-up: every attempt to open a socket, resolve a
name or connect raises ``NetworkDisabledError`` and is counted. The count is
shown in the privacy witnesses and must stay at 0.

Native libraries can bypass Python's ``socket`` module; ``endpoints`` watches
the operating system's connection tables for that case.
"""

from __future__ import annotations

import _socket
import errno
import socket
import threading

from sanscontact.branding import APP_NAME

_lock = threading.Lock()
_attempts = 0
_last_kind: str | None = None
_originals: dict[tuple[object, str], object] | None = None


class NetworkDisabledError(OSError):
    pass


def _record(kind: str) -> NetworkDisabledError:
    global _attempts, _last_kind
    with _lock:
        _attempts += 1
        _last_kind = kind
    return NetworkDisabledError(errno.EACCES, f"{APP_NAME}: network access is disabled ({kind})")


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):  # noqa: ARG002 - signature mirrors socket.socket
        raise _record("socket")


def _blocked(kind: str):
    def refuse(*args, **kwargs):  # noqa: ARG001
        raise _record(kind)

    refuse.__name__ = f"blocked_{kind}"
    return refuse


_TARGETS: tuple[tuple[object, str], ...] = (
    (socket, "socket"),
    (socket, "create_connection"),
    (socket, "create_server"),
    (socket, "socketpair"),
    (socket, "fromfd"),
    (socket, "getaddrinfo"),
    (socket, "gethostbyname"),
    (socket, "gethostbyname_ex"),
    (socket, "gethostbyaddr"),
    (_socket, "socket"),
    (_socket, "getaddrinfo"),
    (_socket, "gethostbyname"),
    (_socket, "gethostbyname_ex"),
    (_socket, "gethostbyaddr"),
)


def install() -> None:
    global _originals
    with _lock:
        if _originals is not None:
            return
        _originals = {(module, name): getattr(module, name) for module, name in _TARGETS if hasattr(module, name)}
        for module, name in _originals:
            replacement = _BlockedSocket if name == "socket" else _blocked(name)
            setattr(module, name, replacement)


def uninstall() -> None:
    """Restore the real functions (tests only)."""
    global _originals
    with _lock:
        if _originals is None:
            return
        for (module, name), original in _originals.items():
            setattr(module, name, original)
        _originals = None


def is_installed() -> bool:
    return _originals is not None


def attempts() -> int:
    return _attempts


def last_attempt_kind() -> str | None:
    return _last_kind


def reset_counter() -> None:
    """Tests only."""
    global _attempts, _last_kind
    with _lock:
        _attempts = 0
        _last_kind = None
