"""Audible ownership validation helpers.

Centralized logic ensuring Audible downloads only occur for titles that are
verified as owned within the synchronized Audible library.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger("AudibleOwnershipValidator")

AUDIBLE_OWNERSHIP_TAG_HINTS: Set[str] = set()

_UNVERIFIED_SYNC_STATUSES: Set[str] = set()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def merge_audible_records(primary: Optional[Dict[str, Any]], secondary: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Merge two metadata records, preferring populated values from ``primary``."""
    if primary is None and secondary is None:
        return None

    if primary is None:
        return dict(secondary)
    if secondary is None:
        return dict(primary)

    merged = dict(primary)
    secondary_source = secondary.get("_source_table") or secondary.get("source_table")

    for key, value in secondary.items():
        if key.startswith("_"):
            continue
        if key not in merged or _is_missing(merged.get(key)):
            merged[key] = value

    if secondary_source:
        combined = merged.get("_source_table") or primary.get("_source_table")
        if combined and secondary_source not in combined:
            merged["_source_table"] = f"{combined}+{secondary_source}"
        elif not combined:
            merged["_source_table"] = secondary_source

    return merged


def _normalize_purchase_date(raw_value: Any) -> Optional[str]:
    """Normalize stored purchase date values to a canonical string or None."""
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if not cleaned:
            return None
        if cleaned.lower() in {"none", "null", "n/a", "pending"}:
            return None
        if cleaned in {"0000-00-00", "0000-00-00T00:00:00"}:
            return None
        return cleaned

    return str(raw_value)


def _normalize_tag_collection(raw_tags: Any) -> Set[str]:
    """Normalize tag metadata into a lowercase set for comparisons."""
    if not raw_tags:
        return set()

    if isinstance(raw_tags, str):
        raw = raw_tags.strip()
        if not raw:
            return set()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, (list, tuple, set)):
            raw_tags = parsed
        elif isinstance(parsed, dict):
            raw_tags = list(parsed.keys())
        else:
            return {tag.strip().lower() for tag in raw.split(",") if tag.strip()}

    if isinstance(raw_tags, (list, tuple, set)):
        return {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}

    return {str(raw_tags).strip().lower()} if str(raw_tags).strip() else set()


def assess_audible_ownership(entry: Optional[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
    """Evaluate whether stored metadata confirms Audible ownership.

    Args:
        entry: Database row represented as a dict (books table preferred, legacy
            audible_library rows still supported).

    Returns:
        Tuple containing the ownership verdict and context details used to
        explain the decision. The context dict always contains human-friendly
        "reason", along with metadata fields for logging/UI purposes.
    """
    details: Dict[str, Any] = {
        "reason": "No Audible library entry found for this ASIN.",
        "sync_status": None,
        "metadata_source": None,
        "purchase_date": None,
        "tags": [],
        "hints": [],
        "status": None,
        "ownership_status": None,
        "source_table": None,
    }

    if not entry:
        logger.debug("Ownership validation failed: no library entry present.")
        return False, details

    sync_status = (entry.get("sync_status") or "").strip().lower()
    metadata_source = (entry.get("metadata_source") or entry.get("source") or "").strip().lower()
    purchase_date = _normalize_purchase_date(entry.get("purchase_date") or entry.get("PurchaseDate"))
    tags = _normalize_tag_collection(entry.get("tags"))
    status_value = (entry.get("status") or entry.get("Status") or "").strip().lower()
    ownership_status = (entry.get("ownership_status") or "").strip().lower()
    source_table = entry.get("_source_table") or entry.get("source_table")

    details.update(
        {
            "sync_status": sync_status or None,
            "metadata_source": metadata_source or None,
            "purchase_date": purchase_date,
            "tags": sorted(tags),
            "status": status_value or None,
            "ownership_status": ownership_status or None,
            "source_table": source_table,
        }
    )

    if sync_status and sync_status in _UNVERIFIED_SYNC_STATUSES:
        details["reason"] = (
            f"Audible library sync status '{sync_status or 'unknown'}' is not verified yet."
        )
        logger.debug("Ownership validation failed: sync status '%s'", sync_status)
        return False, details

    ownership_hints = []

    if purchase_date:
        ownership_hints.append("purchase_date")
    if metadata_source and "audible" in metadata_source:
        ownership_hints.append(f"metadata_source:{metadata_source}")
    if status_value and "audible" in status_value:
        ownership_hints.append(f"status:{status_value}")
    if ownership_status and "audible" in ownership_status:
        ownership_hints.append(f"ownership_status:{ownership_status}")

    tag_hints = tags.intersection(AUDIBLE_OWNERSHIP_TAG_HINTS)
    hints = ownership_hints + list(tag_hints)

    if not purchase_date:
        details["hints"] = sorted(hints) if hints else []
        details["reason"] = "Audible entry missing purchase date confirmation."
        logger.debug(
            "Ownership validation failed: no purchase date recorded for ASIN %s",
            entry.get("asin") or entry.get("ASIN"),
        )
        return False, details

    if ownership_status.startswith("audible") or "audible" in (metadata_source or "") or "audible" in status_value:
        details["hints"] = sorted(hints) if hints else ["books"]
        details["reason"] = "Verified via library book record."
        logger.debug("Ownership validation accepted for ASIN %s", entry.get("asin") or entry.get("ASIN"))
        return True, details

    details["hints"] = sorted(hints) if hints else ["audible_library"]
    details["reason"] = "Verified via Audible library record."
    logger.debug("Ownership validation accepted for ASIN %s", entry.get("asin") or entry.get("ASIN"))
    return True, details


def fetch_audible_library_entry(database_service: Any, asin: Optional[str]) -> Optional[Dict[str, Any]]:
    """Safely retrieve a library record for the given ASIN.

    Prefers the canonical ``books`` table and falls back to the legacy
    ``audible_library`` helper if available.
    """
    if not asin or not database_service:
        return None

    book_entry: Optional[Dict[str, Any]] = None
    library_entry: Optional[Dict[str, Any]] = None

    # Prefer consolidated books table records
    if hasattr(database_service, "get_book_by_asin"):
        try:
            raw_book_entry = database_service.get_book_by_asin(asin)
            if raw_book_entry:
                book_entry = dict(raw_book_entry)
                book_entry.setdefault("_source_table", "books")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to fetch book record for ASIN %s: %s", asin, exc)

    # Fall back to legacy audible_library operations when present
    audible_accessor = getattr(database_service, "audible_library", None)
    if audible_accessor:
        try:
            raw_library_entry = audible_accessor.get_book_by_asin(asin)
            if raw_library_entry:
                library_entry = dict(raw_library_entry)
                library_entry.setdefault("_source_table", "audible_library")
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.debug("Failed to fetch audible library entry for ASIN %s: %s", asin, exc)

    merged = merge_audible_records(book_entry, library_entry)
    if merged and book_entry and library_entry:
        merged.setdefault("_merged_from", "books,audible_library")
    return merged
