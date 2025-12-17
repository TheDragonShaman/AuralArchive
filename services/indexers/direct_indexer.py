"""Direct Indexer Implementation
================================

Lightweight indexer that queries custom provider APIs using a session token
(typically a cookie or bearer token) instead of a Torznab feed.

The provider is expected to expose JSON endpoints with the following defaults:

- ``GET /api/direct/search``: accepts ``q`` (query), ``title``, ``author``, and
  ``limit`` query parameters and returns ``{"success": true, "results": [...]}``
- ``GET /api/direct/health``: optional health-check endpoint that returns
  ``{"success": true}``

Both endpoints must accept the configured session ID via either the
``Authorization: Bearer <session_id>`` header, ``X-Session-ID`` header, or one of
the standard cookies (``session``, ``session_id``, ``mam_id``). Providers that
use a different route naming convention can override the defaults by adding
``search_path`` or ``health_path`` keys to the indexer's configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from .base_indexer import BaseIndexer
from .providers import ProviderRequestSpec, resolve_provider_adapter
from utils.search_normalization import normalize_search_terms

logger = logging.getLogger("Indexer.Direct")


class DirectIndexer(BaseIndexer):
    """Indexer that communicates with custom direct provider APIs."""

    DEFAULT_SEARCH_PATH = "/api/direct/search"
    DEFAULT_HEALTH_PATH = "/api/direct/health"

    def __init__(self, config: Dict[str, Any]):
        cfg = dict(config)
        cfg.setdefault("protocol", "direct")

        if not cfg.get("base_url"):
            raise ValueError("Direct indexer requires a base_url")
        if not cfg.get("session_id"):
            raise ValueError("Direct indexer requires a session_id")

        self.session_id = cfg.get("session_id", "").strip()
        self.search_path = cfg.get("search_path", self.DEFAULT_SEARCH_PATH)
        self.health_path = cfg.get("health_path", self.DEFAULT_HEALTH_PATH)

        cfg["session_id"] = self.session_id
        cfg["search_path"] = self.search_path
        cfg["health_path"] = self.health_path
        cfg["base_url"] = cfg.get("base_url")

        super().__init__(cfg)
        self.adapter = resolve_provider_adapter(self.base_url, cfg)

    def connect(self) -> bool:
        """Attempt to connect to the provider by running the health check."""
        try:
            return self.test_connection().get("success", False)
        except Exception as exc:  # pragma: no cover - defensive
            self.mark_failure(f"Connection failed: {exc}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Ping the provider to ensure authentication works."""
        try:
            spec = self.adapter.build_health_request()
            payload = self._perform_request(spec) if spec else {}
            health = self.adapter.parse_health_response(payload)
            self.capabilities = health.get("capabilities", {
                "search_available": True,
                "book_search_available": True,
                "author_search_available": True,
                "categories": [{"id": "direct", "name": "Direct Provider"}],
                "limits": {"max": 100, "default": 50}
            })
            self.mark_success()
            return {
                "success": True,
                "capabilities": self.capabilities,
                "version": health.get("version", self.name),
            }
        except requests.exceptions.Timeout:
            error = f"Connection timeout after {self.timeout}s"
            self.mark_failure(error)
            return {"success": False, "error": error}
        except PermissionError as exc:
            error = f"Authorization failed: {exc}"
            self.mark_failure(error)
            return {"success": False, "error": error}
        except Exception as exc:  # pragma: no cover - defensive
            error = f"Direct provider health check failed: {exc}"
            logger.exception(error)
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
            logger.warning("%s is unavailable, skipping direct search", self.name)
            return []

        normalized_query = self._compose_focus_query(query, title, author)
        logger.debug("DirectIndexer.search called with query='%s' title='%s' author='%s' -> normalized='%s'",
                 query, title, author, normalized_query)

        params: Dict[str, Any] = {
            "q": normalized_query,
            "title": (title or "").strip(),
            "author": (author or "").strip(),
            "limit": max(1, min(limit or 100, 200)),
            "offset": max(0, offset or 0),
            "session_id": self.session_id,
        }

        try:
            spec = self.adapter.build_search_request(
                params.get("q", ""),
                params.get("author", ""),
                params.get("title", ""),
                params.get("limit", 100),
                params.get("offset", 0)
            )
            logger.debug("DirectIndexer: provider request spec params=%s headers=%s path=%s",
                         spec.params, getattr(spec, 'headers', None), getattr(spec, 'path', None))
            payload = self._perform_request(spec)
            normalized = list(self.adapter.parse_search_results(payload))
            self.mark_success()
            logger.debug("%s (direct) returned %d results", self.name, len(normalized))
            return normalized
        except PermissionError as exc:
            self.mark_failure(f"Authorization failed: {exc}")
        except requests.exceptions.Timeout:
            self.mark_failure(f"Direct search timeout after {self.timeout}s")
        except Exception as exc:  # pragma: no cover - defensive
            self.mark_failure(f"Unexpected direct search error: {exc}")
            logger.exception("Error searching direct provider %s", self.name)
        return []

    def get_capabilities(self) -> Dict[str, Any]:
        if self.capabilities:
            return self.capabilities
        result = self.test_connection()
        return result.get("capabilities", {})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_url(self, path: str) -> str:
        if not path:
            return self.base_url
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip('/'))

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.session_id}",
            "X-Session-ID": self.session_id,
            "User-Agent": "AuralArchive-DirectIndexer/1.0",
            "Accept": "application/json",
        }

    def _build_cookies(self) -> Dict[str, str]:
        return {
            "session": self.session_id,
            "session_id": self.session_id,
            "mam_id": self.session_id,
        }

    def _compose_focus_query(
        self,
        query: Optional[str],
        title: Optional[str],
        author: Optional[str],
    ) -> str:
        fallback = (query or "").strip()
        normalized_query, normalized_title, normalized_author = normalize_search_terms(
            fallback or title,
            title,
            author,
        )
        focus = normalized_query or " ".join(
            part for part in (normalized_title, normalized_author) if part
        ).strip()
        return focus or fallback

    def _perform_request(self, spec: ProviderRequestSpec) -> Optional[Dict[str, Any]]:
        if spec is None:
            return {}

        method = (spec.method or "GET").upper()
        url = self._build_url(spec.path or self.search_path)
        headers = self._build_headers()
        if spec.headers:
            headers.update(spec.headers)
        cookies = self._build_cookies()

        response = requests.request(
            method,
            url,
            params=spec.params,
            data=spec.data,
            json=spec.json,
            headers=headers,
            cookies=cookies,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )

        if spec.allow_missing and response.status_code == 404:
            return None
        if response.status_code == 401:
            raise PermissionError("Direct provider rejected the session ID")
        if response.status_code >= 400:
            raise RuntimeError(f"Direct provider error {response.status_code}: {response.text[:160]}")

        if not response.content:
            return {}

        expects_json = getattr(spec, "expects_json", True)

        if not expects_json:
            return response.text

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Direct provider returned invalid JSON: {exc}") from exc