"""
Module Name: matcher.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Provide AudioBookShelf search and match helpers for post-import pipelines.
Location:
    /services/audiobookshelf/matcher.py

"""

import time
from typing import Any, Dict, Optional, Tuple

import requests
from utils.logger import get_module_logger


class AudioBookShelfMatcher:
    """Encapsulates search + match operations against AudioBookShelf."""

    def __init__(self, connection, logger=None):
        self.connection = connection
        self.logger = logger or get_module_logger("Service.AudioBookShelf.Matcher")

    def match_imported_item(
        self,
        asin: str,
        title: Optional[str] = None,
        library_id: Optional[str] = None,
        delay_seconds: int = 60,
        timeout: float = 15.0,
    ) -> Tuple[bool, str]:
        """Search for a library item and force-match Audible metadata.

        The call optionally sleeps before searching to allow ABS to finish its
        own scan.
        """

        asin_normalized = (asin or "").strip()
        if not asin_normalized:
            return False, "ASIN is required for ABS matching"

        if not self.connection.ensure_authenticated():
            return False, "AudioBookShelf authentication failed"

        base_url = self.connection.get_base_url()
        if not base_url:
            return False, "AudioBookShelf base URL is not configured"

        target_library = (library_id or "").strip() or self.connection.get_config().get("abs_library_id", "")
        if not target_library:
            return False, "AudioBookShelf library_id is not configured"

        if delay_seconds and delay_seconds > 0:
            time.sleep(delay_seconds)

        try:
            session = self.connection.session
            item = self._search_library(
                session=session,
                base_url=base_url,
                library_id=target_library,
                query=(title or asin_normalized),
                asin_match=asin_normalized,
                timeout=timeout,
            )
            search_source = "library search"

            if not item:
                item = self._search_by_asin(
                    session=session,
                    base_url=base_url,
                    library_id=target_library,
                    asin=asin_normalized,
                    timeout=timeout,
                )
                search_source = "asin fallback"

            if not item:
                return False, "No matching library item found in ABS"

            library_item_id = item.get("id")
            if not library_item_id:
                return False, "Matched item is missing an id"

            self._match_item(
                session=session,
                base_url=base_url,
                library_item_id=library_item_id,
                asin=asin_normalized,
                timeout=timeout,
            )

            self.logger.info(
                "ABS auto-match succeeded",
                extra={
                    "libraryItemId": library_item_id,
                    "asin": asin_normalized,
                    "search_source": search_source,
                },
            )
            return True, f"Matched libraryItemId={library_item_id} via {search_source}"
        except requests.HTTPError as err:
            resp = err.response
            status = resp.status_code if resp is not None else "?"
            text = resp.text if resp is not None else str(err)
            self.logger.warning(
                "ABS auto-match failed",
                extra={"status": status, "response": text},
            )
            return False, f"HTTP {status}: {text}"
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error("ABS auto-match error", extra={"error": str(exc)})
            return False, str(exc)

    def _search_library(
        self,
        session: requests.Session,
        base_url: str,
        library_id: str,
        query: str,
        asin_match: Optional[str],
        timeout: float,
        limit: int = 5,
    ) -> Optional[Dict[str, Any]]:
        url = f"{base_url}/libraries/{library_id}/search"
        params = {"q": query, "limit": limit}
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("book") or []
        if not items:
            return None

        for item in items:
            li = item.get("libraryItem")
            if not li:
                continue
            metadata = li.get("media", {}).get("metadata", {})
            if asin_match and metadata.get("asin") == asin_match:
                return li
        return items[0].get("libraryItem") if items else None

    def _search_by_asin(
        self,
        session: requests.Session,
        base_url: str,
        library_id: str,
        asin: str,
        timeout: float,
        limit: int = 5,
    ) -> Optional[Dict[str, Any]]:
        url = f"{base_url}/libraries/{library_id}/search"
        params = {"q": asin, "limit": limit}
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("book") or []
        if not items:
            return None

        for item in items:
            li = item.get("libraryItem")
            if not li:
                continue
            metadata = li.get("media", {}).get("metadata", {})
            if metadata.get("asin") == asin:
                return li
        return items[0].get("libraryItem") if items else None

    def _match_item(
        self,
        session: requests.Session,
        base_url: str,
        library_item_id: str,
        asin: str,
        timeout: float,
    ) -> None:
        url = f"{base_url}/items/{library_item_id}/match"
        payload = {"provider": "audible", "asin": asin, "overrideDefaults": True}
        resp = session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()