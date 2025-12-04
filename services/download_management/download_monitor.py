"""
Download Monitor
================

Monitors active downloads and seeding torrents by polling download clients.
Updates progress, speed, ETA in database and emits SocketIO events.

Features:
- Active download monitoring (DOWNLOADING state)
- Seeding completion monitoring (SEEDING state)
- Detects when client marks torrent as complete based on seeding goals
- Triggers cleanup after seeding completes
"""

import logging
import os
from typing import Dict, Any, Optional

from utils.logger import get_module_logger

logger = get_module_logger("DownloadManagement.DownloadMonitor")


class DownloadMonitor:
    """
    Polls download clients for progress and seeding status updates.
    
    Features:
    - 2-second polling interval for active downloads
    - Progress tracking (%)
    - Speed and ETA calculation
    - Completion detection
    - Stalled download detection
    - Seeding completion monitoring
    - Automatic cleanup trigger when seeding completes
    """
    
    ACTIVE_SEEDING_STATES = {
        "uploading",
        "stalledup",
        "forcedup",
        "checkingup",
        "queuedup",
        "seeding",
    }

    def __init__(self):
        """Initialize download monitor."""
        self.logger = logger
        self._queue_manager = None
        self._client_selector = None
        self._progress_tracker = None
        self._state_machine = None
        self._cleanup_manager = None
        self._event_emitter = None
        self._last_known_downloads: Dict[int, Dict[str, Any]] = {}
    
    def _get_queue_manager(self):
        """Lazy load QueueManager."""
        if self._queue_manager is None:
            from .queue_manager import QueueManager
            self._queue_manager = QueueManager()
        return self._queue_manager
    
    def _get_client_selector(self):
        """Lazy load ClientSelector."""
        if self._client_selector is None:
            from .client_selector import ClientSelector
            self._client_selector = ClientSelector()
        return self._client_selector
    
    def _get_progress_tracker(self):
        """Lazy load ProgressTracker."""
        if self._progress_tracker is None:
            from .progress_tracker import ProgressTracker
            self._progress_tracker = ProgressTracker()
        return self._progress_tracker
    
    def _get_state_machine(self):
        """Lazy load StateMachine."""
        if self._state_machine is None:
            from .state_machine import StateMachine
            self._state_machine = StateMachine()
        return self._state_machine
    
    def _get_cleanup_manager(self):
        """Lazy load CleanupManager."""
        if self._cleanup_manager is None:
            from .cleanup_manager import CleanupManager
            self._cleanup_manager = CleanupManager()
        return self._cleanup_manager
    
    def _get_event_emitter(self):
        """Lazy load EventEmitter."""
        if self._event_emitter is None:
            from .event_emitter import EventEmitter
            self._event_emitter = EventEmitter()
        return self._event_emitter

    def _cache_download(self, download_id: int, download: Dict[str, Any]):
        """Remember last known download data for seeding monitors."""
        if download:
            self._last_known_downloads[download_id] = dict(download)

    @staticmethod
    def _format_ratio_limit(value: Optional[float]) -> str:
        if isinstance(value, (int, float)):
            try:
                return f"{float(value):.2f}"
            except (TypeError, ValueError):
                return "invalid"
        return "unset"

    @staticmethod
    def _format_time_limit(value: Optional[int]) -> str:
        if isinstance(value, (int, float)):
            try:
                return str(int(value))
            except (TypeError, ValueError):
                return "invalid"
        return "unset"
    
    def update_progress(self, download_id: int):
        """
        Poll client and update progress for a download.
        
        Args:
            download_id: Download queue ID
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            self.logger.warning(f"Download {download_id} not found")
            return
        
        if download['status'] != 'DOWNLOADING':
            self.logger.debug(f"Download {download_id} not in DOWNLOADING state")
            return
        
        # Get client and poll for status
        client_selector = self._get_client_selector()
        client = client_selector.get_client(download['download_client'])
        
        if not client:
            self.logger.error(f"Client {download['download_client']} not available")
            return
        
        client_id = download.get('download_client_id')
        if not client_id:
            client_id = self._discover_torrent_hash(client, download)
            if client_id:
                queue_manager.update_download(download_id, {
                    'download_client_id': client_id,
                    'last_error': None
                })
                download['download_client_id'] = client_id
                self.logger.debug(f"Resolved torrent hash for download {download_id}: {client_id}")
            else:
                self.logger.debug(f"Skipping progress update for download {download_id} (torrent hash unavailable)")
                return
        
        try:
            # Poll client for status
            status = client.get_status(client_id)
            
            if not status:
                self.logger.warning(f"No status for download {download_id}")
                return
            
            # Extract progress data
            progress = status.get('progress', 0.0)  # 0-100
            download_speed = status.get('download_speed', 0)  # bytes/sec
            eta_seconds = status.get('eta', -1)
            
            # Update database
            updates = {
                'download_progress': progress,
                'eta_seconds': eta_seconds
            }
            queue_manager.update_download(download_id, updates)
            
            # Emit progress event
            progress_tracker = self._get_progress_tracker()
            progress_tracker.emit_progress(download_id, progress, download_speed, eta_seconds)
            
            # Check if complete
            if progress >= 100.0:
                self.logger.debug(f"Download {download_id} complete")
                state_machine = self._get_state_machine()
                state_machine.transition(download_id, 'COMPLETE')
            
        except Exception as e:
            self.logger.error(f"Error updating progress for download {download_id}: {e}")

    def _discover_torrent_hash(self, client, download: Dict[str, Any]) -> Optional[str]:
        """Attempt to resolve torrent hash for downloads missing client ID."""
        try:
            torrents = client.get_all_torrents()
            if not torrents:
                return None

            temp_path = download.get('temp_file_path')
            normalized_temp = os.path.abspath(temp_path.rstrip('/\\')) if temp_path else None
            book_title = (download.get('book_title') or download.get('title') or '').lower()
            fallback_hash = None

            for torrent in torrents:
                candidate_hash = torrent.get('hash')
                if not candidate_hash:
                    continue

                save_path = torrent.get('save_path') or ''
                if normalized_temp and save_path:
                    normalized_save = os.path.abspath(save_path.rstrip('/\\'))
                    if normalized_save == normalized_temp:
                        return candidate_hash

                name = (torrent.get('name') or '').lower()
                if book_title and name and book_title in name:
                    fallback_hash = candidate_hash

            return fallback_hash

        except Exception as exc:
            self.logger.debug(f"Unable to discover torrent hash: {exc}")
            return None
    
    def stop_monitoring(self, download_id: int):
        """
        Stop monitoring a download (used during cancellation).
        
        Args:
            download_id: Download queue ID
        """
        self.logger.debug(f"Stopped monitoring download {download_id}")
        # Currently no per-download monitoring threads
        # Main monitor loop handles all active downloads
    
    def monitor_seeding(self, download_id: int):
        """
        Monitor a seeding torrent and detect when seeding completes.
        
        This method is called for downloads in SEEDING state to check if the
        download client has marked the torrent as complete based on its seeding
        goals (ratio reached, time elapsed, etc.).
        
        When seeding completes, triggers cleanup based on delete_source setting.
        
        Args:
            download_id: Download queue ID
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            download = getattr(self, '_last_known_downloads', {}).get(download_id)
            if not download:
                self.logger.warning(f"Download {download_id} not found for seeding monitor")
                return
        else:
            self._cache_download(download_id, download)
        
        # Only monitor downloads in SEEDING state
        if download.get('status') != 'SEEDING':
            self.logger.debug(f"Download {download_id} not in SEEDING state, skipping seeding monitor")
            return
        
        # Get client
        client_selector = self._get_client_selector()
        client_name = download.get('download_client')
        client_id = download.get('download_client_id')
        
        if not client_name or not client_id:
            self.logger.error(f"Download {download_id} missing client info for seeding monitor")
            return
        
        client = client_selector.get_client(client_name)
        if not client:
            self.logger.error(f"Client {client_name} not available for seeding monitor")
            return
        
        try:
            # Poll client for seeding status
            try:
                status = client.get_status(client_id)
            except ValueError:
                self.logger.info(
                    "Torrent %s not found while monitoring download %s; assuming seeding finished",
                    client_id,
                    download_id
                )
                self._complete_seeding_transition(download_id, download)
                return
            
            if not status:
                self.logger.warning(f"No status from client for download {download_id}")
                return
            
            # Check if torrent is still active/seeding
            state_value = str(status.get('state') or '').lower()
            is_seeding = state_value in self.ACTIVE_SEEDING_STATES
            is_complete = (status.get('progress', 0) or 0) >= 100.0
            
            # Get seeding metrics
            ratio = status.get('ratio', 0.0)
            seeding_time = status.get('seeding_time', 0)  # seconds
            
            # Log seeding progress
            self.logger.debug(
                f"Download {download_id} seeding: ratio={ratio:.2f}, "
                f"time={seeding_time}s, state={status.get('state')}"
            )
            
            # Update seeding metrics in database
            try:
                queue_manager.update_download(download_id, {
                    'seeding_ratio': ratio,
                    'seeding_time_seconds': seeding_time
                })
            except Exception as update_error:
                self.logger.debug(
                    "Skipping seeding metric update for download %s: %s",
                    download_id,
                    update_error
                )
            self._cache_download(download_id, download)
            
            # Check if client has marked torrent as complete
            # This happens when client's seeding goals are met (ratio, time, etc.)
            # Different clients use different fields to indicate completion
            client_marked_complete = False
            completion_reason = None
            if hasattr(client, 'is_seeding_complete'):
                client_marked_complete = client.is_seeding_complete(status)
                if client_marked_complete:
                    completion_reason = 'client'
            else:
                if is_complete and not is_seeding:
                    client_marked_complete = True
                    completion_reason = 'fallback_state'

            if client_marked_complete:
                ratio_limit = status.get('seed_ratio_limit')
                time_limit = status.get('seed_time_limit_seconds')
                self.logger.info(
                    "Download %s seeding complete via %s (state=%s, ratio=%.2f/%s, time=%ss/%s, progress=%.2f)",
                    download_id,
                    completion_reason or 'unknown',
                    status.get('state'),
                    ratio,
                    self._format_ratio_limit(ratio_limit),
                    seeding_time,
                    self._format_time_limit(time_limit),
                    status.get('progress', 0.0)
                )
                self._complete_seeding_transition(
                    download_id,
                    download,
                    ratio=ratio,
                    seeding_time=seeding_time
                )
            
        except Exception as e:
            self.logger.error(f"Error monitoring seeding for download {download_id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _complete_seeding_transition(self, download_id: int, download: Dict[str, Any],
                                     ratio: float = 0.0, seeding_time: int = 0):
        """Shared helper to finish seeding workflow and cleanup."""
        state_machine = self._get_state_machine()
        if state_machine.transition(download_id, 'SEEDING_COMPLETE'):
            event_emitter = self._get_event_emitter()
            event_emitter.emit_state_changed(
                download_id,
                'SEEDING_COMPLETE',
                f'Seeding complete - ratio {ratio:.2f}, time {seeding_time}s'
            )
            self._handle_seeding_complete(download_id, download)

            queue_manager = self._get_queue_manager()
            try:
                queue_manager.delete_download(download_id)
                event_emitter.emit_queue_updated()
                self.logger.info(f"Download {download_id} removed from queue after seeding")
            except Exception as delete_error:
                self.logger.error(
                    f"Failed to delete download {download_id} after seeding complete: {delete_error}"
                )
            finally:
                self._last_known_downloads.pop(download_id, None)
    
    def _handle_seeding_complete(self, download_id: int, download: Dict[str, Any]):
        """
        Handle cleanup after seeding completes.
        
        Args:
            download_id: Download queue ID
            download: Download data dictionary
        """
        try:
            cleanup_manager = self._get_cleanup_manager()
            
            # Check if we should delete source files
            delete_source = download.get('delete_source', False)
            
            # Let cleanup manager remove torrents/temps with correct delete_files flag
            cleanup_manager.finalize_seeding(
                download_id,
                download,
                delete_files=delete_source
            )

            if delete_source:
                self.logger.debug(
                    f"Download {download_id} - deleted torrent data after seeding"
                )
            else:
                self.logger.debug(
                    f"Download {download_id} - kept source files, removed torrent reference"
                )

            self.logger.debug(f"Seeding cleanup complete for download {download_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling seeding complete for download {download_id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
