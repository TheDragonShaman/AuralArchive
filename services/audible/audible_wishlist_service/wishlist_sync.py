"""
Module Name: wishlist_sync.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Background service that syncs Audible wishlist entries into the local library on a schedule.
Location:
    /services/audible/audible_wishlist_service/wishlist_sync.py

"""

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from utils.logger import get_module_logger

class WishlistSyncService:
    """Background service for automatic wishlist synchronization."""
    
    def __init__(self, recommendations_service, sync_interval_minutes: int = 15, logger=None):
        """
        Initialize the wishlist sync service.
        
        Args:
            recommendations_service: Instance of AudibleRecommendationsService
            sync_interval_minutes: Minutes between sync attempts (default: 15)
        """
        self.logger = logger or get_module_logger("Service.Audible.Wishlist.Sync")
        self.recommendations_service = recommendations_service
        self.sync_interval = sync_interval_minutes * 60  # Convert to seconds
        self.running = False
        self.thread = None
        self.last_sync_time = None
        self.last_sync_result = None
        
    def start(self) -> bool:
        """Start the background sync service."""
        if self.running:
            self.logger.warning("Wishlist sync service is already running", extra={"running": True})
            return False
        
        try:
            self.running = True
            self.thread = threading.Thread(target=self._sync_loop, daemon=True)
            self.thread.start()
            self.logger.info(
                "Wishlist sync service started",
                extra={"interval_minutes": self.sync_interval // 60},
            )
            return True
        except Exception as e:
            self.logger.error("Failed to start wishlist sync service", extra={"error": str(e)}, exc_info=True)
            self.running = False
            return False
    
    def stop(self) -> bool:
        """Stop the background sync service."""
        if not self.running:
            self.logger.warning("Wishlist sync service is not running", extra={"running": False})
            return False
        
        try:
            self.running = False
            if self.thread and self.thread.is_alive():
                self.logger.info("Stopping wishlist sync service", extra={"joining": True})
                # Give the thread a moment to finish current operation
                self.thread.join(timeout=5)
            self.logger.info("Wishlist sync service stopped", extra={"running": False})
            return True
        except Exception as e:
            self.logger.error("Error stopping wishlist sync service", extra={"error": str(e)}, exc_info=True)
            return False
    
    def is_running(self) -> bool:
        """Check if the sync service is currently running."""
        return self.running and self.thread and self.thread.is_alive()
    
    def force_sync(self) -> Dict[str, Any]:
        """Force an immediate wishlist sync."""
        try:
            self.logger.info("Force syncing wishlist", extra={"forced": True})
            result = self._perform_sync()
            self.last_sync_time = datetime.now()
            self.last_sync_result = result
            return result
        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e),
                'sync_time': datetime.now().isoformat()
            }
            self.last_sync_result = error_result
            return error_result
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the sync service."""
        return {
            'running': self.is_running(),
            'sync_interval_minutes': self.sync_interval // 60,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'last_sync_result': self.last_sync_result,
            'next_sync_in_seconds': self._get_next_sync_seconds(),
            'service_configured': self.recommendations_service.is_configured() if self.recommendations_service else False
        }
    
    def _sync_loop(self):
        """Main sync loop that runs in background thread."""
        self.logger.info("Wishlist sync loop started", extra={"interval_minutes": self.sync_interval // 60})
        
        # Perform initial sync after 30 seconds to allow app to fully start
        time.sleep(30)
        
        while self.running:
            try:
                # Check if service is configured
                if not self.recommendations_service or not self.recommendations_service.is_configured():
                    self.logger.debug("Audible not configured, skipping wishlist sync")
                    time.sleep(60)  # Check again in 1 minute
                    continue
                
                # Perform sync
                self.logger.info("Performing scheduled wishlist sync", extra={"scheduled": True})
                result = self._perform_sync()
                self.last_sync_time = datetime.now()
                self.last_sync_result = result
                
                if result.get('success'):
                    added = result.get('added', 0)
                    updated = result.get('updated', 0)
                        if added > 0 or updated > 0:
                            self.logger.info(
                                "Wishlist sync completed",
                                extra={"added": added, "updated": updated, "status": "ok"},
                            )
                        else:
                            self.logger.debug("Wishlist sync: no changes", extra={"status": "no_change"})
                else:
                    self.logger.warning(
                        "Wishlist sync failed",
                        extra={"error": result.get('error', 'Unknown error'), "status": "failed"},
                    )
                
            except Exception as e:
                self.logger.error("Error in wishlist sync loop", extra={"error": str(e)}, exc_info=True)
                self.last_sync_result = {
                    'success': False,
                    'error': str(e),
                    'sync_time': datetime.now().isoformat()
                }
            
            # Wait for next sync
            sleep_time = 0
            while sleep_time < self.sync_interval and self.running:
                time.sleep(min(10, self.sync_interval - sleep_time))  # Check every 10 seconds if we should stop
                sleep_time += 10
        
        self.logger.info("Wishlist sync loop stopped", extra={"running": False})
    
    def _perform_sync(self) -> Dict[str, Any]:
        """Perform a single sync operation."""
        try:
            result = self.recommendations_service.sync_wishlist_to_library()
            result['sync_time'] = datetime.now().isoformat()
            return result
        except Exception as e:
            self.logger.error("Sync operation failed", extra={"error": str(e)}, exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'sync_time': datetime.now().isoformat()
            }
    
    def _get_next_sync_seconds(self) -> int:
        """Get seconds until next scheduled sync."""
        if not self.last_sync_time:
            return 0  # Will sync soon
        
        next_sync = self.last_sync_time + timedelta(seconds=self.sync_interval)
        now = datetime.now()
        
        if next_sync <= now:
            return 0
        
        return int((next_sync - now).total_seconds())


    # Performance follow-up:
    # - Sync loop polls every 10 seconds during sleep; consider event-driven wakeups or longer sleep slices to reduce CPU wakeups.
    # - Repeated calls to recommendations_service within the loop; add backoff and telemetry around consecutive failures.
    # - Cache wishlist diffs to avoid reprocessing unchanged lists and to reduce churn on the database/import pipeline.

# Global service instance
_wishlist_sync_service = None

def get_wishlist_sync_service(recommendations_service=None, sync_interval_minutes: int = 15):
    """Get the global wishlist sync service instance."""
    global _wishlist_sync_service
    if _wishlist_sync_service is None and recommendations_service:
        _wishlist_sync_service = WishlistSyncService(recommendations_service, sync_interval_minutes)
    return _wishlist_sync_service

def start_wishlist_sync_service(recommendations_service, sync_interval_minutes: int = 15) -> bool:
    """Start the global wishlist sync service."""
    service = get_wishlist_sync_service(recommendations_service, sync_interval_minutes)
    if service:
        return service.start()
    return False

def stop_wishlist_sync_service() -> bool:
    """Stop the global wishlist sync service."""
    service = get_wishlist_sync_service()
    if service:
        return service.stop()
    return False
