"""
Helpers for translating remote download-client paths to local filesystem paths.
"""

import os
from typing import Optional


def normalize_remote_path(path: Optional[str]) -> str:
    """Normalize remote-style paths for prefix comparisons."""
    if not path:
        return ""

    normalized = str(path).replace("\\", "/").strip()
    while len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized or "/"


def remap_remote_to_local(path: Optional[str], remote_base: Optional[str], local_base: Optional[str]) -> Optional[str]:
    """Map a client-reported remote path to the equivalent local path.

    If mapping does not apply, returns the original path.
    """
    if not path:
        return path

    remote_norm = normalize_remote_path(remote_base)
    path_norm = normalize_remote_path(path)

    if not remote_norm or not local_base:
        return path

    if path_norm != remote_norm and not path_norm.startswith(remote_norm + "/"):
        return path

    local_base_abs = os.path.abspath(str(local_base))
    suffix = path_norm[len(remote_norm):].lstrip("/")
    if not suffix:
        return local_base_abs

    return os.path.join(local_base_abs, suffix.replace("/", os.sep))
