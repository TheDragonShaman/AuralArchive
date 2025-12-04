"""Generic JSON direct provider adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .base import DirectProviderAdapter, ProviderRequestSpec
from . import register_provider


@register_provider
class GenericJSONAdapter(DirectProviderAdapter):
    """Default adapter that expects simple JSON payloads."""

    key = "generic"

    def build_search_request(
        self,
        query: str,
        author: str,
        title: str,
        limit: int,
        offset: int,
    ) -> ProviderRequestSpec:
        params: Dict[str, Any] = {
            "q": query.strip(),
            "title": title.strip(),
            "author": author.strip(),
            "limit": max(1, min(limit, 200)),
            "offset": max(0, offset),
            "session_id": self.session_id,
        }
        return ProviderRequestSpec(path=self.search_path, params=params)

    def parse_search_results(self, payload: Any) -> Sequence[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for entry in results:
            parsed = self._normalize_result(entry)
            if parsed:
                normalized.append(parsed)
        return normalized

    def _normalize_result(self, entry: Any) -> Dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None

        download_url = entry.get("download_url") or entry.get("url") or entry.get("link")
        if not download_url:
            return None

        size_bytes = self._safe_int(entry.get("size_bytes") or entry.get("size") or entry.get("filesize"), default=0)
        publish_date = entry.get("publish_date") or entry.get("published") or entry.get("time")

        return {
            "indexer": self.indexer_name,
            "title": entry.get("title") or entry.get("name") or "Unknown",
            "author": entry.get("author"),
            "narrator": entry.get("narrator"),
            "series": entry.get("series"),
            "sequence": entry.get("sequence") or entry.get("series_index"),
            "language": entry.get("language"),
            "format": entry.get("format") or entry.get("extension"),
            "bitrate": self._safe_int(entry.get("bitrate"), default=0),
            "size": size_bytes,
            "size_bytes": size_bytes,
            "seeders": self._safe_int(entry.get("seeders"), default=-1),
            "peers": self._safe_int(entry.get("peers"), default=-1),
            "protocol": "direct",
            "indexer_id": str(entry.get("id") or entry.get("guid") or entry.get("hash") or ""),
            "category": entry.get("category") or "direct",
            "publish_date": publish_date,
            "download_url": download_url,
            "info_url": entry.get("info_url") or entry.get("details") or entry.get("detail_url"),
            "_source": "direct-generic",
        }
