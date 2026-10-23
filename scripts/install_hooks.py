"""Install the pre-commit hook that runs scripts/privacy_check.py --staged.

Usage: .venv\\Scripts\\python.exe scripts\\install_hooks.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".git" / "hooks" / "pre-commit"

SCRIPT = """#!/bin/sh
# SansContact: privacy check before every commit (installed by scripts/install_hooks.py).
if [ -x ".venv/Scripts/python.exe" ]; then
  exec ".venv/Scripts/python.exe" -I "scripts/privacy_check.py" --staged
fi
exec python -I "scripts/privacy_check.py" --staged
"""


def main() -> int:
    if not HOOK.parent.is_dir():
        raise SystemExit("not a git repository (.git/hooks is missing)")
    HOOK.write_text(SCRIPT, encoding="utf-8", newline="\n")
    print(f"pre-commit hook installed: {HOOK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
