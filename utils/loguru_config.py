"""
Module Name: loguru_config.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Sets up Loguru sinks, logging interception, and naming conventions for
    application loggers. Bridges standard logging to Loguru handlers.

Location:
    /utils/loguru_config.py

"""

# Bottleneck: console sink formatting on high-volume logs; keep levels sane.
# Upgrade: add JSON sink option for structured logging pipelines.

import logging
import sys
from pathlib import Path
from typing import Union

from loguru import logger


def _standardize_name(raw_name: Union[str, int]) -> str:
    """Normalize logger names to dotted, title-cased segments (Service.Audible.CatalogCover)."""
    if not raw_name:
        return "AuralArchive"
    if isinstance(raw_name, int):
        return str(raw_name)

    normalized = str(raw_name).replace("\\", ".").replace("/", ".").replace("_", ".").replace(" ", ".")
    parts = [segment for segment in normalized.split(".") if segment]
    return ".".join(part[:1].upper() + part[1:] for part in parts)


class InterceptHandler(logging.Handler):
    """Route standard logging records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_name == "emit":
            frame = frame.f_back
            depth += 1

        logger_name = _standardize_name(record.name)

        logger.bind(logger_name=logger_name).opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _coerce_level(level: Union[str, int]) -> Union[str, int]:
    if isinstance(level, str):
        return level.upper()
    if isinstance(level, int):
        return level
    try:
        return int(level)
    except Exception:
        return "INFO"


CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "| <level>{level: <8}</level> "
    "| <cyan>{extra[logger_name]}</cyan> - "
    "<level>{message}</level>"
)
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {extra[logger_name]} - {message}"


def setup_loguru(log_level: Union[str, int] = "INFO", log_file: str = "auralarchive_web.log", logger_name: str = "AuralArchive"):
    """Configure Loguru sinks and hook standard logging into Loguru."""

    # Ensure SUCCESS level is available in Loguru (built-in by default, guard just in case)
    try:
        logger.level("SUCCESS")
    except ValueError:
        logger.level("SUCCESS", no=25, color="<green>")

    level = _coerce_level(log_level)
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file

    # Reset existing Loguru configuration
    logger.remove()

    # Console sink with color
    logger.add(
        sys.stdout,
        level=level,
        format=CONSOLE_FORMAT,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        colorize=True,
    )

    # Rotating file sink (plain text)
    logger.add(
        log_path,
        level=level,
        format=FILE_FORMAT,
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.NOTSET, force=True)
    logging.getLogger().setLevel(logging.NOTSET)

    # Quiet noisy third-party loggers we don't control
    for noisy in ("audible", "audible.auth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    standardized_root = _standardize_name(logger_name)

    # Default logger name for direct Loguru usage
    logger.configure(extra={"logger_name": standardized_root})

    return logger
