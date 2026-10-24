"""Bounded console and rotating-file logging for the solution application."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

LOGGER_NAME = "solution"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = "camera.log"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3
_OWNED = "_solution_owned_handler"


def setup_logging(log_dir: Path | None = None, stream=None) -> logging.Logger:
    """Configure the solution logger once; file failures fall back to console."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(getattr(handler, _OWNED, False) for handler in logger.handlers):
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s")
    console = logging.StreamHandler(stream if stream is not None else sys.stderr)
    console.setFormatter(formatter)
    setattr(console, _OWNED, True)
    logger.addHandler(console)

    target_dir = Path(log_dir) if log_dir is not None else LOG_DIR
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            target_dir / LOG_FILE, maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT, encoding="utf-8")
        file_handler.setFormatter(formatter)
        setattr(file_handler, _OWNED, True)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Cannot open camera log directory=%s; console only: %s",
                       target_dir, exc)
    return logger


def shutdown_logging() -> None:
    """Close handlers created here; mainly useful for deterministic shutdown/tests."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, _OWNED, False):
            logger.removeHandler(handler)
            handler.close()
