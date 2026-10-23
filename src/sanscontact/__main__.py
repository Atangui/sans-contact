"""Entry point: ``python -m sanscontact``.

The network guard is installed before anything else is imported, so no code
path of the application can open a connection.
"""

from __future__ import annotations

import sys


def main() -> int:
    from sanscontact.privacy import network_guard

    network_guard.install()
    from sanscontact.app import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
