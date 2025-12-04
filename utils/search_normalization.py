"""Shared helpers for normalizing search terms across the app."""

from __future__ import annotations

import re
from typing import Tuple

__all__ = ["normalize_search_terms", "strip_subtitle"]


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

    return normalized_query.strip(), normalized_title, normalized_author
