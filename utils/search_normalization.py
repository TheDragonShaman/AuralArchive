"""
Module Name: search_normalization.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Normalizes title, author, and query strings for consistent search lookups.
    Provides helpers to split combined title/author strings and drop subtitles
    to improve match quality across indexers.

Location:
    /utils/search_normalization.py

"""

# Bottleneck: regex-heavy parsing per call; consider caching compiled patterns if hot.
# Upgrade: add optional locale-aware normalization for non-ASCII titles.

from __future__ import annotations

import re
from typing import Tuple

from utils.logger import get_module_logger

__all__ = ["normalize_search_terms", "strip_subtitle"]


_LOGGER = get_module_logger("Utils.SearchNormalization")


def split_title_author(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""
    parts = re.split(r"\s+by\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


def strip_subtitle(text: str) -> str:
    if not text:
        return ""
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return text.strip()


def normalize_search_terms(query: str, title: str, author: str) -> Tuple[str, str, str]:
    original_query = query
    original_title = title
    original_author = author

    query = (query or "").strip()
    title = (title or "").strip()
    author = (author or "").strip()

    if not title and query:
        title = query

    title_base, title_author = split_title_author(title)
    query_base, query_author = split_title_author(query)

    normalized_author = (author or title_author or query_author).strip()
    normalized_title = strip_subtitle(title_base)
    normalized_query_base = strip_subtitle(query_base)

    if normalized_title and normalized_author:
        normalized_query = f"{normalized_title} {normalized_author}".strip()
    elif normalized_title:
        normalized_query = normalized_title
    elif normalized_query_base:
        normalized_query = normalized_query_base
    else:
        normalized_query = normalized_author

    if not normalized_query:
        normalized_query = normalized_title or normalized_query_base or ""

    normalized_query = normalized_query.strip()

    _LOGGER.debug(
        "Normalized search terms",
        extra={
            "query": original_query,
            "title": original_title,
            "author": original_author,
            "normalized_query": normalized_query,
            "normalized_title": normalized_title,
            "normalized_author": normalized_author,
        },
    )

    return normalized_query, normalized_title, normalized_author
