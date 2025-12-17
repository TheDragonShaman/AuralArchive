"""
Download Management Service
===========================

Main singleton service coordinating complete download workflow:
QUEUED → SEARCHING → FOUND → DOWNLOADING → COMPLETE → 
(Audible) CONVERTING → CONVERTED → IMPORTING → IMPORTED
(Torrent/NZB) IMPORTING → IMPORTED

Features:
- ASIN-based tracking with uniqueness enforcement
- Automatic pipeline progression
- Smart conversion detection (Audible only)
- Seeding support for torrent clients
- Configurable retry logic
- Real-time progress monitoring

Download Clients:
- Currently supported: qBittorrent (torrents/magnets)
- Coming soon: Deluge, Transmission
"""

import asyncio
import threading
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import requests

from utils.logger import get_module_logger
from services.audible.ownership_validator import (
    assess_audible_ownership,
    fetch_audible_library_entry,
    merge_audible_records,
)

logger = get_module_logger("DownloadManagementService")


class DownloadManagementService:
    """
    Main download management service following DatabaseService singleton pattern.
    
    Coordinates:
    - Queue management and prioritization
    - State machine transitions
    - Download monitoring (2-second polling)
    - Client selection and coordination
    - Conversion and import triggering
    - Cleanup and seeding management
    """
    
    _instance: Optional['DownloadManagementService'] = None
    _lock = threading.Lock()
    _initialized = False
    CLEARABLE_STATUSES: List[str] = [
        'QUEUED', 'SEARCHING', 'FOUND', 'DOWNLOADING', 'AUDIBLE_DOWNLOADING',
        'AUDIBLE_DOWNLOAD_FAILED', 'DOWNLOAD_COMPLETE', 'COMPLETE', 'CONVERTING',
        'CONVERTED', 'PROCESSING', 'PROCESSED', 'IMPORTING', 'IMPORTED',
        'SEARCH_FAILED', 'DOWNLOAD_FAILED',
        'CONVERSION_FAILED', 'IMPORT_FAILED', 'FAILED', 'PAUSED', 'SEEDING',
        'SEEDING_COMPLETE', 'CANCELLED'
    ]
    
    def __new__(cls):
        """Singleton pattern - only one instance allowed."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize service components (only once)."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    logger.debug("Initializing DownloadManagementService...")
                    
                    # Initialize helper components
                    from .queue_manager import QueueManager
                    from .state_machine import StateMachine
                    from .download_monitor import DownloadMonitor
                    from .client_selector import ClientSelector
                    from .progress_tracker import ProgressTracker
                    from .retry_handler import RetryHandler
                    from .cleanup_manager import CleanupManager
                    from .event_emitter import EventEmitter
                    
                    self.queue_manager = QueueManager()
                    self.state_machine = StateMachine()
                    self.download_monitor = DownloadMonitor()
                    self.client_selector = ClientSelector()
                    self.progress_tracker = ProgressTracker()
                    self.retry_handler = RetryHandler()
                    self.cleanup_manager = CleanupManager()
                    self.event_emitter = EventEmitter()
                    self.event_emitter.attach_lookup(self.queue_manager.get_download)

                    # Track active Audible downloads for cooperative cancellation
                    self._audible_context_lock = threading.Lock()
                    self._audible_download_context: Dict[int, Dict[str, Any]] = {}
                    self._audible_executor_lock = threading.Lock()
                    self._audible_executor: Optional[ThreadPoolExecutor] = None
                    self._audible_max_workers = 1
                    
                    # Service dependencies (lazy loaded)
                    self._database_service = None
                    self._config_service = None
                    self._search_engine_service = None
                    self._conversion_service = None
                    self._import_service = None
                    
                    # Configuration
                    self.polling_interval = 2  # seconds
                    self.monitor_running = False
                    self.monitor_thread = None
                    self._monitor_lock = threading.Lock()
                    self.jackett_download_base_url: Optional[str] = None
                    self.jackett_verify_ssl: bool = True
                    
                    # Download management settings (loaded from config)
                    self.seeding_enabled = False
                    self.delete_source_after_import = False
                    self.temp_download_path = '/tmp/auralarchive/downloads'
                    self.temp_conversion_path = '/tmp/auralarchive/converting'
                    self.torrent_download_root = None
                    self.torrent_download_root_local = None
                    self.torrent_download_root_remote = None
                    self.qbittorrent_path_mappings = []
                    self.max_concurrent_downloads = 2
                    self.retry_limits = {
                        'SEARCH_FAILED': 3,
                        'DOWNLOAD_FAILED': 2,
                        'CONVERSION_FAILED': 1,
                        'IMPORT_FAILED': 2
                    }
                    self.retry_backoff_seconds = 10
                    self.keep_torrent_active = True
                    self.wait_for_seeding_completion = True
                    self.delete_temp_files = True
                    self.retention_days = 7
                    self.auto_start_monitoring = True
                    self.monitor_seeding_enabled = True
                    self.auto_process_queue = True
                    self.queue_priority_default = 5
                    self.max_active_searches = 2
                    self.temp_failed_path = '/tmp/auralarchive/failed'
                    self.direct_provider_sessions: Dict[str, Dict[str, str]] = {}
                    
                    # Initialize service
                    self._initialize_service()
                    
                    DownloadManagementService._initialized = True
                    logger.debug("Download management service ready")
    
    def _initialize_service(self):
        """Initialize the download management service."""
        try:
            # Load configuration from config.txt
            self._load_configuration()
            self._configure_audible_concurrency()
            # Ensure the monitoring loop is running regardless of startup entrypoint
            self._ensure_monitor_running()
            logger.debug("Download management service ready")
        except Exception as e:
            logger.error(f"Error initializing download management service: {e}")
            raise
    
    def _load_configuration(self):
        """Load download management configuration from config.txt"""
        try:
            config_service = self._get_config_service()
            dm_config = config_service.get_section('download_management')
            
            if dm_config:
                def _coerce_bool(value, default):
                    if isinstance(value, bool):
                        return value
                    if value is None:
                        return default
                    return str(value).strip().lower() in {'true', '1', 'yes', 'on'}

                def _coerce_int(value, default):
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return default

                # Seeding and queue behaviour
                self.seeding_enabled = _coerce_bool(dm_config.get('seeding_enabled', self.seeding_enabled), self.seeding_enabled)
                self.keep_torrent_active = _coerce_bool(dm_config.get('keep_torrent_active', self.keep_torrent_active), self.keep_torrent_active)
                self.wait_for_seeding_completion = _coerce_bool(dm_config.get('wait_for_seeding_completion', self.wait_for_seeding_completion), self.wait_for_seeding_completion)
                self.delete_source_after_import = _coerce_bool(dm_config.get('delete_source_after_import', self.delete_source_after_import), self.delete_source_after_import)
                self.delete_temp_files = _coerce_bool(dm_config.get('delete_temp_files', self.delete_temp_files), self.delete_temp_files)
                self.retention_days = _coerce_int(dm_config.get('retention_days', self.retention_days), self.retention_days)
                self.auto_process_queue = _coerce_bool(dm_config.get('auto_process_queue', self.auto_process_queue), self.auto_process_queue)

                # Monitoring configuration
                monitoring_raw = dm_config.get('monitoring_interval', dm_config.get('polling_interval_seconds', self.polling_interval))
                monitoring_value = _coerce_int(monitoring_raw, self.polling_interval)
                self.polling_interval = max(1, monitoring_value)
                self.auto_start_monitoring = _coerce_bool(dm_config.get('auto_start_monitoring', self.auto_start_monitoring), self.auto_start_monitoring)
                self.monitor_seeding_enabled = _coerce_bool(dm_config.get('monitor_seeding', self.monitor_seeding_enabled), self.monitor_seeding_enabled)
                self.max_concurrent_downloads = _coerce_int(dm_config.get('max_concurrent_downloads', self.max_concurrent_downloads), self.max_concurrent_downloads)
                self.queue_priority_default = _coerce_int(dm_config.get('queue_priority_default', self.queue_priority_default), self.queue_priority_default)
                self.max_active_searches = max(1, _coerce_int(dm_config.get('max_active_searches', self.max_active_searches), self.max_active_searches))

                # Paths
                self.temp_download_path = dm_config.get('temp_download_path', self.temp_download_path)
                self.temp_conversion_path = dm_config.get('temp_conversion_path', self.temp_conversion_path)
                self.temp_failed_path = dm_config.get('temp_failed_path', self.temp_failed_path)
                
                # Retry limits
                self.retry_limits = {
                    'SEARCH_FAILED': _coerce_int(dm_config.get('retry_search_max', self.retry_limits.get('SEARCH_FAILED', 3)), self.retry_limits.get('SEARCH_FAILED', 3)),
                    'DOWNLOAD_FAILED': _coerce_int(dm_config.get('retry_download_max', self.retry_limits.get('DOWNLOAD_FAILED', 2)), self.retry_limits.get('DOWNLOAD_FAILED', 2)),
                    'CONVERSION_FAILED': _coerce_int(dm_config.get('retry_conversion_max', self.retry_limits.get('CONVERSION_FAILED', 1)), self.retry_limits.get('CONVERSION_FAILED', 1)),
                    'IMPORT_FAILED': _coerce_int(dm_config.get('retry_import_max', self.retry_limits.get('IMPORT_FAILED', 2)), self.retry_limits.get('IMPORT_FAILED', 2))
                }

                backoff_seconds_value = None
                backoff_seconds_raw = dm_config.get('retry_backoff_seconds')
                if backoff_seconds_raw is not None:
                    try:
                        backoff_seconds_value = int(backoff_seconds_raw)
                    except (TypeError, ValueError):
                        logger.warning(f"Invalid retry_backoff_seconds value: {backoff_seconds_raw}")

                if backoff_seconds_value is None:
                    backoff_minutes_raw = dm_config.get('retry_backoff_minutes')
                    if backoff_minutes_raw is not None:
                        try:
                            minutes_int = int(backoff_minutes_raw)
                            backoff_seconds_value = minutes_int * 60
                        except (TypeError, ValueError):
                            logger.warning(f"Invalid retry_backoff_minutes value: {backoff_minutes_raw}")

                if backoff_seconds_value is None or backoff_seconds_value <= 0:
                    backoff_seconds_value = 10

                self.retry_backoff_seconds = max(10, backoff_seconds_value)
                self.retry_handler.set_retry_backoff(self.retry_backoff_seconds)
                logger.debug(f"Configured download retry backoff: {self.retry_backoff_seconds} seconds")
                
                logger.debug(
                    "Download management configuration loaded: seeding=%s, delete_source=%s, polling_interval=%ss",
                    self.seeding_enabled,
                    self.delete_source_after_import,
                    self.polling_interval
                )
            else:
                logger.warning("No [download_management] section in config - using defaults")

            # Align torrent save path with qBittorrent configuration when provided
            qbittorrent_cfg = {}
            try:
                qbittorrent_cfg = self.client_selector.get_client_config('qbittorrent') or {}
            except Exception as cfg_error:
                logger.warning(f"Unable to load qBittorrent configuration: {cfg_error}")

            self.qbittorrent_path_mappings = qbittorrent_cfg.get('path_mappings') or []

            remote_root_candidate = ''
            local_root_candidate = ''

            if qbittorrent_cfg:
                if self.qbittorrent_path_mappings:
                    remote_root_candidate = self.qbittorrent_path_mappings[0].get('remote', '') or remote_root_candidate
                    local_root_candidate = self.qbittorrent_path_mappings[0].get('local', '') or local_root_candidate

                if not remote_root_candidate:
                    remote_root_candidate = (
                        qbittorrent_cfg.get('download_path_remote')
                        or qbittorrent_cfg.get('download_path')
                        or ''
                    )

                if not local_root_candidate:
                    local_root_candidate = qbittorrent_cfg.get('download_path_local') or ''

            if local_root_candidate:
                local_root_abs = os.path.abspath(local_root_candidate)
                try:
                    os.makedirs(local_root_abs, exist_ok=True)
                    self.torrent_download_root_local = local_root_abs
                    logger.debug(
                        "Configured qBittorrent local save path: %s",
                        self.torrent_download_root_local,
                    )
                except Exception as path_error:
                    logger.warning(
                        "Failed to prepare qBittorrent local save path '%s': %s",
                        local_root_abs,
                        path_error,
                    )

            if not self.torrent_download_root_local and remote_root_candidate:
                mapped_local = self._map_remote_to_local(remote_root_candidate)
                if mapped_local:
                    try:
                        os.makedirs(mapped_local, exist_ok=True)
                        self.torrent_download_root_local = mapped_local
                        logger.debug(
                            "Derived qBittorrent local save path from remote mapping: %s",
                            self.torrent_download_root_local,
                        )
                    except Exception as map_error:
                        logger.warning(
                            "Failed to prepare mapped qBittorrent local save path '%s': %s",
                            mapped_local,
                            map_error,
                        )

            if remote_root_candidate:
                self.torrent_download_root_remote = self._strip_trailing_separators(remote_root_candidate)
                logger.debug(
                    "Configured qBittorrent remote save path: %s",
                    self.torrent_download_root_remote,
                )

            if not self.torrent_download_root_local:
                # Fall back to temp download directory and ensure it exists
                fallback_local = os.path.abspath(self.temp_download_path)
                os.makedirs(fallback_local, exist_ok=True)
                self.torrent_download_root_local = fallback_local
                logger.debug(
                    "Using temporary download directory for torrents: %s",
                    self.torrent_download_root_local,
                )

            if not self.torrent_download_root_remote and self.torrent_download_root_local:
                self.torrent_download_root_remote = self.torrent_download_root_local

            self.torrent_download_root = self.torrent_download_root_local

            jackett_section = config_service.get_section('jackett') or {}
            self.jackett_download_base_url = self._extract_jackett_download_base(jackett_section)
            verify_value = jackett_section.get('verify_ssl') or jackett_section.get('verify_cert')
            if isinstance(verify_value, str):
                verify_value = verify_value.strip().lower()
                if verify_value in {"false", "0", "no", "off"}:
                    self.jackett_verify_ssl = False
                elif verify_value in {"true", "1", "yes", "on"}:
                    self.jackett_verify_ssl = True
            elif isinstance(verify_value, bool):
                self.jackett_verify_ssl = verify_value
            if self.jackett_download_base_url:
                logger.debug(
                    "Configured external Jackett base URL for torrent downloads: %s",
                    self.jackett_download_base_url,
                )

            self._load_direct_provider_sessions()
                
        except Exception as e:
            logger.error(f"Error loading download management configuration: {e}")
            # Keep defaults on error
    
    def _load_direct_provider_sessions(self) -> None:
        """Build a map of direct providers that require session cookies for downloads."""

        mapping: Dict[str, Dict[str, str]] = {}

        try:
            config_service = self._get_config_service()
            indexers = config_service.list_indexers_config() or {}
        except Exception as exc:
            logger.debug("Unable to load direct provider sessions: %s", exc)
            self.direct_provider_sessions = mapping
            return

        for key, data in indexers.items():
            if not isinstance(data, dict):
                continue

            enabled = data.get('enabled', True)
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in {'true', '1', 'yes', 'on'}
            if not enabled:
                continue

            idx_type = str(data.get('type', '')).lower()
            protocol = str(data.get('protocol', '')).lower()
            if idx_type != 'direct' and protocol != 'direct':
                continue

            session_id = (data.get('session_id') or '').strip()
            base_url = (data.get('base_url') or '').strip()
            if not session_id or not base_url:
                continue

            hostname = urlparse(base_url).hostname or base_url
            if not hostname:
                continue

            host_keys = {hostname.lower()}
            if hostname.lower().startswith('www.'):
                host_keys.add(hostname.lower()[4:])

            meta = {
                'session_id': session_id,
                'indexer': data.get('name') or key,
                'base_url': base_url.rstrip('/'),
            }

            for host in host_keys:
                mapping[host] = meta

        self.direct_provider_sessions = mapping
        if mapping:
            logger.debug(
                "Loaded %d direct provider session(s) for download bridge",
                len(mapping),
            )

    def _configure_audible_concurrency(self):
        """Configure Audible download concurrency based on [audible] config."""
        max_workers = 1
        try:
            config_service = self._get_config_service()
            audible_config = config_service.get_section('audible') or {}
            raw_value = (
                audible_config.get('concurrent_downloads')
                or audible_config.get('max_concurrent_downloads')
                or audible_config.get('download_concurrency')
            )
            if raw_value is None:
                raw_value = 1
            max_workers = int(raw_value)
        except Exception as exc:
            logger.debug(f"Falling back to single Audible worker: {exc}")
            max_workers = 1

        if max_workers < 1:
            max_workers = 1
        elif max_workers > 8:
            max_workers = 8  # hard cap to avoid abuse

        if max_workers != self._audible_max_workers or self._audible_executor is None:
            logger.debug(
                "Configuring Audible concurrency: previous=%s, new=%s",
                self._audible_max_workers,
                max_workers,
            )
            self._reset_audible_executor(max_workers)

    def _reset_audible_executor(self, max_workers: Optional[int] = None):
        """Recreate the Audible download executor with a new worker count."""
        if max_workers is None:
            max_workers = self._audible_max_workers or 1

        with self._audible_executor_lock:
            if self._audible_executor:
                try:
                    self._audible_executor.shutdown(wait=False)
                except Exception as exc:
                    logger.debug(f"Error shutting down Audible executor: {exc}")
                finally:
                    self._audible_executor = None

            self._audible_max_workers = max_workers
            self._audible_executor = ThreadPoolExecutor(
                max_workers=self._audible_max_workers,
                thread_name_prefix="AudibleDownload"
            )

    def set_audible_concurrency(self, max_workers: int) -> int:
        """Public helper to adjust Audible download worker count."""
        try:
            requested = int(max_workers)
        except (TypeError, ValueError):
            requested = 1

        if requested < 1:
            requested = 1
        elif requested > 8:
            requested = 8

        self._reset_audible_executor(requested)
        logger.debug("Audible concurrency updated to %s worker(s)", requested)
        return requested

    def _ensure_audible_executor(self) -> ThreadPoolExecutor:
        """Return an active executor for Audible downloads."""
        with self._audible_executor_lock:
            if self._audible_executor is None:
                self._audible_executor = ThreadPoolExecutor(
                    max_workers=self._audible_max_workers or 1,
                    thread_name_prefix="AudibleDownload"
                )
            return self._audible_executor

    def _schedule_audible_download(self, download_id: int, download: Dict[str, Any]):
        """Submit an Audible download task to the worker pool."""
        cancel_event = self._register_audible_download(download_id)
        executor = self._ensure_audible_executor()

        future = executor.submit(
            self._run_audible_download,
            download_id,
            download,
            cancel_event,
        )

        def _log_future_done(fut):
            try:
                fut.result()
            except Exception as exc:  # pragma: no cover - executor callback logging
                logger.error(f"Audible download task for {download_id} raised: {exc}")

        future.add_done_callback(_log_future_done)

        with self._audible_context_lock:
            context = self._audible_download_context.get(download_id, {})
            context['future'] = future
            self._audible_download_context[download_id] = context

    def reload_configuration(self) -> bool:
        """Reload download management configuration without recreating the singleton."""
        with self._lock:
            try:
                logger.debug("Reloading download management configuration...")
                self._load_configuration()
                self._configure_audible_concurrency()

                if self.auto_start_monitoring:
                    self._ensure_monitor_running()
                elif self.monitor_running:
                    logger.debug("Auto-start disabled; stopping active monitor thread")
                    self.stop_monitoring()

                return True
            except Exception as exc:  # pragma: no cover - defensive safety net
                logger.error(f"Failed to reload download management configuration: {exc}")
                return False

    def _extract_jackett_download_base(self, jackett_section: Dict[str, Any]) -> Optional[str]:
        """Determine an alternate Jackett base URL for download link rewriting."""

        candidates = [
            os.environ.get("JACKETT_DOWNLOAD_BASE_URL"),
            jackett_section.get('download_base_url'),
            jackett_section.get('download_url_base'),
            jackett_section.get('download_url_host'),
            jackett_section.get('download_host'),
            jackett_section.get('external_base_url'),
        ]

        for candidate in candidates:
            if not candidate:
                continue
            if isinstance(candidate, bool):
                continue
            value = str(candidate).strip()
            if value:
                return value
        return None

    def _get_database_service(self):
        """Lazy load DatabaseService."""
        if self._database_service is None:
            from services.service_manager import get_database_service
            self._database_service = get_database_service()
        return self._database_service
    
    def _get_config_service(self):
        """Lazy load ConfigService."""
        if self._config_service is None:
            from services.service_manager import get_config_service
            self._config_service = get_config_service()
        return self._config_service
    
    def _get_search_engine_service(self):
        """Lazy load SearchEngineService."""
        if self._search_engine_service is None:
            from services.service_manager import get_search_engine_service
            self._search_engine_service = get_search_engine_service()
        return self._search_engine_service
    
    def _get_conversion_service(self):
        """Lazy load ConversionService."""
        if self._conversion_service is None:
            from services.conversion_service.conversion_service import ConversionService
            self._conversion_service = ConversionService()
        return self._conversion_service
    
    def _get_import_service(self):
        """Lazy load ImportService."""
        if self._import_service is None:
            from services.import_service.import_service import ImportService
            self._import_service = ImportService()
        return self._import_service
    
    # ============================================================================
    # PUBLIC API - Queue Management
    # ============================================================================
    
    def add_to_queue(self, book_asin: str, search_result_id: Optional[int] = None,
                     priority: int = 5, **kwargs) -> Dict[str, Any]:
        """
        Add a book to the download queue.
        
        Args:
            book_asin: Audible ASIN (primary identifier)
            search_result_id: Reference to search_results table (optional)
            priority: Queue priority 1-10 (default 5)
            **kwargs: Additional book metadata (title, author, etc.)
        
        Returns:
            {
                'success': bool,
                'download_id': int,
                'message': str
            }
        """
        try:
            logger.info(f"Adding book {book_asin} to download queue (priority={priority})")

            requested_type = (kwargs.get('download_type') or 'torrent').lower()
            ownership_details: Dict[str, Any] = kwargs.get('ownership_details') or {}
            audible_entry_override: Optional[Dict[str, Any]] = kwargs.pop('audible_entry_override', None)

            if requested_type == 'audible':
                db_service = self._get_database_service()
                audible_entry = fetch_audible_library_entry(db_service, book_asin)
                if audible_entry_override:
                    audible_entry = merge_audible_records(audible_entry, audible_entry_override)
                owned_via_audible, assessed_details = assess_audible_ownership(audible_entry)

                if not owned_via_audible:
                    reason = assessed_details.get('reason') if assessed_details else 'Ownership verification failed.'
                    logger.warning(
                        "Blocked Audible queue request for ASIN %s: %s",
                        book_asin,
                        reason
                    )
                    return {
                        'success': False,
                        'message': f'Audible ownership verification failed: {reason}'
                    }

                if not ownership_details:
                    ownership_details = assessed_details
                else:
                    ownership_details.setdefault('reason', assessed_details.get('reason'))
                kwargs['ownership_details'] = ownership_details
                kwargs['download_type'] = 'audible'
            
            # Check for existing active download
            existing = self.queue_manager.get_active_download_by_asin(book_asin)
            if existing:
                return {
                    'success': False,
                    'message': f"Book already in queue with status: {existing['status']}"
                }
            
            # Add to queue
            download_id = self.queue_manager.add_to_queue(
                book_asin=book_asin,
                search_result_id=search_result_id,
                priority=priority,
                **kwargs
            )
            
            # Emit event
            self.event_emitter.emit_queue_added(download_id, book_asin)
            
            # Make sure the monitor loop is active so this item progresses
            self._ensure_monitor_running()

            logger.info(f"Book {book_asin} added to queue with ID {download_id}")
            return {
                'success': True,
                'download_id': download_id,
                'message': 'Added to download queue'
            }
            
        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return {
                'success': False,
                'message': f'Failed to add to queue: {str(e)}'
            }
    
    def get_queue(self, status_filter: Optional[str] = None, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all items in the download queue.
        
        Args:
            status_filter: Optional status to filter by
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)
        
        Returns:
            List of download queue items
        """
        all_items = self.queue_manager.get_queue(status_filter)
        
        # Apply pagination if limit is specified
        if limit is not None:
            return all_items[offset:offset + limit]
        elif offset > 0:
            return all_items[offset:]
        
        return all_items
    
    def cancel_download(self, download_id: int) -> Dict[str, Any]:
        """
        Cancel a download and clean up files.
        
        Args:
            download_id: Download queue ID
        
        Returns:
            {'success': bool, 'message': str}
        """
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                return {'success': False, 'message': 'Download not found'}
            
            logger.info(f"Cancelling download {download_id} (ASIN: {download['book_asin']})")
            
            # Stop monitoring if active
            status = (download.get('status') or '').upper()
            if status == 'AUDIBLE_DOWNLOADING':
                self._request_audible_cancel(download_id)
                self.download_monitor.stop_monitoring(download_id)
            elif status == 'DOWNLOADING':
                self.download_monitor.stop_monitoring(download_id)
            
            # Remove from client if present
            if download.get('download_client_id'):
                self.cleanup_manager.remove_from_client(
                    download['download_client'],
                    download['download_client_id']
                )
            
            # Clean up files
            self.cleanup_manager.cleanup_download_files(download_id)
            
            # Update state
            self.state_machine.transition(download_id, 'CANCELLED')
            
            # Emit event
            self.event_emitter.emit_download_cancelled(download_id)
            
            return {'success': True, 'message': 'Download cancelled'}
            
        except Exception as e:
            logger.error(f"Error cancelling download: {e}")
            return {'success': False, 'message': str(e)}
    
    def pause_download(self, download_id: int) -> Dict[str, Any]:
        """
        Pause an active download (only works during DOWNLOADING state).
        
        Args:
            download_id: Download queue ID
        
        Returns:
            {'success': bool, 'message': str}
        """
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                return {'success': False, 'message': 'Download not found'}
            
            if download['status'] != 'DOWNLOADING':
                return {
                    'success': False,
                    'message': f"Cannot pause download in {download['status']} state"
                }
            
            logger.info(f"Pausing download {download_id}")
            
            # Pause in client
            client = self.client_selector.get_client(download['download_client'])
            if client:
                client.pause(download['download_client_id'])
            
            # Update state
            self.state_machine.transition(download_id, 'PAUSED')
            
            # Emit event
            self.event_emitter.emit_download_paused(download_id)
            
            return {'success': True, 'message': 'Download paused'}
            
        except Exception as e:
            logger.error(f"Error pausing download: {e}")
            return {'success': False, 'message': str(e)}
    
    def resume_download(self, download_id: int) -> Dict[str, Any]:
        """
        Resume a paused download.
        
        Args:
            download_id: Download queue ID
        
        Returns:
            {'success': bool, 'message': str}
        """
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                return {'success': False, 'message': 'Download not found'}
            
            if download['status'] != 'PAUSED':
                return {
                    'success': False,
                    'message': f"Cannot resume download in {download['status']} state"
                }
            
            logger.info(f"Resuming download {download_id}")
            
            # Resume in client
            client = self.client_selector.get_client(download['download_client'])
            if client:
                client.resume(download['download_client_id'])
            
            # Update state
            self.state_machine.transition(download_id, 'DOWNLOADING')
            
            # Emit event
            self.event_emitter.emit_download_resumed(download_id)
            
            return {'success': True, 'message': 'Download resumed'}
            
        except Exception as e:
            logger.error(f"Error resuming download: {e}")
            return {'success': False, 'message': str(e)}

    def clear_queue(self, include_active: bool = False,
                    include_imported: bool = False,
                    statuses: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Remove downloads from the queue for recovery scenarios.

        Args:
            include_active: If True, also cancel and remove active downloads.
            include_imported: If True, remove imported entries from history.
            statuses: Optional list of statuses to clear. Defaults to known pipeline states.

        Returns:
            {'success': bool, 'removed': int, 'cleared_ids': List[int], 'message': str}
        """
        try:
            base_statuses = statuses if statuses else list(self.CLEARABLE_STATUSES)

            processed_ids = set()
            cleared_ids: List[int] = []
            errors: List[Dict[str, Any]] = []

            normalized_statuses: List[str] = []
            for status in base_statuses:
                if not isinstance(status, str):
                    continue
                normalized = status.upper()
                if normalized in {'DOWNLOADING', 'AUDIBLE_DOWNLOADING'} and not include_active:
                    continue
                if normalized == 'IMPORTED' and not include_imported:
                    continue
                normalized_statuses.append(normalized)

            # Ensure deterministic ordering and remove duplicates while preserving order
            seen_statuses = set()
            ordered_statuses: List[str] = []
            for status in normalized_statuses:
                if status not in seen_statuses:
                    seen_statuses.add(status)
                    ordered_statuses.append(status)

            for status in ordered_statuses:
                try:
                    queue_items = self.queue_manager.get_queue(status_filter=status)
                except Exception as fetch_error:
                    logger.error(f"Error fetching downloads for status {status}: {fetch_error}")
                    errors.append({'status': status, 'error': str(fetch_error)})
                    continue

                for item in queue_items:
                    download_id = item.get('id') or item.get('ID')
                    if download_id is None or download_id in processed_ids:
                        continue

                    processed_ids.add(download_id)

                    try:
                        if status == 'AUDIBLE_DOWNLOADING':
                            self._request_audible_cancel(download_id)

                        if status in {'DOWNLOADING', 'AUDIBLE_DOWNLOADING'}:
                            self.download_monitor.stop_monitoring(download_id)
                    except Exception as monitor_error:
                        logger.warning(f"Failed to stop monitoring download {download_id}: {monitor_error}")

                    try:
                        self.cleanup_manager.cleanup_download_files(download_id)
                    except Exception as cleanup_error:
                        logger.warning(f"Cleanup failed for download {download_id}: {cleanup_error}")

                    try:
                        self.queue_manager.delete_download(download_id)
                        cleared_ids.append(download_id)
                    except Exception as delete_error:
                        logger.error(f"Failed to delete download {download_id}: {delete_error}")
                        errors.append({'id': download_id, 'error': str(delete_error)})

            if cleared_ids:
                self.event_emitter.emit_queue_updated()

            message = f"Removed {len(cleared_ids)} download(s) from queue"
            success_flag = True
            if errors and not cleared_ids:
                message = 'No downloads were removed from the queue'
                success_flag = False
            elif errors:
                message = f"{message} with some errors"

            result: Dict[str, Any] = {
                'success': success_flag,
                'removed': len(cleared_ids),
                'cleared_ids': cleared_ids,
                'message': message
            }
            if errors:
                result['errors'] = errors

            return result

        except Exception as e:
            logger.error(f"Error clearing download queue: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Failed to clear queue: {str(e)}'
            }
    
    # ============================================================================
    # MONITORING & AUTOMATION
    # ============================================================================
    
    def start_monitoring(self):
        """Start the download monitoring thread."""
        with self._monitor_lock:
            if self.monitor_running:
                logger.debug("Download monitor thread already running")
                return

            logger.debug("Starting download monitor thread...")
            self.monitor_running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="DownloadMonitor",
                daemon=True
            )
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop the download monitoring thread."""
        logger.debug("Stopping download monitor thread...")
        self.monitor_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            self.monitor_thread = None
    
    @property
    def monitoring_active(self) -> bool:
        """Expose monitor thread state for status reporting endpoints."""
        return self.monitor_running

    # ------------------------------------------------------------------
    # Audible download coordination helpers
    # ------------------------------------------------------------------

    def _register_audible_download(self, download_id: int) -> threading.Event:
        """Create and track a cancellation token for an Audible download."""
        cancel_event = threading.Event()
        with self._audible_context_lock:
            self._audible_download_context[download_id] = {
                'cancel_event': cancel_event,
                'registered_at': datetime.utcnow().isoformat()
            }
        return cancel_event

    def _request_audible_cancel(self, download_id: int):
        """Signal any in-flight Audible download to cancel cooperatively."""
        with self._audible_context_lock:
            context = self._audible_download_context.get(download_id)

        if not context:
            return

        cancel_event = context.get('cancel_event')
        if cancel_event and not cancel_event.is_set():
            logger.info("Cancellation requested for Audible download %s", download_id)
            cancel_event.set()

    def _clear_audible_context(self, download_id: int):
        """Remove Audible download tracking metadata once finished."""
        with self._audible_context_lock:
            removed = self._audible_download_context.pop(download_id, None)

        if removed:
            logger.debug("Audible download %s context cleared", download_id)

    def _monitor_loop(self):
        """Main monitoring loop - runs continuously."""
        import time
        
        logger.debug("Download monitor thread started")
        
        while self.monitor_running:
            try:
                # Process queue - move QUEUED items to next stage
                self._process_queue()
                
                # Monitor active downloads
                self._monitor_downloads()
                
                # Process completed downloads
                self._process_pipeline()
                
                # Sleep until next poll
                time.sleep(self.polling_interval)
                
            except Exception as e:
                logger.exception("Error in download monitor loop")
                time.sleep(5)  # Back off on error
        
        logger.debug("Download monitor thread stopped")

    def _ensure_monitor_running(self):
        """Start monitoring thread if not already active."""
        if not self.monitor_running:
            self.start_monitoring()

    def _is_retry_ready(self, download: Dict[str, Any]) -> bool:
        """Return True when the download is eligible for another retry attempt."""
        next_retry_at = download.get('next_retry_at')
        if not next_retry_at:
            return True

        try:
            retry_time = datetime.fromisoformat(next_retry_at)
        except ValueError:
            return True

        return retry_time <= datetime.utcnow()
    
    def _process_queue(self):
        """Process queued items - transition QUEUED → SEARCHING/FOUND → DOWNLOADING."""
        queued_items = self.queue_manager.get_queue(status_filter='QUEUED')
        active_searches = self._count_active_searches()

        for item in queued_items:
            try:
                if not self._is_retry_ready(item):
                    continue

                download_type = (item.get('download_type') or '').strip().lower()

                if download_type == 'audible':
                    logger.info(
                        "Download %s is Audible content; launching dedicated Audible pipeline",
                        item['id']
                    )

                    updates: Dict[str, Any] = {}
                    if not item.get('indexer'):
                        updates['indexer'] = 'Audible'
                    if item.get('last_error'):
                        updates['last_error'] = None
                    if item.get('next_retry_at'):
                        updates['next_retry_at'] = None

                    if updates:
                        self.queue_manager.update_download(item['id'], updates)

                    if self.state_machine.transition(item['id'], 'AUDIBLE_DOWNLOADING'):
                        self.event_emitter.emit_download_started(item['id'])
                        refreshed = self.queue_manager.get_download(item['id']) or item
                        self._schedule_audible_download(item['id'], refreshed)
                    else:
                        logger.debug(
                            "Audible download %s already in progress; skipping start",
                            item['id']
                        )
                    continue
                # If we have search_result_id, skip to FOUND
                if item.get('search_result_id'):
                    logger.info("Download %s using pre-selected search result; scheduling download", item['id'])
                    self.state_machine.transition(item['id'], 'FOUND')
                else:
                    if active_searches >= self.max_active_searches:
                        logger.debug(
                            "Reached search concurrency limit (%s); deferring remaining queued items",
                            self.max_active_searches
                        )
                        break
                    # Need to search
                    logger.info("Download %s entering SEARCHING stage", item['id'])
                    self.state_machine.transition(item['id'], 'SEARCHING')
                    self._start_search(item['id'])
                    active_searches += 1
                    
            except Exception as e:
                logger.error(f"Error processing queued item {item['id']}: {e}")
        
        # Process FOUND items - start the actual download
        found_items = self.queue_manager.get_queue(status_filter='FOUND')
        
        for item in found_items:
            try:
                if not self._is_retry_ready(item):
                    continue

                download_type = (item.get('download_type') or '').strip().lower()
                if download_type == 'audible':
                    logger.debug(
                        "Found-stage handler skipping Audible download %s; handled via dedicated pipeline",
                        item['id']
                    )
                    continue

                logger.info("Download %s entering DOWNLOADING stage (%s)", item['id'], item.get('book_title', 'Unknown'))
                
                # Prepare source info from the item
                source_info = {
                    'download_url': item.get('download_url'),
                    'download_type': item.get('download_type', 'torrent'),
                    'indexer': item.get('indexer'),
                    'info_hash': item.get('info_hash')
                }

                if item.get('next_retry_at'):
                    self.queue_manager.update_download(item['id'], {'next_retry_at': None})
                
                # Start the actual download
                self._start_download(item['id'], source_info)
                    
            except Exception as e:
                logger.exception("Error starting download for FOUND item %s", item['id'])
    
    def _count_active_searches(self) -> int:
        try:
            searching_items = self.queue_manager.get_queue(status_filter='SEARCHING')
            return len(searching_items)
        except Exception as exc:
            logger.debug("Unable to count active searches: %s", exc)
            return 0

    def _monitor_downloads(self):
        """Monitor active downloads - poll clients for progress."""
        active_downloads = self.queue_manager.get_queue(status_filter='DOWNLOADING')
        
        for download in active_downloads:
            try:
                if (download.get('download_type') or '').strip().lower() == 'audible':
                    logger.debug(
                        "Skipping monitor poll for Audible download %s; progress handled via API callbacks",
                        download['id']
                    )
                    continue
                self.download_monitor.update_progress(download['id'])
            except Exception as e:
                logger.exception("Error monitoring download %s", download['id'])
    
    def _process_pipeline(self):
        """
        Process completed stages - trigger next pipeline stage.
        
        Critical: Conversion is ONLY needed for Audible downloads (AAX/AAXC format).
        Torrent/NZB downloads are already in M4B/MP3 format and skip directly to import.
        """
        # COMPLETE → check if conversion needed
        complete_items = self.queue_manager.get_queue(status_filter='COMPLETE')
        for item in complete_items:
            try:
                # Determine if conversion is needed based on source
                raw_download_url = item.get('download_url')
                download_url = (raw_download_url or '').strip()
                raw_file_format = item.get('file_format')
                file_format = (raw_file_format or '').strip().lower()
                temp_file_path = (item.get('temp_file_path') or '').strip()
                
                # Multiple checks to identify Audible downloads that need conversion:
                # 1. Download URL contains 'audible.com'
                # 2. File format is explicitly AAX/AAXC
                # 3. Downloaded file has .aax or .aaxc extension
                needs_conversion = (
                    'audible.com' in download_url.lower() or
                    file_format in ('aax', 'aaxc') or
                    download_url.endswith('.aax') or
                    download_url.endswith('.aaxc') or
                    (temp_file_path and (temp_file_path.endswith('.aax') or temp_file_path.endswith('.aaxc')))
                )
                
                if needs_conversion:
                    logger.info(f"Download {item['id']} is Audible format (AAX/AAXC) - starting FFmpeg conversion to M4B")
                    self._start_conversion(item['id'])
                else:
                    # Torrent/NZB downloads are already in M4B/MP3 - skip to import
                    logger.info(f"Download {item['id']} is torrent/NZB (already M4B/MP3) - skipping conversion, proceeding to AudioBookShelf import")
                    self._start_import(item['id'])
                    
            except Exception as e:
                logger.error(f"Error processing completed item {item['id']}: {e}")
        
        # CONVERTED → start import
        converted_items = self.queue_manager.get_queue(status_filter='CONVERTED')
        for item in converted_items:
            try:
                self._start_import(item['id'])
            except Exception as e:
                logger.error(f"Error starting import for {item['id']}: {e}")
        
        # SEEDING → monitor or finalize depending on configuration
        seeding_items = self.queue_manager.get_queue(status_filter='SEEDING')

        if self.monitor_seeding_enabled:
            for item in seeding_items:
                try:
                    self.download_monitor.monitor_seeding(item['id'])
                except Exception as e:
                    logger.error(f"Error monitoring seeding for {item['id']}: {e}")
        else:
            for item in seeding_items:
                try:
                    if self.cleanup_manager.check_seeding_complete(item['id'], item):
                        logger.info(f"Seeding complete for download {item['id']}, finalizing...")

                        self.cleanup_manager.finalize_seeding(
                            download_id=item['id'],
                            download_data=item,
                            delete_files=self.delete_source_after_import
                        )

                        if self.state_machine.transition(item['id'], 'SEEDING_COMPLETE'):
                            self.event_emitter.emit_state_changed(
                                item['id'],
                                'SEEDING_COMPLETE',
                                'Seeding finished and cleaned up'
                            )
                            logger.info(f"Download {item['id']} marked as SEEDING_COMPLETE")
                            try:
                                self.queue_manager.delete_download(item['id'])
                                self.event_emitter.emit_queue_updated()
                                logger.info(f"Download {item['id']} removed from queue after seeding")
                            except Exception as delete_error:
                                logger.error(
                                    "Failed to remove download %s from queue after seeding: %s",
                                    item['id'],
                                    delete_error
                                )

                except Exception as e:
                    logger.error(f"Error processing seeding item {item['id']}: {e}")
    
    def _start_search(self, download_id: int):
        """Initiate search for a book in indexers."""
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                logger.error(f"Download {download_id} not found")
                return
            
            current_type = (download.get('download_type') or '').strip().lower()
            if current_type == 'audible':
                logger.info(
                    "Download %s marked as Audible; skipping indexer search and transitioning to FOUND",
                    download_id
                )
                if not download.get('indexer'):
                    self.queue_manager.update_download(download_id, {'indexer': 'Audible', 'last_error': None})
                if self.state_machine.transition(download_id, 'FOUND'):
                    self.event_emitter.emit_state_changed(
                        download_id,
                        'FOUND',
                        'Audible download scheduled for direct retrieval'
                    )
                return

            book_asin = download.get('book_asin')
            logger.info(f"Starting search for download {download_id} (ASIN: {book_asin})")
            
            # Get book metadata from database
            db_service = self._get_database_service()
            book_data = db_service.get_book_by_asin(book_asin)
            
            if not book_data:
                error_msg = f"Book with ASIN {book_asin} not found in database"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return
            
            # Extract search parameters
            title = book_data.get('Title', '')
            author = book_data.get('Author', '')
            
            if not title or not author:
                error_msg = f"Missing title or author for ASIN {book_asin}"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return
            
            # Perform search using SearchEngineService
            search_service = self._get_search_service()
            logger.info(f"Searching for: {title} by {author}")
            
            search_results = search_service.search_for_audiobook(
                title=title,
                author=author,
                manual_search=False  # Automatic search for download management
            )
            
            if not search_results.get('success'):
                error_msg = search_results.get('error', 'Search failed')
                logger.error(f"Search failed for {title}: {error_msg}")
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return
            
            # Get the best result (automatic selection)
            results = search_results.get('results', [])
            if not results:
                error_msg = f"No search results found for {title} by {author}"
                logger.warning(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return
            
            def _unwrap_result(entry: Dict[str, Any]) -> Dict[str, Any]:
                if not isinstance(entry, dict):
                    return {}
                nested = entry.get('selected_result')
                if isinstance(nested, dict) and nested:
                    combined = nested.copy()
                    # Preserve useful metadata from wrapper when missing in nested payload
                    if 'confidence_score' not in combined and 'confidence_score' in entry:
                        combined['confidence_score'] = entry.get('confidence_score')
                    if 'indexer' not in combined and 'indexer' in entry:
                        combined['indexer'] = entry.get('indexer')
                    return combined
                return entry

            def _confidence(entry: Dict[str, Any]) -> float:
                payload = _unwrap_result(entry)
                score = payload.get('confidence_score')
                if score is None:
                    score = entry.get('confidence_score', 0)
                return score or 0

            best_wrapper = max(results, key=_confidence)
            best_result = _unwrap_result(best_wrapper)
            best_confidence = _confidence(best_wrapper)

            min_confidence = 85
            if best_confidence < min_confidence:
                error_msg = (
                    f"Best search result confidence {best_confidence} below required"
                    f" threshold {min_confidence}"
                )
                logger.warning(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return

            if not best_result.get('download_url'):
                error_msg = "Selected search result is missing a download URL"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=error_msg
                )
                return

            logger.info(
                "Found download source: %s - Quality: %s",
                best_result.get('indexer'),
                best_result.get('confidence_score', 0)
            )
            
            # Update download with source info
            new_type = (best_result.get('download_type') or '').strip().lower()
            if current_type == 'audible' and new_type != 'audible':
                new_type = 'audible'
            elif not new_type:
                new_type = current_type or 'torrent'

            self.queue_manager.update_download(download_id, {
                'download_url': best_result.get('download_url'),
                'indexer': best_result.get('indexer'),
                'quality_score': best_result.get('confidence_score', 0),
                'download_type': new_type,
                'last_error': None,
                'info_hash': best_result.get('info_hash')
            })
            
            # Transition to FOUND state and start download
            if self.state_machine.transition(download_id, 'FOUND'):
                self.event_emitter.emit_state_changed(download_id, 'FOUND', 'Search completed')
                # Start actual download in next cycle
                self._start_download(download_id, best_result)
            
        except Exception as e:
            logger.exception("Error during search for download %s", download_id)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='SEARCH_FAILED',
                    error_message=str(e)
                )
    
    def _start_download(self, download_id: int, source_info: Dict[str, Any]):
        """Start the actual download using appropriate client based on download_type."""
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                logger.error(f"Download {download_id} not found")
                return

            if download.get('next_retry_at'):
                self.queue_manager.update_download(download_id, {'next_retry_at': None})
            
            download_url = source_info.get('download_url') or download.get('download_url')
            download_type = (source_info.get('download_type')
                             or download.get('download_type')
                             or 'torrent')
            download_type = (download_type or '').strip().lower()
            
            logger.info(f"Starting {download_type} download for {download_id}")
            
            # Branch based on download_type
            if download_type == 'audible':
                current_status = (download.get('status') or '').upper()

                if current_status == 'AUDIBLE_DOWNLOADING':
                    logger.debug(
                        "Audible download %s already running via dedicated pipeline",
                        download_id
                    )
                    return

                if self.state_machine.transition(download_id, 'AUDIBLE_DOWNLOADING'):
                    self.event_emitter.emit_download_started(download_id)
                    refreshed = self.queue_manager.get_download(download_id) or download
                    self._schedule_audible_download(download_id, refreshed)
                else:
                    logger.debug(
                        "Audible download %s could not transition to AUDIBLE_DOWNLOADING (status=%s)",
                        download_id,
                        current_status or 'UNKNOWN'
                    )
                return
            elif download_type in ('torrent', 'nzb'):
                if not download_url:
                    error_msg = "Download source missing download_url; retrying search"
                    logger.error(error_msg)
                    self.retry_handler.handle_failure(
                        download_id=download_id,
                        failure_status='SEARCH_FAILED',
                        error_message=error_msg
                    )
                    return

                try:
                    normalized_url = self._normalize_download_url(download_url, allow_localhost=True)
                except RuntimeError as rewrite_error:
                    error_msg = str(rewrite_error)
                    logger.error(error_msg)
                    self.queue_manager.update_download(download_id, {'last_error': error_msg})
                    self.retry_handler.handle_failure(
                        download_id=download_id,
                        failure_status='DOWNLOAD_FAILED',
                        error_message=error_msg
                    )
                    return

                if normalized_url != download_url:
                    logger.debug(
                        "Rewriting download URL for download %s: %s -> %s",
                        download_id,
                        download_url,
                        normalized_url,
                    )
                    download_url = normalized_url
                    self.queue_manager.update_download(download_id, {'download_url': download_url})

                info_hash = source_info.get('info_hash') or download.get('info_hash')
                self._start_torrent_download(
                    download_id,
                    download,
                    download_url,
                    download_type,
                    info_hash,
                )
            else:
                error_msg = f"Unknown download_type: {download_type}"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='DOWNLOAD_FAILED',
                    error_message=error_msg
                )
                
        except Exception as e:
            logger.exception("Error starting download %s", download_id)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='DOWNLOAD_FAILED',
                    error_message=str(e)
                )
    
    def _run_audible_download(self, download_id: int, download: Dict[str, Any], cancel_event: Optional[threading.Event] = None):
        """Worker function to download an Audible audiobook."""
        temp_path: Optional[str] = None

        try:
            current_status = (download.get('status') or '').upper()
            if current_status == 'CANCELLED':
                logger.info(
                    "Audible download %s cancellation detected before start; skipping",
                    download_id
                )
                return

            if current_status != 'AUDIBLE_DOWNLOADING':
                logger.debug(
                    "Audible download %s invoked while status=%s; ignoring",
                    download_id,
                    current_status or 'UNKNOWN'
                )
                return

            book_asin = download.get('book_asin')
            if not book_asin:
                raise ValueError("Missing book_asin for Audible download")
            
            logger.info(f"Starting Audible download for ASIN: {book_asin}")
            
            # Create download directory
            temp_path = os.path.join(self.temp_download_path, str(download_id))
            os.makedirs(temp_path, exist_ok=True)

            # Determine preferred format/quality from queue metadata or config defaults
            file_format_field = (download.get('file_format') or '').strip()
            config_defaults = {}
            try:
                config_service = self._get_config_service()
                config_defaults = config_service.get_section('audible') or {}
            except Exception as cfg_error:  # pragma: no cover - defensive logging
                logger.debug(f"Unable to load Audible config defaults: {cfg_error}")

            config_format = str(config_defaults.get('download_format', 'aaxc')).lower()
            config_quality = str(config_defaults.get('download_quality', 'best')).lower()
            fallback_flag_raw = str(config_defaults.get('aax_fallback_enabled', 'true')).strip().lower()
            fallback_enabled_default = fallback_flag_raw in {'true', '1', 'yes', 'on'}

            valid_formats = {'aax', 'aaxc', 'aax-fallback'}
            valid_qualities = {'best', 'high', 'normal'}

            preferred_format = config_format if config_format in valid_formats else 'aaxc'
            preferred_quality = config_quality if config_quality in valid_qualities else 'best'

            if file_format_field:
                parts = [segment.strip().lower() for segment in file_format_field.split(':') if segment.strip()]
                if parts:
                    if parts[0] in valid_formats:
                        preferred_format = parts[0]
                    if len(parts) > 1 and parts[1] in valid_qualities:
                        preferred_quality = parts[1]

            # Finalize format and fallback behaviour
            download_format = preferred_format
            aax_fallback_enabled = fallback_enabled_default

            if download_format == 'aax-fallback':
                download_format = 'aax'
                aax_fallback_enabled = True
            elif download_format == 'aax':
                aax_fallback_enabled = fallback_enabled_default
            else:
                # For AAXC we always allow helper to fall back internally if needed
                aax_fallback_enabled = True

            logger.info(
                "Audible download %s preferences → format=%s, quality=%s, fallback=%s",
                download_id,
                download_format,
                preferred_quality,
                aax_fallback_enabled
            )
            
            # Import and use AudibleDownloadHelper
            from services.audible.audible_download_service.audible_download_helper import AudibleDownloadHelper
            
            start_time = datetime.now()
            last_logged_pct = {'value': -10.0}

            # Progress callback for real-time updates
            def on_progress(downloaded_bytes: int, total_bytes: int, message: str):
                if total_bytes <= 0 or (cancel_event and cancel_event.is_set()):
                    return

                progress_pct = (downloaded_bytes / total_bytes) * 100
                self.queue_manager.update_download(download_id, {
                    'download_progress': progress_pct,
                    'updated_at': datetime.now().isoformat()
                })
                self.event_emitter.emit_progress(download_id, progress_pct, message)

                if progress_pct >= last_logged_pct['value'] + 10.0 or downloaded_bytes >= total_bytes:
                    elapsed = (datetime.now() - start_time).total_seconds() or 1.0
                    downloaded_mb = downloaded_bytes / (1024 * 1024)
                    total_mb = total_bytes / (1024 * 1024)
                    speed_mb_s = downloaded_mb / elapsed
                    logger.debug(
                        "Audible download %s progress %.1f%% (%.2f / %.2f MB, %.2f MB/s)",
                        download_id,
                        progress_pct,
                        downloaded_mb,
                        total_mb,
                        speed_mb_s
                    )
                    last_logged_pct['value'] = progress_pct
            
            # Initialize download helper with progress callback and cancellation support
            download_helper = AudibleDownloadHelper(progress_callback=on_progress, cancel_event=cancel_event)
            
            # Get book metadata for filename
            db_service = self._get_database_service()
            book_data = db_service.get_book_by_asin(book_asin)
            title = book_data.get('Title', book_asin) if book_data else book_asin
            
            # Sanitize filename
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
            
            # Download the audiobook (async operation)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    download_helper.download_book(
                        asin=book_asin,
                        output_dir=Path(temp_path),
                        filename=safe_title,
                        format_preference=download_format,
                        quality=preferred_quality,
                        aax_fallback=aax_fallback_enabled
                    )
                )
            finally:
                loop.close()
            
            if not result.get('success'):
                raise Exception(result.get('error', 'Audible download failed'))
            
            # Extract file paths
            audio_file = result.get('audio_file')
            voucher_file = result.get('voucher_file')
            file_format = result.get('format', 'aaxc').upper()
            
            total_elapsed = (datetime.now() - start_time).total_seconds() or 1.0
            total_size_mb = os.path.getsize(audio_file) / (1024 * 1024) if audio_file and os.path.exists(audio_file) else 0.0
            avg_speed_mb_s = total_size_mb / total_elapsed
            logger.info(
                "Audible download complete: %s (elapsed %.1fs, %.2f MB, avg %.2f MB/s)",
                audio_file,
                total_elapsed,
                total_size_mb,
                avg_speed_mb_s
            )
            
            # Update download record with file paths and mark download as finished
            completion_updates = {
                'temp_file_path': audio_file,
                'voucher_file_path': voucher_file,
                'file_format': file_format.lower(),
                'download_progress': 100.0,
                'completed_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
            self.queue_manager.update_download(download_id, completion_updates)

            if self.state_machine.transition(download_id, 'COMPLETE'):
                self.event_emitter.emit_complete(download_id)
            else:
                current_record = self.queue_manager.get_download(download_id) or {}
                current_status = (current_record.get('status') or '').upper()

                # Attempt to normalize stale states so we don't requeue the download
                if current_status in {'FOUND', 'AUDIBLE_DOWNLOAD_FAILED'}:
                    logger.warning(
                        "Audible download %s finished while queue status was %s; coercing lifecycle",
                        download_id,
                        current_status
                    )

                    if self.state_machine.transition(download_id, 'AUDIBLE_DOWNLOADING'):
                        if self.state_machine.transition(download_id, 'COMPLETE'):
                            self.event_emitter.emit_complete(download_id)
                            logger.info(
                                "Audible download %s lifecycle coerced to COMPLETE from FOUND",
                                download_id
                            )
                            return

                elif current_status == 'CANCELLED':
                    logger.info(
                        "Audible download %s completed after cancellation request; leaving status CANCELLED",
                        download_id
                    )
                    return

                logger.warning(
                    "Audible download %s completed but state transition to COMPLETE was rejected (status=%s)",
                    download_id,
                    current_status or 'UNKNOWN'
                )
                # Ensure downstream pipeline does not restart the download
                self.queue_manager.update_download(download_id, {'status': 'COMPLETE'})
                self.event_emitter.emit_complete(download_id)
            
            logger.info(f"Audible download {download_id} completed successfully")
            
        except asyncio.CancelledError:
            logger.info("Audible download %s cancelled before completion", download_id)

            if temp_path and os.path.isdir(temp_path):
                shutil.rmtree(temp_path, ignore_errors=True)

            existing_record = self.queue_manager.get_download(download_id)
            if existing_record:
                self.queue_manager.update_download(download_id, {
                    'download_progress': None,
                    'temp_file_path': None,
                    'voucher_file_path': None,
                    'updated_at': datetime.now().isoformat()
                })
                self.state_machine.transition(download_id, 'CANCELLED')
                self.event_emitter.emit_download_cancelled(download_id)

        except Exception as e:
            logger.error(f"Audible download failed for {download_id}: {e}", exc_info=True)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='AUDIBLE_DOWNLOAD_FAILED',
                    error_message=str(e)
                )
        finally:
            self._clear_audible_context(download_id)
    
    def _start_torrent_download(
        self,
        download_id: int,
        download: Dict[str, Any],
        download_url: str,
        download_type: str,
        info_hash: Optional[str] = None,
    ):
        """Download from torrent/NZB indexers using download clients."""
        try:
            logger.info(f"Starting {download_type} download for {download_id}")
            
            # Select appropriate download client
            client_name = 'qbittorrent'
            client = self.client_selector.get_client(client_name)  # Currently only qBittorrent supported
            if not client:
                error_msg = f"No {download_type} client available"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='DOWNLOAD_FAILED',
                    error_message=error_msg
                )
                return
            
            # Get category from config
            config_service = self._get_config_service()
            category = config_service.get_config_value('qbittorrent', 'category', fallback='audiobooks')
            
            download_dir = self._build_download_directory_path(download_id, download)
            os.makedirs(download_dir, exist_ok=True)

            remote_save_path = self._map_local_to_remote(download_dir)
            if remote_save_path:
                logger.debug(
                    "Mapped local download directory '%s' to remote save path '%s' for qBittorrent",
                    download_dir,
                    remote_save_path,
                )
            else:
                logger.debug(
                    "No remote mapping for download directory '%s'; using local path for qBittorrent",
                    download_dir,
                )

            save_path_for_client = remote_save_path or download_dir
            
            torrent_payload: Any = download_url
            if download_url and isinstance(download_url, str):
                trimmed_url = download_url.strip()
                if trimmed_url.lower().startswith("magnet:"):
                    torrent_payload = trimmed_url
                elif trimmed_url.lower().startswith(("http://", "https://")):
                    try:
                        fetched_payload, fetched_type = self._fetch_remote_torrent(trimmed_url, download)
                    except PermissionError as exc:
                        error_msg = str(exc) or "Direct provider rejected download session"
                        logger.error(error_msg)
                        self.retry_handler.handle_failure(
                            download_id=download_id,
                            failure_status='DOWNLOAD_FAILED',
                            error_message=error_msg
                        )
                        return
                    if fetched_type == "bytes" and fetched_payload:
                        torrent_payload = fetched_payload
                        logger.debug("Using server-fetched torrent payload for download %s", download_id)
                    elif fetched_type == "magnet" and fetched_payload:
                        torrent_payload = fetched_payload
                        logger.debug("Resolved download %s to magnet URI via Jackett redirect", download_id)
                    else:
                        logger.warning(
                            "Failed to fetch torrent payload from %s; falling back to handing URL to client",
                            download_url,
                        )

            # Use qBittorrent's add_torrent method
            add_result = client.add_torrent(
                torrent_data=torrent_payload,
                save_path=save_path_for_client,
                category=category,
                paused=False,
                auto_tmm=False,
                expected_hash=info_hash,
            )
            
            if not add_result.get('success'):
                error_msg = add_result.get('error', 'Failed to add download to client')
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='DOWNLOAD_FAILED',
                    error_message=error_msg
                )
                return
            
            # qBittorrent may return torrent hash, or we need to find it after submission
            torrent_hash = add_result.get('hash')

            if torrent_hash:
                actual_dir = self._detect_actual_save_path(client, torrent_hash)
                if actual_dir and os.path.isdir(actual_dir):
                    requested_dir = os.path.abspath(download_dir)
                    actual_dir_abs = os.path.abspath(actual_dir)
                    if actual_dir_abs != requested_dir:
                        logger.warning(
                            "qBittorrent stored download %s in '%s' instead of requested path '%s'. "
                            "Check category defaults or Auto TMM settings if this is unintended.",
                            download_id,
                            actual_dir_abs,
                            requested_dir,
                        )
                        relocation_target = save_path_for_client
                        if relocation_target and hasattr(client, 'set_location'):
                            if client.set_location(torrent_hash, relocation_target):
                                logger.info(
                                    "Requested relocation of download %s back to %s via qBittorrent",
                                    download_id,
                                    relocation_target,
                                )
                                updated_dir = self._detect_actual_save_path(client, torrent_hash)
                                if updated_dir and os.path.isdir(updated_dir):
                                    download_dir = updated_dir
                            else:
                                logger.debug(
                                    "qBittorrent refused relocation for download %s",
                                    download_id,
                                )
                        download_dir = actual_dir_abs

            if not torrent_hash:
                import time

                time.sleep(1)  # Give qBittorrent time to add the torrent

                book_title = (download.get('book_title') or download.get('title') or '').lower()
                normalized_temp = os.path.abspath(download_dir)
                matched_hash = None

                try:
                    torrents_url = client.api_url + 'torrents/info'
                    base_params = {'sort': 'added_on', 'reverse': 'true'}

                    torrents = []
                    response = client.session.get(
                        torrents_url,
                        params={**base_params, 'category': category} if category else base_params,
                        timeout=10
                    )

                    if response.status_code == 200:
                        torrents = response.json() or []

                    # Fall back to unfiltered request if category lookup returned nothing
                    if not torrents:
                        response = client.session.get(
                            torrents_url,
                            params=base_params,
                            timeout=10
                        )

                        if response.status_code == 200:
                            torrents = response.json() or []

                    for torrent in torrents:
                        candidate_hash = torrent.get('hash')
                        if not candidate_hash:
                            continue

                        name = (torrent.get('name') or '').lower()
                        save_path = torrent.get('save_path') or ''

                        if save_path:
                            normalized_save = os.path.abspath(save_path.rstrip('/\\'))
                            if normalized_save == normalized_temp:
                                torrent_hash = candidate_hash
                                logger.info(f"Found torrent hash via save_path match: {torrent_hash}")
                                break

                        if book_title and name and book_title in name:
                            matched_hash = candidate_hash

                    if not torrent_hash and matched_hash:
                        torrent_hash = matched_hash
                        logger.info(f"Found torrent hash via name match: {torrent_hash}")

                    if not torrent_hash and torrents:
                        sorted_torrents = sorted(torrents, key=lambda t: t.get('added_on', 0), reverse=True)
                        if sorted_torrents:
                            torrent_hash = sorted_torrents[0].get('hash')
                            logger.info(f"Using most recent torrent hash fallback: {torrent_hash}")

                except Exception as find_error:
                    logger.warning(f"Could not determine torrent hash: {find_error}")

            if not torrent_hash:
                logger.warning(f"No torrent hash available for download {download_id} - monitoring may be limited")
                # Still continue - qBittorrent accepted it
            
            update_payload = {
                'download_client': client_name,
                'temp_file_path': download_dir,
                'last_error': None,
                'started_at': datetime.now().isoformat()
            }

            if torrent_hash:
                update_payload['download_client_id'] = torrent_hash
            else:
                logger.debug(f"Torrent hash still unresolved for download {download_id}; monitor will retry discovery")

            self.queue_manager.update_download(download_id, update_payload)

            current_status = download.get('status')
            latest_status = current_status
            if current_status != 'DOWNLOADING':
                latest_record = self.queue_manager.get_download(download_id)
                if latest_record:
                    latest_status = latest_record.get('status', current_status)

            if latest_status == 'DOWNLOADING':
                logger.debug(f"Download {download_id} already in DOWNLOADING state; skipping transition")
            elif self.state_machine.transition(download_id, 'DOWNLOADING'):
                self.event_emitter.emit_download_started(download_id)
                logger.info(f"Download {download_id} started with torrent hash: {torrent_hash}")
            
        except Exception as e:
            logger.exception("Error starting download %s", download_id)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='DOWNLOAD_FAILED',
                    error_message=str(e)
                )

    def _normalize_download_url(self, download_url: Optional[str], allow_localhost: bool = False) -> str:
        """Ensure torrent/NZB URLs are reachable by the download client."""

        if not download_url:
            raise RuntimeError("Missing download URL for torrent submission")

        parsed = urlparse(download_url)

        # Magnet links require no rewriting
        if parsed.scheme and parsed.scheme.lower() == 'magnet':
            return download_url

        if not parsed.scheme:
            raise RuntimeError(f"Download URL missing scheme: {download_url}")

        localhost_hosts = {'localhost', '127.0.0.1', '::1'}
        needs_override = parsed.hostname in localhost_hosts

        base_override = self.jackett_download_base_url
        if not base_override:
            env_override = os.environ.get("JACKETT_DOWNLOAD_BASE_URL")
            if env_override:
                base_override = env_override.strip()

        if needs_override and not base_override:
            if allow_localhost:
                logger.debug(
                    "Leaving localhost download URL unchanged because allow_localhost is True",
                )
                return download_url
            raise RuntimeError(
                "Download URL resolves to localhost but no external Jackett base URL is configured. "
                "Set 'download_base_url' under the [jackett] section of config/config.txt or set the "
                "JACKETT_DOWNLOAD_BASE_URL environment variable."
            )

        if needs_override and base_override:
            rewritten = self._apply_base_override(parsed, base_override)
            if not rewritten:
                raise RuntimeError(
                    f"Unable to rewrite download URL '{download_url}' using base '{base_override}'."
                )
            return rewritten

        return download_url

    @staticmethod
    def _apply_base_override(parsed_url, base_override: str) -> Optional[str]:
        """Rebuild the download URL with a new base host."""

        if not base_override:
            return None

        trimmed = base_override.strip()
        if not trimmed:
            return None

        if not trimmed.startswith(('http://', 'https://')):
            trimmed = f"{parsed_url.scheme or 'http'}://{trimmed}"

        override_parts = urlparse(trimmed)
        netloc = override_parts.netloc or override_parts.path
        if not netloc:
            return None

        base_path = override_parts.path.rstrip('/')
        rewritten_path = f"{base_path}{parsed_url.path}" if parsed_url.path else base_path
        if not rewritten_path.startswith('/'):
            rewritten_path = f"/{rewritten_path}" if rewritten_path else parsed_url.path or '/'

        return urlunparse(
            (
                override_parts.scheme or parsed_url.scheme or 'http',
                netloc,
                rewritten_path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )

    def _resolve_direct_session(self, download_url: str) -> Optional[Dict[str, str]]:
        if not self.direct_provider_sessions:
            return None

        try:
            hostname = urlparse(download_url).hostname or ''
        except Exception:
            hostname = ''

        if not hostname:
            return None

        candidates = [hostname.lower()]
        if hostname.lower().startswith('www.'):
            candidates.append(hostname.lower()[4:])

        for candidate in candidates:
            meta = self.direct_provider_sessions.get(candidate)
            if meta:
                return meta
        return None

    def _fetch_remote_torrent(self, download_url: str, download: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Any], str]:
        """Retrieve the torrent payload, handling redirects to magnet URIs when necessary."""

        session_meta = self._resolve_direct_session(download_url)
        max_attempts = 2 if session_meta else 1
        attempt = 0

        def _build_headers(meta: Optional[Dict[str, str]]) -> Tuple[Dict[str, str], Optional[Dict[str, str]]]:
            headers = {
                "User-Agent": "AuralArchive-DownloadBridge/1.0",
                "Accept": "application/x-bittorrent, application/octet-stream;q=0.9, */*;q=0.1",
            }
            cookies: Optional[Dict[str, str]] = None
            if meta:
                session_id = meta.get('session_id', '').strip()
                if session_id:
                    headers.update({
                        "Authorization": f"Bearer {session_id}",
                        "X-Session-ID": session_id,
                        "Referer": meta.get('base_url') or download_url,
                    })
                    cookies = {
                        "session": session_id,
                        "session_id": session_id,
                        "mam_id": session_id,
                    }
            return headers, cookies

        current_meta = session_meta

        while attempt < max_attempts:
            headers, cookies = _build_headers(current_meta)
            try:
                request_kwargs = {
                    "timeout": 30,
                    "verify": self.jackett_verify_ssl,
                    "headers": headers,
                    "allow_redirects": False,
                }
                if cookies:
                    request_kwargs["cookies"] = cookies

                response = requests.get(download_url, **request_kwargs)

                if response.status_code in {401, 403} and current_meta:
                    logger.warning(
                        "Direct provider rejected session while fetching %s (attempt %s)",
                        download_url,
                        attempt + 1,
                    )
                    if attempt + 1 < max_attempts:
                        self._load_direct_provider_sessions()
                        refreshed_meta = self._resolve_direct_session(download_url)
                        if refreshed_meta and refreshed_meta.get('session_id') != current_meta.get('session_id'):
                            current_meta = refreshed_meta
                            attempt += 1
                            continue
                    raise PermissionError(
                        f"Direct provider authentication failed for {download_url}"
                    )

                if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                    location = (response.headers.get("Location") or "").strip()
                    if location.lower().startswith("magnet:"):
                        return location, "magnet"
                    if location:
                        logger.debug("Following redirect for torrent payload: %s", location)
                        follow_kwargs = {
                            "timeout": 30,
                            "verify": self.jackett_verify_ssl,
                            "headers": headers,
                        }
                        if cookies:
                            follow_kwargs["cookies"] = cookies
                        response = requests.get(location, **follow_kwargs)

                response.raise_for_status()

                content_type_header = response.headers.get("Content-Type", "")
                content_type_lower = content_type_header.lower()

                text_body = response.text.strip() if content_type_lower.startswith("text/") else ""
                if text_body.lower().startswith("magnet:"):
                    return text_body, "magnet"

                content = response.content
                if not content:
                    logger.warning("Torrent download returned empty payload from %s", download_url)
                    return None, ""

                if 'bittorrent' not in content_type_lower and not download_url.lower().endswith('.torrent'):
                    logger.debug(
                        "Torrent payload from %s has unexpected content-type '%s'",
                        download_url,
                        content_type_header,
                    )

                return content, "bytes"

            except requests.RequestException as exc:
                logger.error("Failed to fetch torrent file from %s: %s", download_url, exc)
                return None, ""

        return None, ""
    
    def _start_conversion(self, download_id: int):
        """Start FFmpeg conversion for completed download."""
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                logger.error(f"Download {download_id} not found")
                return
            
            book_asin = download.get('book_asin')
            temp_file_path = download.get('temp_file_path')
            voucher_file_path = download.get('voucher_file_path')
            
            logger.info(f"Starting conversion for download {download_id} (ASIN: {book_asin})")
            
            if not temp_file_path or not os.path.exists(temp_file_path):
                error_msg = f"Downloaded file not found at {temp_file_path}"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='CONVERSION_FAILED',
                    error_message=error_msg
                )
                return
            
            # Transition to CONVERTING state
            if not self.state_machine.transition(download_id, 'CONVERTING'):
                logger.error(f"Failed to transition download {download_id} to CONVERTING state")
                return
            
            self.event_emitter.emit_state_changed(download_id, 'CONVERTING', 'Starting conversion')
            
            # Get book metadata for conversion
            db_service = self._get_database_service()
            book_data = db_service.get_book_by_asin(book_asin)
            
            # Find the actual file (may be in subdirectory)
            actual_file = self._find_downloaded_file(temp_file_path)
            if not actual_file:
                error_msg = f"Could not locate downloaded audiobook file in {temp_file_path}"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='CONVERSION_FAILED',
                    error_message=error_msg
                )
                return

            # AAXC conversions require a matching voucher file
            if Path(actual_file).suffix.lower() == '.aaxc':
                if not voucher_file_path:
                    error_msg = (
                        f"Voucher file missing for AAXC download {download_id}; "
                        "conversion cannot continue"
                    )
                    logger.error(error_msg)
                    self.retry_handler.handle_failure(
                        download_id=download_id,
                        failure_status='CONVERSION_FAILED',
                        error_message=error_msg
                    )
                    return
                if not os.path.exists(voucher_file_path):
                    error_msg = (
                        f"Voucher file not found at {voucher_file_path} for AAXC "
                        f"download {download_id}"
                    )
                    logger.error(error_msg)
                    self.retry_handler.handle_failure(
                        download_id=download_id,
                        failure_status='CONVERSION_FAILED',
                        error_message=error_msg
                    )
                    return
            
            # Setup output path for conversion
            conversion_temp_dir = os.path.join(self.temp_conversion_path, f"convert_{download_id}")
            os.makedirs(conversion_temp_dir, exist_ok=True)
            
            output_filename = f"{book_data.get('Title', 'audiobook')}.m4b"
            output_file = os.path.join(conversion_temp_dir, output_filename)
            
            # Perform conversion using ConversionService
            conversion_service = self._get_conversion_service()
            
            # Progress callback for conversion updates
            def progress_callback(message: str, progress: int):
                self.progress_tracker.emit_progress(
                    download_id=download_id,
                    progress_percentage=progress,
                    message=message
                )
            
            conversion_result = conversion_service.convert_audiobook(
                input_file=actual_file,
                output_file=output_file,
                progress_callback=progress_callback,
                metadata=book_data,
                voucher_file=voucher_file_path
            )
            
            if not conversion_result.get('success'):
                error_msg = conversion_result.get('error', 'Conversion failed')
                logger.error(f"Conversion failed for {download_id}: {error_msg}")
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='CONVERSION_FAILED',
                    error_message=error_msg
                )
                return
            
            converted_file_path = conversion_result.get('output_file', output_file)
            
            # Update download record with converted file path
            self.queue_manager.update_download(download_id, {
                'converted_file_path': converted_file_path,
                'original_file_path': actual_file,
                'last_error': None
            })
            
            # Transition to CONVERTED state
            if self.state_machine.transition(download_id, 'CONVERTED'):
                self.event_emitter.emit_state_changed(download_id, 'CONVERTED', 'Conversion completed')
                logger.info(f"Conversion completed for download {download_id}: {converted_file_path}")
                # Start import in next cycle
                self._start_import(download_id)
            
        except Exception as e:
            logger.exception("Error during conversion for download %s", download_id)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='CONVERSION_FAILED',
                    error_message=str(e)
                )
    
    def _start_import(self, download_id: int):
        """Start import to library for converted file."""
        try:
            download = self.queue_manager.get_download(download_id)
            if not download:
                logger.error(f"Download {download_id} not found")
                return
            
            book_asin = download.get('book_asin')
            download_type = download.get('download_type', 'torrent')
            temp_file_path = download.get('temp_file_path')
            converted_file_path = download.get('converted_file_path')
            
            logger.info(f"Starting import for download {download_id} (ASIN: {book_asin})")

            # Resolve media file path when conversion step was skipped (torrent/NZB)
            if not converted_file_path or not os.path.exists(converted_file_path):
                resolved_path = None
                if download_type != 'audible' and temp_file_path:
                    resolved_path = self._find_downloaded_file(temp_file_path)
                elif temp_file_path and os.path.isfile(temp_file_path):
                    resolved_path = temp_file_path

                if resolved_path and os.path.exists(resolved_path):
                    converted_file_path = resolved_path
                    download['converted_file_path'] = converted_file_path
                    self.queue_manager.update_download(download_id, {
                        'converted_file_path': converted_file_path,
                        'last_error': None
                    })
                    logger.info(f"Resolved media path for download {download_id}: {converted_file_path}")
                else:
                    expected_path = converted_file_path or temp_file_path
                    error_msg = (
                        f"Converted media file not found for download {download_id}"
                        f" (expected at {expected_path})"
                    )
                    logger.error(error_msg)
                    self.retry_handler.handle_failure(
                        download_id=download_id,
                        failure_status='IMPORT_FAILED',
                        error_message=error_msg
                    )
                    return

            # Transition to IMPORTING state (allow retries already in IMPORTING)
            current_status = download.get('status')
            transitioned = self.state_machine.transition(download_id, 'IMPORTING')
            if transitioned:
                self.event_emitter.emit_state_changed(download_id, 'IMPORTING', 'Starting library import')
                download['status'] = 'IMPORTING'
            elif current_status == 'IMPORTING':
                logger.debug(f"Download {download_id} already in IMPORTING state; continuing import workflow")
            else:
                logger.error(f"Failed to transition download {download_id} to IMPORTING state from {current_status}")
                return
            
            # Get book metadata for import
            db_service = self._get_database_service()
            book_data = db_service.get_book_by_asin(book_asin)
            
            if not book_data:
                error_msg = f"Book data not found for ASIN {book_asin}"
                logger.error(error_msg)
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='IMPORT_FAILED',
                    error_message=error_msg
                )
                return
            
            # Perform import using ImportService
            import_service = self._get_import_service()
            
            # Determine whether to move or copy file based on download type and seeding
            download_type = download.get('download_type', 'torrent')
            should_move = True  # Default: move file to library
            
            # For torrents with seeding enabled, copy instead of move to preserve seeding
            if download_type == 'torrent' and self.seeding_enabled:
                should_move = False
                logger.debug(f"Using copy mode for download {download_id} (seeding enabled)")
            else:
                logger.debug(f"Using move mode for download {download_id} (download_type={download_type}, seeding={self.seeding_enabled})")
            
            success, message, destination_path = import_service.import_book(
                source_file_path=converted_file_path,
                book_data=book_data,
                move=should_move,
                import_source='download_manager'
            )
            
            if not success:
                logger.error(f"Import failed for {download_id}: {message}")
                self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='IMPORT_FAILED',
                    error_message=message
                )
                return
            
            logger.info(f"Import successful for download {download_id}: {destination_path}")
            
            # Update download record with final path
            self.queue_manager.update_download(download_id, {
                'final_file_path': destination_path,
                'last_error': None
            })
            
            # Always ensure we pass through IMPORTED before any optional seeding
            imported_transitioned = False
            if self.state_machine.transition(download_id, 'IMPORTED'):
                imported_transitioned = True
                download['status'] = 'IMPORTED'
                self.event_emitter.emit_download_completed(download_id)
                logger.info(f"Download {download_id} completed successfully")
            elif download.get('status') == 'IMPORTED':
                imported_transitioned = True
                logger.debug(f"Download {download_id} already marked as IMPORTED; continuing post-import workflow")
            else:
                logger.error(f"Download {download_id} could not enter IMPORTED state; skipping cleanup/seeding")
                return

            # Post-import handling: seeding-aware cleanup vs full cleanup
            download_type = download.get('download_type', 'torrent')
            if self.seeding_enabled and download_type == 'torrent':
                self.cleanup_manager.cleanup_after_import(
                    download_id=download_id,
                    download_data=download,
                    seeding=True,
                    delete_source=False
                )

                if self.state_machine.transition(download_id, 'SEEDING'):
                    self.event_emitter.emit_state_changed(download_id, 'SEEDING', 'Seeding torrent')
                    logger.info(f"Download {download_id} entered seeding state")
                else:
                    logger.warning(
                        "Download %s could not transition to SEEDING despite seeding being enabled",
                        download_id
                    )
            else:
                self.cleanup_manager.cleanup_after_import(
                    download_id=download_id,
                    download_data=download,
                    seeding=False,
                    delete_source=True
                )
            
        except Exception as e:
            logger.exception("Error during import for download %s", download_id)
            self.retry_handler.handle_failure(
                    download_id=download_id,
                    failure_status='IMPORT_FAILED',
                    error_message=str(e)
                )

    def _map_local_to_remote(self, local_path: Optional[str]) -> Optional[str]:
        """Translate a local filesystem path to the remote path expected by the client."""

        if not local_path:
            return None

        normalized_local = os.path.abspath(local_path)

        local_root = self.torrent_download_root_local
        remote_root = self.torrent_download_root_remote

        if local_root and remote_root:
            local_root_abs = os.path.abspath(local_root)
            if normalized_local == local_root_abs or normalized_local.startswith(local_root_abs + os.sep):
                relative = os.path.relpath(normalized_local, local_root_abs)
                if relative in {'.', os.curdir}:
                    relative = ''
                return self._join_remote_path(remote_root, relative)

        for mapping in self.qbittorrent_path_mappings:
            local_base = mapping.get('local')
            remote_base = mapping.get('remote')
            if not local_base or not remote_base:
                continue
            local_base_abs = os.path.abspath(local_base)
            if normalized_local == local_base_abs or normalized_local.startswith(local_base_abs + os.sep):
                relative = os.path.relpath(normalized_local, local_base_abs)
                if relative in {'.', os.curdir}:
                    relative = ''
                return self._join_remote_path(remote_base, relative)

        return None

    def _map_remote_to_local(self, remote_path: Optional[str]) -> Optional[str]:
        """Translate a remote client path back to the local filesystem when possible."""

        if not remote_path:
            return None

        normalized_remote = self._normalize_remote_for_compare(remote_path)

        for mapping in self.qbittorrent_path_mappings:
            remote_base = mapping.get('remote')
            local_base = mapping.get('local')
            if not remote_base or not local_base:
                continue
            remote_base_norm = self._normalize_remote_for_compare(remote_base)
            if normalized_remote == remote_base_norm or normalized_remote.startswith(remote_base_norm + '/'):
                suffix = normalized_remote[len(remote_base_norm):].lstrip('/')
                local_base_abs = os.path.abspath(local_base)
                if not suffix:
                    return local_base_abs
                return os.path.join(local_base_abs, suffix.replace('/', os.sep))

        if self.torrent_download_root_remote and self.torrent_download_root_local:
            base_remote_norm = self._normalize_remote_for_compare(self.torrent_download_root_remote)
            if normalized_remote == base_remote_norm or normalized_remote.startswith(base_remote_norm + '/'):
                suffix = normalized_remote[len(base_remote_norm):].lstrip('/')
                local_base_abs = os.path.abspath(self.torrent_download_root_local)
                if not suffix:
                    return local_base_abs
                return os.path.join(local_base_abs, suffix.replace('/', os.sep))

        return None

    @staticmethod
    def _normalize_remote_for_compare(path: str) -> str:
        if not path:
            return ''
        normalized = path.replace('\\', '/').strip()
        while len(normalized) > 1 and normalized.endswith('/'):
            normalized = normalized[:-1]
        return normalized or '/'

    @staticmethod
    def _strip_trailing_separators(path: str) -> str:
        if not path:
            return ''
        trimmed = path
        while len(trimmed) > 1 and trimmed.endswith(('/', '\\')):
            trimmed = trimmed[:-1]
        return trimmed

    @staticmethod
    def _join_remote_path(base: str, suffix: Optional[str]) -> str:
        base = base or ''
        suffix = suffix or ''
        if not suffix:
            return base

        use_backslash = False
        if base.startswith('\\'):
            use_backslash = True
        elif base and '\\' in base and '/' not in base:
            use_backslash = True

        sep = '\\' if use_backslash else '/'

        formatted_suffix = (
            suffix.replace('/', sep)
            .replace('\\', sep)
            .strip('/\\')
        )
        if not formatted_suffix:
            return base

        if not base:
            return formatted_suffix

        if base.endswith(sep):
            return f"{base}{formatted_suffix}"

        return f"{base}{sep}{formatted_suffix}"

    def _detect_actual_save_path(self, client, torrent_hash: str) -> Optional[str]:
        """Ask the torrent client where it stored the download and map to local path."""

        if not torrent_hash or not client:
            return None

        try:
            status = client.get_status(torrent_hash)
        except Exception as exc:
            logger.debug("Unable to query qBittorrent save path for %s: %s", torrent_hash, exc)
            return None

        save_path = status.get('save_path') if isinstance(status, dict) else None
        if not save_path:
            return None

        mapped_local = self._map_remote_to_local(save_path)
        if mapped_local and os.path.isdir(mapped_local):
            return mapped_local

        normalized = os.path.abspath(save_path)
        if os.path.isdir(normalized):
            return normalized

        return None

    def _find_downloaded_file(self, base_path: Optional[str]) -> Optional[str]:
        """Find the actual audiobook file in the download directory."""
        if not base_path:
            return None

        import glob

        if os.path.isfile(base_path):
            return base_path
        if not os.path.isdir(base_path):
            return None
        
        # Common audiobook extensions
        extensions = ['*.m4b', '*.m4a', '*.mp3', '*.aax', '*.aaxc', '*.flac', '*.ogg', '*.wav']
        
        for ext in extensions:
            # Search in base path and subdirectories
            files = glob.glob(os.path.join(base_path, '**', ext), recursive=True)
            if files:
                # Return the largest file (likely the audiobook)
                return max(files, key=os.path.getsize)
        
        return None

    def _build_download_directory_path(self, download_id: int, download: Dict[str, Any]) -> str:
        """Construct a deterministic, sanitized directory for torrent downloads."""
        base_path = (
            self.torrent_download_root_local
            or self.torrent_download_root
            or self.temp_download_path
        )
        os.makedirs(base_path, exist_ok=True)

        raw_title = (
            download.get('book_title')
            or download.get('title')
            or download.get('book_asin')
            or f'download_{download_id}'
        )

        sanitized = ''.join(
            ch if ch.isalnum() or ch in (' ', '-', '_') else '_'
            for ch in raw_title
        ).strip()

        if not sanitized:
            sanitized = f'download_{download_id}'

        normalized = '_'.join(sanitized.split())
        folder_name = f"{normalized[:64]}_{download_id}"

        return os.path.join(base_path, folder_name)
    
    def _get_search_service(self):
        """Get SearchEngineService instance."""
        if not hasattr(self, '_search_service') or self._search_service is None:
            from services.search_engine.search_engine_service import SearchEngineService
            self._search_service = SearchEngineService()
        return self._search_service
    
    def _get_conversion_service(self):
        """Get ConversionService instance."""
        if not hasattr(self, '_conversion_service') or self._conversion_service is None:
            from services.conversion_service.conversion_service import ConversionService
            self._conversion_service = ConversionService()
        return self._conversion_service
    
    def _get_import_service(self):
        """Get ImportService instance."""
        if not hasattr(self, '_import_service') or self._import_service is None:
            from services.import_service.import_service import ImportService
            self._import_service = ImportService()
        return self._import_service
    
    def _get_database_service(self):
        """Get DatabaseService instance."""
        if not hasattr(self, '_database_service') or self._database_service is None:
            from services.service_manager import get_database_service
            self._database_service = get_database_service()
        return self._database_service
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status and statistics."""
        queue_stats = self.queue_manager.get_queue_statistics()
        
        active_standard = len(self.queue_manager.get_queue(status_filter='DOWNLOADING'))
        active_audible = len(self.queue_manager.get_queue(status_filter='AUDIBLE_DOWNLOADING'))

        return {
            'monitor_running': self.monitor_running,
            'polling_interval': self.polling_interval,
            'queue_statistics': queue_stats,
            'active_downloads': active_standard + active_audible
        }
