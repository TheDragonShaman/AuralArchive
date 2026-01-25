"""
Module Name: paths.py
Author: TheDragonShaman
Created: Jan 18 2026
Description:
    Centralized helpers for resolving config-based file paths.
    Now uses the universal path resolver for consistent behavior.
"""

import os
from pathlib import Path
from typing import Union

from utils.path_resolver import get_path_resolver


def resolve_config_dir() -> str:
    """Resolve the configuration directory using the path resolver."""
    return get_path_resolver().get_config_dir()


def resolve_config_path(filename: str) -> str:
    """Resolve a filename under the configuration directory."""
    return os.path.join(resolve_config_dir(), filename)


def resolve_users_file() -> str:
    """Return the path to users.json in the config directory."""
    return resolve_config_path("users.json")


def resolve_audible_auth_file() -> Union[str, Path]:
    """Return the path to audible_auth.json in the config directory."""
    return resolve_config_path("audible_auth.json")
