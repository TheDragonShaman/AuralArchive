"""
Jackett Indexer Implementation
==============================

Torznab wrapper that only returns direct .torrent download URLs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse
import xml.etree.ElementTree as ET

import requests

from .base_indexer import BaseIndexer
from utils.logger import get_module_logger

logger = get_module_logger("Indexer.Jackett")

TORZNAB_NS = {"torznab": "http://torznab.com/schemas/2015/feed"}


@dataclass
class ParsedItem:
    """Normalized Torznab search item."""

    title: str
    download_url: str
    info_url: str
    publish_date: str
    size_bytes: int
    seeders: int
    peers: int
    category: str
    guid: str
    attributes: Dict[str, str]


class JackettIndexer(BaseIndexer):
    """Jackett indexer that filters out magnet links entirely."""

    def __init__(self, config: Dict[str, Any]):
        config = dict(config)
        config["protocol"] = "torznab"

        feed_url = config.get("feed_url")
        if feed_url:
            self.api_endpoint = feed_url.rstrip("/")
            parts = self.api_endpoint.split("/api/")
            config["base_url"] = parts[0] if parts else self.api_endpoint
            try:
                self.indexer_id = self.api_endpoint.split("/indexers/")[1].split("/")[0]
            except (IndexError, AttributeError):
                self.indexer_id = "all"
        else:
            config["base_url"] = config.get("base_url", "http://172.18.0.1:9117").rstrip("/")
            self.indexer_id = config.get("indexer_id", "all")
            self.api_endpoint = (
                f"{config['base_url']}/api/v2.0/indexers/{self.indexer_id}/results/torznab"
            )

        super().__init__(config)
        logger.debug("Jackett indexer initialized: %s", self.api_endpoint)

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
            return {
                "success": True,
                "capabilities": capabilities,
                "version": "Jackett (Torznab)",
                "indexer_id": self.indexer_id,
            }
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

    def search(
        self,
        query: str,
        author: Optional[str] = None,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self.is_available():
            logger.warning("%s is unavailable, skipping search", self.name)
            return []

        query = query or ""
        cleaned_query = self._clean_query(query)
        caps = self.capabilities or self.get_capabilities()
        supports_book = caps.get("book_search_available", False)

        params = self._base_params("search")
        if author or title:
            if supports_book:
                params = self._base_params("book")
                combined = cleaned_query or query
            else:
                combined = " ".join(part for part in [title, author, query] if part)
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
            parsed_items = [item for item in self._parse_items(root) if item.download_url]
            results = [self._build_result(item) for item in parsed_items]
            self.mark_success()
            logger.debug("%s returned %d torrent results", self.name, len(results))
            return results
        except requests.exceptions.Timeout:
            self.mark_failure(f"Search timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as exc:
            self.mark_failure(f"Connection error during search: {exc}")
        except ET.ParseError as exc:
            self.mark_failure(f"Invalid XML response: {exc}")
        except Exception as exc:
            self.mark_failure(f"Unexpected search error: {exc}")
            logger.exception("Error searching %s", self.name)

        return []

    def get_capabilities(self) -> Dict[str, Any]:
        if self.capabilities:
            return self.capabilities
        result = self.test_connection()
        return result.get("capabilities", {})

    def _request(self, params: Dict[str, Any]) -> requests.Response:
        final_params = self._inject_auth(params)
        response = requests.get(
            self.api_endpoint,
            params=final_params,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        if response.status_code == 403:
            raise PermissionError("Invalid API key")
        if response.status_code == 404:
            raise FileNotFoundError(f"Indexer ID '{self.indexer_id}' not found")
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

    def _parse_items(self, root: ET.Element) -> List[ParsedItem]:
        items: List[ParsedItem] = []
        for element in root.findall(".//item"):
            try:
                parsed = self._parse_single_item(element)
                if parsed:
                    items.append(parsed)
            except Exception as exc:
                logger.debug("Skipping malformed Torznab item: %s", exc, exc_info=True)
        return items

    def _parse_single_item(self, element: ET.Element) -> Optional[ParsedItem]:
        title = self._get_text(element, "title", "")
        info_url = self._get_text(element, "comments", "")
        guid = self._get_text(element, "guid", "")
        publish_date = self._normalize_date(self._get_text(element, "pubDate", ""))
        size_bytes = self._safe_int(self._get_text(element, "size", "0"))

        attrs = self._extract_attributes(element)

        download_url = self._select_torrent_url(element)
        if not download_url:
            info_hash = attrs.get("infohash")
            if info_hash:
                magnet = self._build_magnet_from_attributes(info_hash, attrs, title)
                if magnet:
                    download_url = magnet
        if not download_url:
            logger.debug("Skipping %s - no .torrent URL present", title)
            return None
        seeders = self._safe_int(attrs.get("seeders", -1), default=-1)
        peers = self._safe_int(attrs.get("peers", -1), default=-1)
        category = attrs.get("category", self.CATEGORY_AUDIOBOOK)

        return ParsedItem(
            title=title,
            download_url=download_url,
            info_url=info_url,
            publish_date=publish_date,
            size_bytes=size_bytes,
            seeders=seeders,
            peers=peers,
            category=category,
            guid=guid,
            attributes=attrs,
        )

    def _build_magnet_from_attributes(
        self,
        info_hash: str,
        attrs: Dict[str, str],
        title: str,
    ) -> Optional[str]:
        info_hash = info_hash.strip()
        if not info_hash:
            return None

        trackers: List[str] = []
        raw_trackers = attrs.get("tracker") or attrs.get("trackers")
        if raw_trackers:
            separators = ['|', ',', ';']
            tokens = [raw_trackers]
            for sep in separators:
                tokens = [sub_token for token in tokens for sub_token in token.split(sep)]
            trackers.extend(t.strip() for t in tokens if t.strip())

        if not trackers:
            trackers = [
                "udp://tracker.opentrackr.org:1337/announce",
                "udp://tracker.torrent.eu.org:451/announce",
                "udp://tracker.openbittorrent.com:6969/announce",
                "udp://exodus.desync.com:6969/announce",
                "udp://tracker.dler.org:6969/announce",
                "udp://tracker.moeking.me:6969/announce",
            ]

        display_name = (
            attrs.get("dn")
            or attrs.get("title")
            or title
        )

        parts = [f"magnet:?xt=urn:btih:{info_hash.lower()}"]
        for tracker in trackers:
            encoded = quote(tracker, safe=':/?&=')
            parts.append(f"tr={encoded}")
        if display_name:
            parts.append(f"dn={quote(display_name)}")

        return "&".join(parts)

    def _select_torrent_url(self, element: ET.Element) -> Optional[str]:
        enclosure = element.find("enclosure")
        if enclosure is not None:
            url = enclosure.get("url") or ""
            content_type = (enclosure.get("type") or "").lower()
            if self._is_torrent_url(url, content_type):
                return url

        fallback = self._get_text(element, "link", "")
        if self._is_torrent_url(fallback, ""):
            return fallback
        return None

    def _is_torrent_url(self, url: str, content_type: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        if "bittorrent" in content_type:
            return True

        parsed = urlparse(url)
        path = parsed.path or ""
        if path.lower().endswith(".torrent"):
            return True

        query_params = parse_qs(parsed.query)
        filename_params = query_params.get("file") or query_params.get("filename")
        return bool(
            filename_params
            and any(name.lower().endswith(".torrent") for name in filename_params)
        )

    def _extract_attributes(self, element: ET.Element) -> Dict[str, str]:
        attrs: Dict[str, str] = {}
        for attr in element.findall("torznab:attr", TORZNAB_NS):
            name = attr.get("name")
            value = attr.get("value")
            if name and value is not None:
                attrs[name] = value
        return attrs

    def _parse_capabilities(self, root: ET.Element) -> Dict[str, Any]:
        caps = {
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
                elif tag == "author-search":
                    caps["author_search_available"] = available

        for category in root.findall(".//category"):
            cat_id = category.get("id") or ""
            cat_name = category.get("name") or "Unknown"
            caps["categories"].append({"id": cat_id, "name": cat_name})
            for subcat in category.findall(".//subcat"):
                sub_id = subcat.get("id") or ""
                sub_name = subcat.get("name") or "Unknown"
                caps["categories"].append({"id": sub_id, "name": sub_name})

        limits = root.find(".//limits")
        if limits is not None:
            caps["limits"] = {
                "max": self._safe_int(limits.get("max", 100), default=100),
                "default": self._safe_int(limits.get("default", 100), default=100),
            }

        return caps

    def _build_result(self, item: ParsedItem) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "indexer": self.name,
            "title": item.title,
            "download_url": item.download_url,
            "size": item.size_bytes,
            "size_bytes": item.size_bytes,
            "publish_date": item.publish_date,
            "seeders": item.seeders,
            "peers": item.peers,
            "protocol": "torrent",
            "indexer_id": item.guid,
            "category": item.category,
            "info_url": item.info_url,
        }

        format_info = self._extract_format(item.title)
        media_primary, media_extras = self._extract_media_details(item.attributes)

        if media_primary.get("format"):
            format_info["format"] = media_primary.pop("format")
        if media_primary.get("bitrate"):
            format_info["bitrate"] = media_primary.pop("bitrate")

        result["format"] = format_info.get("format", "unknown")
        result["bitrate"] = format_info.get("bitrate", 0)

        author = (
            media_primary.pop("author", None)
            or self._extract_author(item.title)
        )
        if author:
            result["author"] = author

        if media_primary.get("narrator"):
            result["narrator"] = media_primary.pop("narrator")
        if media_primary.get("language"):
            result["language"] = media_primary.pop("language")
        if media_primary.get("series"):
            result["series"] = media_primary.pop("series")
        if media_primary.get("sequence"):
            result["sequence"] = media_primary.pop("sequence")

        if media_extras:
            result["media_info"] = media_extras

        if item.attributes:
            result["raw_attributes"] = item.attributes

        return result

    def _extract_media_details(self, attrs: Optional[Dict[str, str]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return (primary_fields, extra_media_info) from torznab attributes."""
        primary: Dict[str, Any] = {}
        extras: Dict[str, Any] = {}
        if not attrs:
            return primary, extras

        normalized = {str(k).lower(): v for k, v in attrs.items() if v is not None}

        def grab(*keys: str) -> Optional[str]:
            for key in keys:
                if key in normalized and normalized[key]:
                    return normalized[key]
            return None

        bitrate = grab("bitrate", "audio:bitrate", "bitratekbps", "audio_bitrate")
        if bitrate:
            primary["bitrate"] = self._safe_int(bitrate, 0)

        codec = grab("codec", "format", "audioformat", "encoding")
        if codec:
            primary["format"] = codec.lower()

        author = grab("author", "bookauthor", "writer")
        if author:
            primary["author"] = author

        narrator = grab("narrator", "reader")
        if narrator:
            primary["narrator"] = narrator

        language = grab("language", "lang")
        if language:
            primary["language"] = language

        series = grab("series", "bookseries")
        if series:
            primary["series"] = series

        sequence = grab(
            "booknumber",
            "booknum",
            "seriesnumber",
            "volume",
            "issue",
            "sequence",
        )
        if sequence:
            primary["sequence"] = sequence

        channels = grab("channels", "audio:channels")
        if channels:
            extras["channels"] = channels

        samplerate = grab("samplerate", "sample_rate")
        if samplerate:
            extras["sample_rate"] = samplerate

        runtime = grab("duration", "runtime", "length")
        if runtime:
            extras["runtime"] = runtime

        quality = grab("quality", "releasequality")
        if quality:
            extras["quality"] = quality

        return primary, extras

    def _base_params(self, search_type: str) -> Dict[str, Any]:
        return {"t": search_type}

    def _get_text(self, parent: ET.Element, tag: str, default: str) -> str:
        child = parent.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return default

    def _normalize_date(self, value: str) -> str:
        if not value:
            return ""
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
            return dt.isoformat()
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
        cleaned = query.replace("'", "")
        cleaned = re.sub(r"[^\w\s-]", " ", cleaned)
        words = cleaned.split()
        stopwords = {
            "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "up", "out", "if", "about", "as", "into",
            "through", "over", "after", "before", "a", "an", "am", "is",
            "im", "its", "it",
        }
        filtered = [word for word in words if len(word) > 2 and word.lower() not in stopwords]
        return " ".join(filtered).strip()

    def _extract_format(self, title: str) -> Dict[str, Any]:
        format_patterns = [
            r"\[([Mm]4[Bb])\]", r"\[([Mm]4[Aa])\]", r"\[([Mm][Pp]3)\]",
            r"\[([Ff][Ll][Aa][Cc])\]", r"\[([Aa][Aa][Cc])\]", r"\[([Oo][Gg][Gg])\]",
            r"\(([Mm]4[Bb])\)", r"\(([Mm]4[Aa])\)", r"\(([Mm][Pp]3)\)",
            r"\b([Mm]4[Bb])\b", r"\b([Mm]4[Aa])\b", r"\b([Mm][Pp]3)\b",
        ]
        bitrate_patterns = [
            r"[\[\(]?(\d+)\s*[Kk][Bb][Pp][Ss][\]\)]?",
            r"[\[\(]?(\d+)\s*[Kk][Bb]/[Ss][\]\)]?",
        ]
        result = {"format": "unknown", "bitrate": 0}
        for pattern in format_patterns:
            match = re.search(pattern, title)
            if match:
                result["format"] = match.group(1).lower()
                break
        for pattern in bitrate_patterns:
            match = re.search(pattern, title)
            if match:
                try:
                    result["bitrate"] = int(match.group(1))
                except ValueError:
                    pass
                break
        return result

    def _extract_author(self, title: str) -> Optional[str]:
        dash_pattern = re.search(r"\s+-\s+([A-Z][A-Za-z\s\.,&]+?)\s*[\[(]", title)
        if dash_pattern:
            candidate = dash_pattern.group(1).strip()
            blocked = {
                "progression", "fantasy", "litrpg", "epic", "series",
                "book", "volume", "vol", "audiobook", "unabridged",
            }
            if len(candidate) < 50 and not any(word in candidate.lower() for word in blocked):
                return candidate
        by_pattern = re.search(r"\s+by\s+([A-Z][a-zA-Z\s\.]+?)(?:\s+[\[(]|$)", title, re.IGNORECASE)
        if by_pattern:
            return by_pattern.group(1).strip()
        return None
