"""Where SansContact may store data: %LOCALAPPDATA%\\SansContact and nowhere else.

Documents, Desktop and OneDrive folders are synchronised to the cloud on many
PCs, so any path inside them is refused.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from sanscontact.branding import APP_NAME

_CLOUD_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync")


class UnsafeStorageError(RuntimeError):
    """Raised when a storage path could end up synchronised to the cloud."""


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise UnsafeStorageError("LOCALAPPDATA is not defined")
    path = Path(base) / APP_NAME
    check_storage_location(path)
    return path


def check_storage_location(path: Path) -> None:
    resolved = Path(os.path.abspath(path))
    lowered = [part.lower() for part in resolved.parts]
    if any(marker in part for part in lowered for marker in _CLOUD_MARKERS):
        raise UnsafeStorageError(f"refusing a cloud-synchronised folder: {resolved}")
    for root in _synced_roots():
        if resolved == root or root in resolved.parents:
            raise UnsafeStorageError(f"refusing a folder that may be synchronised: {resolved}")


def _synced_roots() -> list[Path]:
    roots = []
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        value = os.environ.get(var)
        if value:
            roots.append(Path(os.path.abspath(value)))
    roots.extend(_known_folders())
    return roots


def _known_folders() -> list[Path]:
    from sanscontact import _win32 as w

    folders = []
    for folder_id in (w.FOLDERID_DOCUMENTS, w.FOLDERID_DESKTOP):
        raw = ctypes.c_wchar_p()
        if w.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(raw)) == w.S_OK:
            try:
                folders.append(Path(os.path.abspath(raw.value)))
            finally:
                w.CoTaskMemFree(raw)
    return folders
