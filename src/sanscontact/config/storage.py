"""« Supprimer toutes mes données »: remove everything SansContact stored on this PC."""

from __future__ import annotations

import shutil
from pathlib import Path

from sanscontact.branding import APP_NAME


def stored_items(directory: Path) -> list[str]:
    """Names of what is stored, for the privacy witnesses."""
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir())


def delete_all_data(directory: Path) -> bool:
    """Delete the data folder. Returns True if something was deleted.

    Refuses anything that is not a real folder named after the application, so a
    wrong path can never wipe something else.
    """
    if not directory.exists():
        return False
    if directory.name != APP_NAME or directory.is_symlink() or directory.is_junction():
        raise ValueError(f"refusing to delete unexpected path: {directory}")
    if not directory.is_dir():
        raise ValueError(f"not a folder: {directory}")
    for child in directory.rglob("*"):
        if child.is_symlink() or child.is_junction():
            raise ValueError(f"refusing to follow a link inside the data folder: {child}")
    shutil.rmtree(directory)
    return True
