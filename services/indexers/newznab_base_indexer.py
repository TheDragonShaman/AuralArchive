"""
Module Name: newznab_base_indexer.py
Author: TheDragonShaman
Created: Feb 18 2026
Description:
    Protocol base for all Newznab indexers (Prowlarr NZB endpoint, NZBHydra2).
    Owns all Newznab XML parsing, capabilities parsing, and NZB result
    normalisation. Subclasses are responsible only for computing the API
    endpoint URL.

Location:
    /services/indexers/newznab_base_indexer.py

"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests

from .base_indexer import BaseIndexer
from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Indexers.Newznab")

NEWZNAB_NS = {"newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"}

# How long a persisted capabilities cache entry is considered fresh (seconds).
_CAPS_CACHE_TTL = 7 * 24 * 3600  # 7 days


@dataclass
class NewznabItem:
    """Normalised representation of a single Newznab feed item."""

    title: str
    download_url: str
    info_url: str
    publish_date: str
    size_bytes: int
    category: str
    guid: str
    attributes: Dict[str, str] = field(default_factory=dict)


class NewznabBaseIndexer(BaseIndexer):
    """
    Protocol base for Newznab indexers.

    Implements the full Newznab search/caps/result pipeline.
    Subclasses must compute the Newznab API endpoint URL and pass it as
    `api_endpoint` to this constructor.

    Example subclass::

        class NzbHydra2Indexer(NewznabBaseIndexer):
            def __init__(self, config, *, logger=None):
                config = dict(config)
                api_endpoint = f"{config['base_url']}/api"
                super().__init__(config, api_endpoint, logger=logger)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        api_endpoint: str,
        *,
        logger=None,
    ):
        config = dict(config)
        config["protocol"] = "newznab"
        self.api_endpoint = api_endpoint.rstrip("/")
        super().__init__(config, logger=logger or _LOGGER)
        # Attempt to warm the in-memory capabilities from the on-disk cache
        # before any network call is made.  This is a best-effort load; any
        # I/O errors are silently ignored so startup is never blocked.
        if not self.capabilities:
            cached = self._load_caps_cache()
            if cached:
                self.capabilities = cached
                self.logger.debug(
                    "Loaded capabilities from disk cache",
                    extra={"indexer_name": self.name},
                )
        self.logger.debug(
            "Newznab indexer ready",
            extra={"indexer_name": self.name, "endpoint": self.api_endpoint},
        )

    # ------------------------------------------------------------------
    # BaseIndexer interface
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            return self.test_connection().get("success", False)
        except Exception as exc:
            self.mark_failure(f"Connection failed: {exc}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        try:
            response = self._request({"t": "caps"})
            root = ET.fromstring(response.content)
            capabilities = self._parse_capabilities(root)
            self.capabilities = capabilities
            self.mark_success()
            # Persist fresh caps to disk so they survive restarts.
            self._save_caps_cache(capabilities)
        except requests.exceptions.Timeout:
            error = f"Connection timeout after {self.timeout}s"
            self.mark_failure(error)
            return {"success": False, "error": error}
        except requests.exceptions.ConnectionError as exc:
            error = f"Connection error: {exc}"
            self.mark_failure(error)
            return {"success": False, "error": error}
        except ET.ParseError as exc:
            error = f"Invalid XML response: {exc}"
            self.mark_failure(error)
            return {"success": False, "error": error}
        except Exception as exc:
            error = f"Unexpected error: {exc}"
            self.mark_failure(error)
            return {"success": False, "error": error}

        # Caps passed — run a real (minimal) search to verify the search endpoint
        # also works.  Failures here are reported but do not make the connection
        # appear broken, because caps alone are enough for indexer operation.
        search_warning = self._probe_search_endpoint()

        result: Dict[str, Any] = {
            "success": True,
            "capabilities": capabilities,
            "version": "Newznab",
        }
        if search_warning:
            result["search_warning"] = search_warning
        return result

    def _probe_search_endpoint(self) -> Optional[str]:
        """
        Fire a minimal search request (t=search q=audiobook limit=1) to verify
        that the server handles real queries, not just capability fetches.

        Returns a warning string if the probe fails, or None on success.
        This is intentionally non-fatal: caps are sufficient for indexer
        operation; a failed probe is a yellow flag, not a red one.
        """
        try:
            response = self._request({"t": "search", "q": "audiobook", "limit": 1})
            root = ET.fromstring(response.content)
            # A valid Newznab response must contain an RSS channel element.
            channel = root.find("channel")
            if channel is None:
                return "Search probe returned XML with no <channel> element"
            self.logger.debug(
                "Newznab search probe succeeded",
                extra={"indexer_name": self.name},
            )
            return None
        except requests.exceptions.Timeout:
            return f"Search probe timed out after {self.timeout}s"
        except requests.exceptions.ConnectionError as exc:
            return f"Search probe connection error: {exc}"
        except ET.ParseError as exc:
            return f"Search probe returned invalid XML: {exc}"
        except PermissionError:
            return "Search probe rejected (API key may lack search permission)"
        except Exception as exc:
            return f"Search probe failed: {exc}"

    def search(
        self,
        query: str,
        author: Optional[str] = None,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self.is_available():
            self.logger.warning(
                "Newznab indexer unavailable, skipping search",
                extra={"indexer_name": self.name},
            )
            return []

        query = query or ""
        cleaned_query = self._clean_query(query)
        caps = self.capabilities or self.get_capabilities()
        supports_book = caps.get("book_search_available", False)

        params = self._base_params("search")
        if author or title:
            if supports_book:
                params = self._base_params("book")
                if author:
                    params["author"] = author.strip()
                if title:
                    params["title"] = title.strip()
                params["q"] = cleaned_query or query
            else:
                combined = " ".join(p for p in [title, author, query] if p)
                params["q"] = self._clean_query(combined) or combined
        else:
            params["q"] = cleaned_query or query

        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset

        try:
            response = self._request(params)
            root = ET.fromstring(response.content)
            parsed_items = [i for i in self._parse_items(root) if i.download_url]
            results = [self._build_result(i) for i in parsed_items]
            self.mark_success()
            self.logger.debug(
                "Newznab search complete",
                extra={"indexer_name": self.name, "result_count": len(results)},
            )
            return results
        except requests.exceptions.Timeout:
            self.mark_failure(f"Search timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as exc:
            self.mark_failure(f"Connection error during search: {exc}")
        except ET.ParseError as exc:
            self.mark_failure(f"Invalid XML response: {exc}")
        except Exception as exc:
            self.mark_failure(f"Unexpected search error: {exc}")
            self.logger.exception(
                "Error searching Newznab indexer",
                extra={"indexer_name": self.name},
            )
        return []

    def get_capabilities(self) -> Dict[str, Any]:
        if self.capabilities:
            return self.capabilities
        return self.test_connection().get("capabilities", {})

    # ------------------------------------------------------------------
    # Capabilities persistence helpers
    # ------------------------------------------------------------------

    def _caps_cache_path(self) -> Optional[str]:
        """Return the filesystem path for this indexer's capabilities cache file."""
        try:
            from utils.path_resolver import get_path_resolver
            cache_root = get_path_resolver().get_cache_dir()
            caps_dir = os.path.join(cache_root, "indexer_caps")
            os.makedirs(caps_dir, exist_ok=True)
            # Use a stable hash of the endpoint so the file name is always safe
            # regardless of special characters in the indexer name or URL.
            key = f"{self.name}:{self.api_endpoint}"
            safe_key = hashlib.sha1(key.encode()).hexdigest()[:16]
            return os.path.join(caps_dir, f"{safe_key}.json")
        except Exception:
            return None

    def _load_caps_cache(self) -> Optional[Dict[str, Any]]:
        """Load cached capabilities from disk if the entry is still fresh."""
        path = self._caps_cache_path()
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            saved_at = float(data.get("_saved_at", 0))
            if time.time() - saved_at > _CAPS_CACHE_TTL:
                self.logger.debug(
                    "Capabilities cache expired for %s; will re-fetch",
                    self.name,
                )
                return None
            caps = data.get("capabilities")
            return caps if isinstance(caps, dict) else None
        except Exception as exc:
            self.logger.debug(
                "Failed to read capabilities cache for %s: %s", self.name, exc
            )
            return None

    def _save_caps_cache(self, capabilities: Dict[str, Any]) -> None:
        """Persist capabilities to disk with a timestamp for TTL checks."""
        path = self._caps_cache_path()
        if not path:
            return
        try:
            data = {"_saved_at": time.time(), "capabilities": capabilities}
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except Exception as exc:
            self.logger.debug(
                "Failed to write capabilities cache for %s: %s", self.name, exc
            )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(self, params: Dict[str, Any]) -> requests.Response:
        response = requests.get(
            self.api_endpoint,
            params=self._inject_auth(params),
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        if response.status_code == 403:
            raise PermissionError("Invalid API key")
        if response.status_code == 404:
            raise FileNotFoundError(
                f"Newznab endpoint not found: {self.api_endpoint}"
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code}: {response.text[:160]}"
            )
        return response

    def _inject_auth(self, params: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(params)
        merged.setdefault("apikey", self.api_key)
        if merged.get("t") in {"search", "book"} and self.categories:
            merged.setdefault("cat", ",".join(self.categories))
        return merged

    def _base_params(self, search_type: str) -> Dict[str, Any]:
        return {"t": search_type}

    # ------------------------------------------------------------------
    # XML parsing
    # ------------------------------------------------------------------

    def _parse_items(self, root: ET.Element) -> List[NewznabItem]:
        items: List[NewznabItem] = []
        for element in root.findall(".//item"):
            try:
                parsed = self._parse_single_item(element)
                if parsed:
                    items.append(parsed)
            except Exception as exc:
                self.logger.debug(
                    "Skipping malformed Newznab item: %s", exc, exc_info=True
                )
        return items

    def _parse_single_item(self, element: ET.Element) -> Optional[NewznabItem]:
        title = self._get_text(element, "title", "")
        info_url = self._get_text(element, "link", "")
        guid = self._get_text(element, "guid", "")
        publish_date = self._normalize_date(self._get_text(element, "pubDate", ""))
        attrs = self._extract_attributes(element)

        # NZB download URL comes from the enclosure element
        download_url = self._select_nzb_url(element)
        if not download_url:
            self.logger.debug(
                "Skipping item — no NZB enclosure URL found",
                extra={"title": title},
            )
            return None

        # Size from enclosure or newznab:attr
        size_bytes = 0
        enclosure = element.find("enclosure")
        if enclosure is not None:
            size_bytes = self._safe_int(enclosure.get("length", 0))
        if not size_bytes:
            size_bytes = self._safe_int(attrs.get("size", 0))

        category = attrs.get("category", self.CATEGORY_AUDIOBOOK)

        return NewznabItem(
            title=title,
            download_url=download_url,
            info_url=info_url,
            publish_date=publish_date,
            size_bytes=size_bytes,
            category=category,
            guid=guid,
            attributes=attrs,
        )

    def _parse_capabilities(self, root: ET.Element) -> Dict[str, Any]:
        caps: Dict[str, Any] = {
            "search_available": False,
            "book_search_available": False,
            "author_search_available": False,
            "categories": [],
            "limits": {},
        }

        searching = root.find(".//searching")
        if searching is not None:
            for child in list(searching):
                available = child.get("available", "no").lower() == "yes"
                tag = child.tag.lower()
                if tag == "search":
                    caps["search_available"] = available
                elif tag == "book-search":
                    caps["book_search_available"] = available
                elif tag == "audio-search":
                    # Some Newznab indexers report audio-search instead of book-search
                    caps["book_search_available"] = available

        for category in root.findall(".//category"):
            cat_id = category.get("id") or ""
            cat_name = category.get("name") or "Unknown"
            caps["categories"].append({"id": cat_id, "name": cat_name})
            for subcat in category.findall(".//subcat"):
                caps["categories"].append(
                    {
                        "id": subcat.get("id") or "",
                        "name": subcat.get("name") or "Unknown",
                    }
                )

        limits = root.find(".//limits")
        if limits is not None:
            caps["limits"] = {
                "max": self._safe_int(limits.get("max", 100), default=100),
                "default": self._safe_int(limits.get("default", 100), default=100),
            }

        return caps

    # ------------------------------------------------------------------
    # NZB URL selection
    # ------------------------------------------------------------------

    def _select_nzb_url(self, element: ET.Element) -> Optional[str]:
        """Extract the NZB download URL from the enclosure element."""
        enclosure = element.find("enclosure")
        if enclosure is not None:
            url = enclosure.get("url") or ""
            content_type = (enclosure.get("type") or "").lower()
            if self._is_nzb_url(url, content_type):
                return url
        # Fallback: some indexers put the NZB URL in <link>
        fallback = self._get_text(element, "link", "")
        return fallback if self._is_nzb_url(fallback, "") else None

    def _is_nzb_url(self, url: str, content_type: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        if "nzb" in content_type or "x-nzb" in content_type:
            return True
        # Newznab download URLs often contain /getnzb/ or end with &i=...&r=...
        if "/getnzb/" in url or "get=" in url:
            return True
        from urllib.parse import urlparse
        path = (urlparse(url).path or "").lower()
        return path.endswith(".nzb")

    def _rewrite_download_url(self, url: str) -> str:
        """
        If the indexer returns a download URL with a localhost/loopback host,
        rewrite it to use the configured base_url's host and port so that
        AuralArchive can actually fetch it.
        """
        if not url:
            return url
        try:
            parsed = urlparse(url)
            if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                return url
            configured_base = self.config.get("base_url", "").rstrip("/")
            if not configured_base:
                return url
            base_parsed = urlparse(configured_base)
            rewritten = urlunparse((
                base_parsed.scheme or parsed.scheme,
                base_parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
            self.logger.debug(
                "Rewrote localhost download URL to configured base",
                extra={"original": url, "rewritten": rewritten},
            )
            return rewritten
        except Exception:
            return url

    # ------------------------------------------------------------------
    # Result shaping
    # ------------------------------------------------------------------

    def _build_result(self, item: NewznabItem) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "indexer": self.name,
            "title": item.title,
            "download_url": self._rewrite_download_url(item.download_url),
            "size": item.size_bytes,
            "size_bytes": item.size_bytes,
            "publish_date": item.publish_date,
            "protocol": "nzb",
            "result_type": "nzb",
            "indexer_id": item.guid,
            "category": item.category,
            "info_url": item.info_url,
            # NZB-specific fields (no seeders/peers)
            "seeders": -1,
            "peers": -1,
        }

        format_info = self._extract_format(item.title)
        media = self._extract_media_details(item.attributes)

        if media.get("format"):
            format_info["format"] = media.pop("format")
        if media.get("bitrate"):
            format_info["bitrate"] = media.pop("bitrate")

        result["format"] = format_info.get("format", "unknown")
        result["bitrate"] = format_info.get("bitrate", 0)

        author = media.pop("author", None) or self._extract_author(item.title)
        if author:
            result["author"] = author
        for field_name in ("narrator", "language", "series", "sequence"):
            if media.get(field_name):
                result[field_name] = media.pop(field_name)

        if item.attributes:
            result["raw_attributes"] = item.attributes

        return result

    def _extract_media_details(self, attrs: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Extract known media fields from newznab:attr elements."""
        media: Dict[str, Any] = {}
        if not attrs:
            return media

        normalized = {str(k).lower(): v for k, v in attrs.items() if v is not None}

        def grab(*keys: str) -> Optional[str]:
            for key in keys:
                if normalized.get(key):
                    return normalized[key]
            return None

        bitrate = grab("bitrate", "audio:bitrate", "bitratekbps")
        if bitrate:
            media["bitrate"] = self._safe_int(bitrate, 0)
        codec = grab("codec", "format", "audioformat")
        if codec:
            media["format"] = codec.lower()
        author = grab("author", "bookauthor", "writer")
        if author:
            media["author"] = author
        narrator = grab("narrator", "reader")
        if narrator:
            media["narrator"] = narrator
        language = grab("language", "lang")
        if language:
            media["language"] = language
        series = grab("series", "bookseries")
        if series:
            media["series"] = series
        sequence = grab("booknumber", "booknum", "seriesnumber", "volume")
        if sequence:
            media["sequence"] = sequence

        return media

    # ------------------------------------------------------------------
    # Attribute extraction
    # ------------------------------------------------------------------

    def _extract_attributes(self, element: ET.Element) -> Dict[str, str]:
        return {
            attr.get("name"): attr.get("value")
            for attr in element.findall("newznab:attr", NEWZNAB_NS)
            if attr.get("name") and attr.get("value") is not None
        }

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_text(self, parent: ET.Element, tag: str, default: str) -> str:
        child = parent.find(tag)
        return child.text.strip() if (child is not None and child.text) else default

    def _normalize_date(self, value: str) -> str:
        if not value:
            return ""
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(value).isoformat()
        except Exception:
            return value

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clean_query(self, query: str) -> str:
        if not query:
            return ""
        cleaned = re.sub(r"[^\w\s-]", " ", query.replace("'", ""))
        stopwords = {
            "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "up", "out", "if", "about", "as", "into",
            "through", "over", "after", "before", "a", "an", "am", "is",
            "im", "its", "it",
        }
        filtered = [
            w for w in cleaned.split()
            if len(w) > 2 and w.lower() not in stopwords
        ]
        return " ".join(filtered).strip()

    def _extract_format(self, title: str) -> Dict[str, Any]:
        format_patterns = [
            r"\[([Mm]4[Bb])\]", r"\[([Mm]4[Aa])\]", r"\[([Mm][Pp]3)\]",
            r"\[([Ff][Ll][Aa][Cc])\]", r"\[([Aa][Aa][Cc])\]",
            r"\(([Mm]4[Bb])\)", r"\(([Mm]4[Aa])\)", r"\(([Mm][Pp]3)\)",
            r"\b([Mm]4[Bb])\b", r"\b([Mm]4[Aa])\b", r"\b([Mm][Pp]3)\b",
        ]
        bitrate_patterns = [
            r"[\[\(]?(\d+)\s*[Kk][Bb][Pp][Ss][\]\)]?",
            r"[\[\(]?(\d+)\s*[Kk][Bb]/[Ss][\]\)]?",
        ]
        result = {"format": "unknown", "bitrate": 0}
        for pattern in format_patterns:
            m = re.search(pattern, title)
            if m:
                result["format"] = m.group(1).lower()
                break
        for pattern in bitrate_patterns:
            m = re.search(pattern, title)
            if m:
                try:
                    result["bitrate"] = int(m.group(1))
                except ValueError:
                    pass
                break
        return result

    def _extract_author(self, title: str) -> Optional[str]:
        dash = re.search(r"\s+-\s+([A-Z][A-Za-z\s\.,&]+?)\s*[\[(]", title)
        if dash:
            candidate = dash.group(1).strip()
            blocked = {
                "progression", "fantasy", "litrpg", "epic", "series",
                "book", "volume", "vol", "audiobook", "unabridged",
            }
            if len(candidate) < 50 and not any(
                w in candidate.lower() for w in blocked
            ):
                return candidate
        by = re.search(
            r"\s+by\s+([A-Z][a-zA-Z\s\.]+?)(?:\s+[\[(]|$)", title, re.IGNORECASE
        )
        return by.group(1).strip() if by else None
