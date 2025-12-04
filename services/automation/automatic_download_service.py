"""Automatic Download Service
=============================

Background coordinator that watches the library for books marked as
"Wanted" and feeds them into the download management pipeline. The
service keeps queue additions in sync with configuration toggles and
respects an upper bound on active search operations (enforced inside the
DownloadManagementService).
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger import get_module_logger


class AutomaticDownloadService:
    """Singleton service that orchestrates automatic download scheduling."""

    _instance: Optional["AutomaticDownloadService"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = get_module_logger("AutomaticDownloadService")
                    self._database_service = None
                    self._download_service = None
                    self._config_service = None

                    self._thread: Optional[threading.Thread] = None
                    self._stop_event = threading.Event()
                    self._state_lock = threading.Lock()

                    self.running = False
                    self.paused = False
                    self.last_run: Optional[datetime] = None
                    self.last_error: Optional[str] = None

                    self._queue_snapshot: List[Dict[str, Any]] = []
                    self._skip_book_ids: List[int] = []

                    self.config: Dict[str, Any] = {
                        "auto_download_enabled": False,
                        "quality_threshold": 5,
                        "scan_interval_seconds": 60,
                        "max_batch_size": 2,
                    }

                    self.metrics: Dict[str, Any] = {
                        "total_books_queued": 0,
                        "last_book_queued": None,
                        "last_queue_time": None,
                    }

                    self._load_configuration()
                    AutomaticDownloadService._initialized = True

    # ------------------------------------------------------------------
    # Lazy-loaded service dependencies
    # ------------------------------------------------------------------
    def _get_database_service(self):
        if self._database_service is None:
            from services.service_manager import get_database_service

            self._database_service = get_database_service()
        return self._database_service

    def _get_download_service(self):
        if self._download_service is None:
            from services.service_manager import get_download_management_service

            self._download_service = get_download_management_service()
        return self._download_service

    def _get_config_service(self):
        if self._config_service is None:
            from services.service_manager import get_config_service

            self._config_service = get_config_service()
        return self._config_service

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> bool:
        with self._state_lock:
            if self.running:
                self.logger.debug("Automatic download service already running")
                return True

            self._stop_event.clear()
            self.running = True
            self.paused = False
            self._thread = threading.Thread(
                target=self._run_loop,
                name="AutomaticDownloadService",
                daemon=True,
            )
            self._thread.start()
            self.logger.info("Automatic download service started")
            return True

    def stop(self) -> bool:
        with self._state_lock:
            if not self.running:
                self.logger.debug("Automatic download service already stopped")
                return True

            self._stop_event.set()
            self.running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self.logger.info("Automatic download service stopped")
        return True

    def pause(self) -> bool:
        with self._state_lock:
            if self.paused:
                return True
            self.paused = True
            self.logger.info("Automatic download service paused")
        return True

    def resume(self) -> bool:
        with self._state_lock:
            if not self.paused:
                return True
            self.paused = False
            self.logger.info("Automatic download service resumed")
        return True

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _load_configuration(self):
        try:
            config_service = self._get_config_service()
            auto_section = config_service.get_section("auto_search") or {}

            def _coerce_bool(value, default=False):
                if isinstance(value, bool):
                    return value
                if value is None:
                    return default
                return str(value).strip().lower() in {"true", "1", "yes", "on"}

            def _coerce_int(value, default):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            self.config["auto_download_enabled"] = _coerce_bool(
                auto_section.get("auto_download_enabled"), False
            )
            self.config["quality_threshold"] = _coerce_int(
                auto_section.get("quality_threshold"), 5
            )
            self.config["scan_interval_seconds"] = max(
                30, _coerce_int(auto_section.get("scan_interval_seconds"), 120)
            )
            self.config["max_batch_size"] = max(
                1, _coerce_int(auto_section.get("max_batch_size"), 2)
            )

            raw_skip_list = (auto_section.get("skip_book_ids") or "").strip()
            skip_ids: List[int] = []
            if raw_skip_list:
                for token in raw_skip_list.split(','):
                    token_clean = token.strip()
                    if not token_clean:
                        continue
                    try:
                        skip_ids.append(int(token_clean))
                    except ValueError:
                        self.logger.debug("Skipping invalid skip_book_id token: %s", token_clean)
            self._skip_book_ids = skip_ids

        except Exception as exc:
            self.logger.error("Failed to load automatic search configuration: %s", exc)
            self.last_error = str(exc)

    def update_configuration(self, updates: Dict[str, Any]) -> bool:
        config_service = self._get_config_service()
        payload = {}
        for key, value in updates.items():
            payload[f"auto_search.{key}"] = value
        if payload:
            result = config_service.update_multiple_config(payload)
            if result:
                self._load_configuration()
            return result
        return True

    def _persist_skip_book_ids(self):
        skip_value = ",".join(str(book_id) for book_id in sorted(set(self._skip_book_ids)))
        self._get_config_service().update_multiple_config({
            "auto_search.skip_book_ids": skip_value
        })
        self.logger.debug("Persisted %s skipped book IDs", len(self._skip_book_ids))

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------
    def _run_loop(self):
        try:
            while not self._stop_event.is_set():
                self.last_run = datetime.utcnow()
                self._load_configuration()

                if not self.config.get("auto_download_enabled"):
                    self.logger.debug("Automatic downloads disabled; sleeping")
                    self._wait_interval()
                    continue

                if self.paused:
                    self.logger.debug("Automatic downloads paused; sleeping")
                    self._wait_interval()
                    continue

                try:
                    pending_books = self._collect_candidate_books(limit=250)
                    self._queue_snapshot = pending_books

                    if not pending_books:
                        self.logger.debug("No eligible 'Wanted' books found this cycle")
                    else:
                        queued = self._queue_books(pending_books)
                        if queued:
                            self.logger.info("Queued %s books for automatic download", queued)
                except Exception as exc:
                    self.last_error = str(exc)
                    self.logger.error("Automatic search cycle failed: %s", exc, exc_info=True)

                self._wait_interval()
        finally:
            self.running = False

    def _wait_interval(self):
        interval = self.config.get("scan_interval_seconds", 120)
        self._stop_event.wait(interval)

    # ------------------------------------------------------------------
    # Candidate discovery & queue orchestration
    # ------------------------------------------------------------------
    def _collect_candidate_books(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        db_service = self._get_database_service()
        download_service = self._get_download_service()

        wanted_books = db_service.get_books_by_status("Wanted")
        candidates: List[Dict[str, Any]] = []

        for book in wanted_books:
            if limit is not None and len(candidates) >= limit:
                break

            book_id = book.get("ID") or book.get("id")
            asin = book.get("ASIN") or book.get("asin")

            if not book_id or not asin or asin == "N/A":
                continue

            if book_id in self._skip_book_ids:
                continue

            existing = download_service.queue_manager.get_active_download_by_asin(asin)
            if existing:
                continue

            if self._is_future_release(book):
                continue

            candidates.append(
                {
                    "id": int(book_id),
                    "asin": asin,
                    "title": book.get("Title") or book.get("title") or "Unknown Title",
                    "author": book.get("Author") or book.get("author") or "Unknown Author",
                }
            )

        return candidates

    def _queue_books(self, pending_books: List[Dict[str, Any]], max_batch: Optional[int] = None) -> int:
        batch_limit = max_batch if max_batch is not None else self.config.get("max_batch_size", 2)
        download_service = self._get_download_service()

        queued = 0
        for book in pending_books[:batch_limit]:
            if self._stop_event.is_set():
                break

            result = download_service.add_to_queue(
                book_asin=book["asin"],
                search_result_id=None,
                priority=5,
                title=book["title"],
                author=book["author"],
                download_type="torrent",
            )

            if result.get("success"):
                queued += 1
                self.metrics["total_books_queued"] += 1
                self.metrics["last_book_queued"] = book["asin"]
                self.metrics["last_queue_time"] = datetime.utcnow().isoformat()
                # Remove from snapshot so UI reflects remaining backlog immediately
                try:
                    self._queue_snapshot.remove(book)
                except ValueError:
                    pass
            else:
                self.logger.warning(
                    "Failed to queue book %s (%s): %s",
                    book.get("title"),
                    book.get("asin"),
                    result.get("message"),
                )

        return queued

    def _queue_single_book(self, book_id: int) -> Dict[str, Any]:
        db_service = self._get_database_service()
        download_service = self._get_download_service()

        book = db_service.get_book_by_id(book_id)
        if not book:
            return {"success": False, "error": f"Book {book_id} not found"}

        asin = book.get("ASIN") or book.get("asin")
        if not asin or asin == "N/A":
            return {"success": False, "error": "Book is missing a valid ASIN"}

        existing = download_service.queue_manager.get_active_download_by_asin(asin)
        if existing:
            return {
                "success": False,
                "error": "Book already has an active download in the queue",
                "download_id": existing.get("id"),
            }

        if self._is_future_release(book):
            return {"success": False, "error": "Book release date is in the future"}

        result = download_service.add_to_queue(
            book_asin=asin,
            search_result_id=None,
            priority=5,
            title=book.get("Title", "Unknown Title"),
            author=book.get("Author", "Unknown Author"),
            download_type="torrent",
        )

        if result.get("success"):
            if book_id in self._skip_book_ids:
                self._skip_book_ids.remove(book_id)
                self._persist_skip_book_ids()
            self.metrics["total_books_queued"] += 1
            self.metrics["last_book_queued"] = asin
            self.metrics["last_queue_time"] = datetime.utcnow().isoformat()

        return result

    # ------------------------------------------------------------------
    # Release-date helpers
    # ------------------------------------------------------------------
    def _is_future_release(self, book: Dict[str, Any]) -> bool:
        raw_value = (
            book.get("Release Date")
            or book.get("release_date")
            or book.get("releaseDate")
        )

        if not raw_value:
            return False

        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
        else:
            cleaned = str(raw_value).strip()

        if not cleaned or cleaned.lower() in {"unknown", "n/a", "tbd", "none"}:
            return False

        parsed = self._parse_release_date(cleaned)
        if parsed is not None:
            return parsed.date() > datetime.utcnow().date()

        release_year = self._extract_year(cleaned)
        if release_year is None:
            return False
        return release_year > datetime.utcnow().year

    @staticmethod
    def _parse_release_date(date_str: str) -> Optional[datetime]:
        normalized = date_str.strip()
        if not normalized:
            return None

        iso_candidate = normalized
        if normalized.endswith("Z"):
            iso_candidate = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(iso_candidate)
        except ValueError:
            pass

        date_formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _extract_year(date_str: str) -> Optional[int]:
        match = re.search(r"\b(19|20)\d{2}\b", date_str)
        if match:
            try:
                return int(match.group())
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    # Public control surface (used by API/UI)
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        pending = len(self._queue_snapshot)
        return {
            "running": self.running,
            "paused": self.paused,
            "auto_enabled": self.config.get("auto_download_enabled", False),
            "queue_size": pending,
            "scan_interval": self.config.get("scan_interval_seconds", 120),
            "max_batch_size": self.config.get("max_batch_size", 2),
            "metrics": self.metrics,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_error": self.last_error,
        }

    def get_search_queue(self) -> List[Dict[str, Any]]:
        pending_books = self._collect_candidate_books(limit=250)
        self._queue_snapshot = pending_books
        return pending_books

    def clear_queue(self) -> Dict[str, Any]:
        pending_books = self._collect_candidate_books(limit=None)
        skipped = 0
        for book in pending_books:
            book_id = book.get("id")
            if book_id is None:
                continue
            if book_id not in self._skip_book_ids:
                self._skip_book_ids.append(book_id)
                skipped += 1
        if skipped:
            self._persist_skip_book_ids()
        return {
            "success": True,
            "skipped": skipped,
            "message": "Current automatic queue cleared",
        }

    def remove_from_queue(self, book_id: int) -> Dict[str, Any]:
        if book_id not in self._skip_book_ids:
            self._skip_book_ids.append(book_id)
            self._persist_skip_book_ids()
        return {
            "success": True,
            "message": f"Book {book_id} excluded from automatic downloads",
        }

    def force_search_all(self) -> Dict[str, Any]:
        self._skip_book_ids = []
        self._persist_skip_book_ids()
        pending_books = self._collect_candidate_books(limit=None)
        queued = self._queue_books(pending_books, max_batch=len(pending_books))
        return {
            "success": True,
            "queued": queued,
            "message": "Force search triggered for all pending books",
        }

    def force_search_book(self, book_id: int) -> Dict[str, Any]:
        if book_id in self._skip_book_ids:
            self._skip_book_ids.remove(book_id)
            self._persist_skip_book_ids()
        result = self._queue_single_book(book_id)
        result.setdefault("success", result.get("error") is None)
        return result
