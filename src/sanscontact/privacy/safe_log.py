"""Technical log: aggregated metrics and errors only.

Never logged: images, cursor or gaze positions, window titles, file names,
screen content. Lines carry the time since start-up, not the date, so the log
cannot serve as a diary of when the tool was used. Tracebacks never include
local variables.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "metrics.log"
LOGGER_NAME = "sanscontact"
MAX_BYTES = 512 * 1024


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def setup(directory: Path | None, *, to_file: bool, to_console: bool) -> logging.Logger:
    logger = get_logger()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    formatter = logging.Formatter("t+%(relativeCreated)08.0fms %(levelname)s %(message)s")
    if to_file and directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / LOG_FILE, maxBytes=MAX_BYTES, backupCount=1, encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if to_console and sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        logger.addHandler(console)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def close() -> None:
    """Close the log file; later messages are discarded (nothing is re-created on disk)."""
    logger = get_logger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.addHandler(logging.NullHandler())


def format_exception(exc: BaseException) -> str:
    """Traceback text without local variables (``capture_locals`` stays False)."""
    return "".join(traceback.TracebackException.from_exception(exc, capture_locals=False).format())


def install_excepthooks(on_crash) -> None:
    """Log uncaught errors (without locals) and let the app release camera and buttons."""

    def report(exc: BaseException, where: str) -> None:
        get_logger().error("uncaught error in %s:\n%s", where, format_exception(exc))
        try:
            on_crash(exc)
        except Exception as nested:  # noqa: BLE001 - last line of defence
            get_logger().error("error while handling a crash: %s", type(nested).__name__)

    def sys_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        report(exc, "main thread")

    def thread_hook(args: threading.ExceptHookArgs):
        if args.exc_value is not None:
            report(args.exc_value, f"thread {args.thread.name if args.thread else '?'}")

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
