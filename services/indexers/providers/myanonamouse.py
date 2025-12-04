"""MyAnonamouse provider adapter."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence
from urllib.parse import urljoin

import logging
from .base import DirectProviderAdapter, ProviderRequestSpec
from . import register_provider


@register_provider
class MyAnonamouseAdapter(DirectProviderAdapter):
    """Adapter that speaks the MyAnonamouse JSON search API."""

    key = "myanonamouse"
    domains = ("myanonamouse.net",)
    SEARCH_PATH = "/tor/js/loadSearchJSONbasic.php"

    AUDIO_FILETYPES = {"m4b", "mp3", "flac", "aac", "ogg", "m4a", "wav"}
    EBOOK_FILETYPES = {"epub", "pdf", "mobi", "azw", "azw3", "cbz", "cbr"}

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Always force the well-known AJAX endpoint regardless of generic defaults
        self.search_path = self.SEARCH_PATH
        self.health_path = self.SEARCH_PATH
        self._raw_category_values = self._as_list(config.get("categories"))
        self._request_categories = self._compute_request_categories()
        self._explicit_all_categories = any(value == "0" for value in self._raw_category_values)
        self._include_all_categories = self._explicit_all_categories or not self._request_categories
        if self._include_all_categories:
            self._request_categories = []
        self._allowed_main_categories = self._compute_allowed_main_categories()

    def build_health_request(self) -> ProviderRequestSpec:
        return self.build_search_request("healthcheck", "", "", limit=1, offset=0)

    def build_search_request(
        self,
        query: str,
        author: str,
        title: str,
        limit: int,
        offset: int,
    ) -> ProviderRequestSpec:
        search_parts: List[str] = []
        if title:
            search_parts.append(title)
        if author:
            search_parts.append(author)
        if not search_parts and query:
            search_parts.append(query)

        search_focus = " ".join(part.strip() for part in search_parts if part).strip()
        clean_query = self._sanitize_query(search_focus)
        text_query = clean_query or "*"

        params: List[tuple[str, str]] = []
        params.append(("tor[text]", text_query))
        params.append(("tor[searchType]", self._resolve_search_type()))
        params.append(("tor[searchIn]", "torrents"))
        params.append(("tor[sortType]", "default"))
        params.append(("tor[perpage]", str(self._clamp(limit, 5, 1000))))
        params.append(("tor[startNumber]", str(max(0, offset))))
        params.append(("tor[browseStart]", "true"))
        params.append(("tor[browseFlagsHideVsShow]", "0"))
        params.append(("thumbnails", "1"))
        params.append(("description", "1"))
        params.append(("mediaInfo", "set"))
        params.append(("dlLink", ""))

        for field, enabled in self._search_in_flags().items():
            params.append((f"tor[srchIn][{field}]", "true" if enabled else "false"))

        categories = self._request_categories
        if not self._include_all_categories and categories:
            for idx, cat in enumerate(categories):
                params.append((f"tor[cat][{idx}]", cat))
        else:
            params.append(("tor[cat][0]", "0"))

        languages = self._resolve_languages()
        if languages:
            for idx, lang in enumerate(languages):
                params.append((f"tor[browse_lang][{idx}]", lang))

        return ProviderRequestSpec(
            method="GET",
            path=self.SEARCH_PATH,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    def parse_search_results(self, payload: Any) -> Sequence[Dict[str, Any]]:
        adapter_logger = logging.getLogger("Indexer.MyAnonamouseAdapter")
        if not isinstance(payload, dict):
            adapter_logger.debug("parse_search_results: payload not a dict (type=%s)", type(payload))
            return []
        entries = payload.get("data")
        if not isinstance(entries, list):
            adapter_logger.debug("parse_search_results: 'data' missing or not a list, payload keys=%s", list(payload.keys()))
            return []

        adapter_logger.debug("parse_search_results: raw entries count=%d", len(entries))
        titles = []
        results: List[Dict[str, Any]] = []
        for entry in entries:
            # attempt to capture title-like fields for debug
            t = entry.get("title") or entry.get("name") or entry.get("torrent_name")
            if t:
                titles.append(str(t))
            parsed = self._normalize_entry(entry)
            if parsed:
                results.append(parsed)

        # Log what we kept vs raw
        adapter_logger.debug("parse_search_results: parsed_count=%d kept_count=%d sample_titles=%s", len(entries), len(results), titles[:6])
        return results

    def parse_health_response(self, payload: Any) -> Dict[str, Any]:
        return {
            "capabilities": {
                "search_available": True,
                "book_search_available": True,
                "author_search_available": True,
                "categories": [
                    {"id": "13", "name": "Audiobooks"},
                    {"id": "14", "name": "E-Books"},
                ],
                "limits": {"max": 1000, "default": 50},
            },
            "version": "MyAnonamouse"
        }

    def _normalize_entry(self, entry: Any) -> Dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None

        torrent_id = entry.get("id") or entry.get("tid") or entry.get("torrent_id")
        if not torrent_id:
            return None

        adapter_logger = logging.getLogger("Indexer.MyAnonamouseAdapter")

        entry_main_cat = self._resolve_entry_main_cat(entry)
        # If adapter has an explicit allowed main category list, respect it
        if self._allowed_main_categories and (
            not entry_main_cat or entry_main_cat not in self._allowed_main_categories
        ):
            adapter_logger.debug("Dropping entry %s: main_cat '%s' not allowed", torrent_id, entry_main_cat)
            return None

        # -----------------------------
        # Audio-only filtering (conservative)
        # -----------------------------
        # Prefer explicit filetype when present
        filetype = str(entry.get("filetype") or "").lower()
        title_text = str(entry.get("title") or "").lower()
        tags_text = str(entry.get("tags") or "").lower()

        # If the provider explicitly labels this as an eBook filetype, drop it
        if filetype:
            if filetype in self.EBOOK_FILETYPES:
                adapter_logger.debug("Dropping entry %s: filetype '%s' is non-audio", torrent_id, filetype)
                return None
            # If it's an audio filetype, accept immediately
            if filetype in self.AUDIO_FILETYPES:
                pass
            else:
                # Unknown filetype - fall back to category/mediatype heuristics below
                pass

        # mediatype (1 = audio, 2 = ebook) is a strong indicator when present
        mediatype = entry.get("mediatype")
        if mediatype in (2, "2"):
            adapter_logger.debug("Dropping entry %s: mediatype indicates ebook (%s)", torrent_id, mediatype)
            return None

        if entry_main_cat:
            # main category '14' is e-books per adapter mapping
            if str(entry_main_cat) == "14":
                adapter_logger.debug("Dropping entry %s: main_cat == 14 (ebook)", torrent_id)
                return None

        # Heuristic title/tags checks for eBook indicators
        ebook_indicators = ("ebook", "epub", "pdf", "mobi", "azw", "azw3", "ebookcollection", "e-book")
        if any(term in title_text for term in ebook_indicators) or any(term in tags_text for term in ebook_indicators):
            adapter_logger.debug("Dropping entry %s: title/tags indicate ebook ('%s' / '%s')", torrent_id, title_text[:120], tags_text[:120])
            return None


        download_url = urljoin(f"{self.base_url}/", f"tor/download.php?tid={torrent_id}")

        size_bytes = self._parse_size(entry.get("size") or entry.get("size_bytes"))
        author_values = self._extract_people_list(entry.get("author_info"))
        narrator_values = self._extract_people_list(entry.get("narrator_info"))
        series_name, series_sequence = self._extract_series(entry.get("series_info"))

        return {
            "indexer": self.indexer_name,
            "title": entry.get("title") or entry.get("name") or "Unknown",
            "author": ", ".join(author_values) if author_values else None,
            "narrator": ", ".join(narrator_values) if narrator_values else None,
            "series": series_name,
            "sequence": series_sequence,
            "language": entry.get("lang_code"),
            "format": entry.get("filetype"),
            "bitrate": 0,
            "size": size_bytes,
            "size_bytes": size_bytes,
            "seeders": self._safe_int(entry.get("seeders"), default=-1),
            "peers": self._safe_int(entry.get("leechers"), default=-1),
            "protocol": "torrent",
            "indexer_id": str(entry.get("id")),
            "category": entry.get("category") or entry.get("main_cat") or "13",
            "publish_date": entry.get("added"),
            "download_url": download_url,
            "info_url": urljoin(f"{self.base_url}/", f"t/{torrent_id}") if torrent_id else None,
            "_source": "direct-myanonamouse",
        }

    @staticmethod
    def _extract_people_list(blob: Any) -> List[str]:
        if not blob:
            return []
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                return [value for value in parsed.values() if value]
        except json.JSONDecodeError:
            return []
        return []

    @staticmethod
    def _extract_series(blob: Any) -> tuple[str | None, str | None]:
        if not blob:
            return (None, None)
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                for value in parsed.values():
                    if isinstance(value, list) and value:
                        name = value[0]
                        sequence = value[1] if len(value) > 1 else None
                        return name, sequence
        except json.JSONDecodeError:
            return (None, None)
        return (None, None)

    @staticmethod
    def _sanitize_query(value: str) -> str:
        if not value:
            return ""
        return re.sub(r"[^\w]+", " ", value).strip()

    def _compute_request_categories(self) -> List[str]:
        tracker_values: List[str] = []
        for entry in self._raw_category_values:
            entry = entry.strip()
            if not entry or entry == "0":
                continue
            try:
                num = int(entry)
            except ValueError:
                continue
            if 0 < num < 1000:
                tracker_values.append(str(num))

        if not tracker_values:
            return []

        seen = set()
        unique_values: List[str] = []
        for value in tracker_values:
            if value not in seen:
                seen.add(value)
                unique_values.append(value)
        return unique_values

    def _compute_allowed_main_categories(self) -> List[str]:
        if self._explicit_all_categories:
            return []

        if not self._raw_category_values:
            return ["13"]

        mapped: List[str] = []
        for entry in self._raw_category_values:
            entry = entry.strip()
            if not entry or entry == "0":
                continue
            mapped_value = self._map_category_to_main(entry)
            if mapped_value:
                mapped.append(mapped_value)

        if mapped:
            return sorted(set(mapped))

        # No torznab/main-cat hints were provided; default to audiobooks.
        return ["13"]

    @staticmethod
    def _map_category_to_main(value: str) -> str | None:
        try:
            num = int(value)
        except ValueError:
            return None

        if num >= 3000 and num < 4000:
            return "13"  # Torznab audio buckets
        if num >= 7000 and num < 8000:
            return "14"  # Torznab ebook buckets
        if num in (13, 14):
            return str(num)
        return None

    def _resolve_entry_main_cat(self, entry: Dict[str, Any]) -> str | None:
        for key in ("main_cat", "maincat", "mainCategory"):
            value = entry.get(key)
            if value is not None:
                return str(value)

        mediatype = entry.get("mediatype")
        if mediatype in (1, "1"):
            return "13"
        if mediatype in (2, "2"):
            return "14"

        filetype = str(entry.get("filetype") or "").lower()
        if filetype in self.AUDIO_FILETYPES:
            return "13"
        if filetype in self.EBOOK_FILETYPES:
            return "14"
        return None

    def _resolve_languages(self) -> List[str]:
        raw = self._as_list(self.config.get("languages"))
        return [value for value in raw if value]

    @staticmethod
    def _search_in_flags() -> Dict[str, bool]:
        return {
            "title": True,
            "author": True,
            "narrator": True,
            "series": True,
            "description": True,
            "filenames": True,
        }

    def _resolve_search_type(self) -> str:
        raw = (self.config.get("search_type") or "all").strip().lower()
        valid = {
            "all",
            "active",
            "inactive",
            "fl",
            "fl-vip",
            "vip",
            "nvip",
            "nmeta",
        }
        return raw if raw in valid else "all"

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            numeric = minimum
        return max(minimum, min(numeric, maximum))

    @staticmethod
    def _parse_size(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)

        text = str(value).strip()
        if not text:
            return 0

        try:
            return int(text)
        except ValueError:
            pass

        match = re.match(r"(?P<num>[\d]+(?:\.\d+)?)\s*(?P<unit>[A-Za-z]+)", text)
        if not match:
            return 0

        number = float(match.group("num"))
        unit = match.group("unit").lower()
        multipliers = {
            "b": 1,
            "bytes": 1,
            "kb": 1024,
            "kib": 1024,
            "mb": 1024 ** 2,
            "mib": 1024 ** 2,
            "gb": 1024 ** 3,
            "gib": 1024 ** 3,
            "tb": 1024 ** 4,
            "tib": 1024 ** 4,
        }

        multiplier = multipliers.get(unit, 1)
        return int(number * multiplier)
