"""
Module Name: logger.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Configures Loguru-backed logging and provides standardized module logger
    helpers for the application. Centralizes logger naming and setup.

Location:
    /utils/logger.py

"""

# Bottleneck: repeated setup_logger calls are guarded; minimal impact.
# Upgrade: consider structured logging schema defaults.

import logging
from typing import Optional

from utils.loguru_config import setup_loguru


_LOGGER_INITIALIZED = False

# Ensure SUCCESS level exists for standard logging
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kws)


# Patch logging.Logger to include success (idempotent)
logging.Logger.success = success


def setup_logger(name: str = "AuralArchive", log_file: str = "auralarchive_web.log", level: int = logging.INFO):
    """Initialize logging via Loguru while preserving the existing API."""
    global _LOGGER_INITIALIZED

    standardized_name = _standardize_name(name)

    if not _LOGGER_INITIALIZED:
        setup_loguru(log_level=level, log_file=log_file, logger_name=standardized_name)
        _LOGGER_INITIALIZED = True

    logger = logging.getLogger(standardized_name)
    logger.setLevel(level)
    return logger


def setup_child_loggers(level: int = logging.INFO, name: str = "AuralArchive"):
    """Maintain compatibility; child loggers propagate into Loguru interceptor."""
    standardized_name = _standardize_name(name)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    logging.getLogger(standardized_name).setLevel(level)


def _standardize_name(raw_name: Optional[str]) -> str:
    """Normalize logger names to dotted, title-cased segments (Service.Audible.CatalogCover)."""
    if not raw_name:
        return "AuralArchive"

    normalized = raw_name.replace("\\", ".").replace("/", ".").replace("_", ".").replace(" ", ".")
    parts = [segment for segment in normalized.split(".") if segment]
    return ".".join(part[:1].upper() + part[1:] for part in parts)


def get_module_logger(module_name: str):
    """Return a standard logger; Loguru intercepts its output."""
    if not _LOGGER_INITIALIZED:
        setup_logger()

    standardized = _standardize_name(module_name)
    logger = logging.getLogger(standardized)
    logger.success = logging.Logger.success.__get__(logger, logger.__class__)
    logger.debug("Initialized module logger", extra={"logger_name": standardized})
    return logger


def get_logger(name: str = "AuralArchive"):
    """Return the named logger (intercepted by Loguru)."""
    if not _LOGGER_INITIALIZED:
        setup_logger(name)

    standardized = _standardize_name(name)
    logger = logging.getLogger(standardized)
    logger.success = logging.Logger.success.__get__(logger, logger.__class__)
    logger.debug("Initialized named logger", extra={"logger_name": standardized})
    return logger