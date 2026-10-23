"""Download the MediaPipe model bundles once, from Google's official storage.

Each file is checked against a pinned SHA-256 before it is kept. The application
itself never downloads anything: it only reads the verified files in ``models/``.

Usage:
    .venv\\Scripts\\python.exe scripts\\fetch_models.py           # every pinned model
    .venv\\Scripts\\python.exe scripts\\fetch_models.py --force   # download again
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sanscontact.perception.models import MODELS, MODELS_DIR, ModelSpec  # noqa: E402

CHUNK = 1 << 16


def download(spec: ModelSpec, force: bool = False) -> Path:
    target = MODELS_DIR / spec.filename
    if target.exists() and not force:
        if _sha256(target.read_bytes()) == spec.sha256:
            print(f"OK      {spec.filename} (already present, hash verified)")
            return target
        print(f"WARNING {spec.filename}: hash mismatch, downloading again")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=MODELS_DIR, delete=False, suffix=".part") as tmp:
        tmp_path = Path(tmp.name)
        with urllib.request.urlopen(spec.url, timeout=60) as response:
            while chunk := response.read(CHUNK):
                digest.update(chunk)
                tmp.write(chunk)
    actual = digest.hexdigest()
    if actual != spec.sha256:
        tmp_path.unlink(missing_ok=True)
        raise SystemExit(
            f"ERROR   {spec.filename}: SHA-256 mismatch\n  expected {spec.sha256}\n  got      {actual}"
        )
    tmp_path.replace(target)
    print(f"OK      {spec.filename} downloaded and verified ({target.stat().st_size} bytes)")
    return target


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="download again even if present")
    args = parser.parse_args()
    for spec in MODELS.values():
        download(spec, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
