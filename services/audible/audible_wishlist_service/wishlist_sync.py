"""
Audible Wishlist Auto-Sync Service
==================================

Background service that automatically syncs Audible wishlist to local library
every 15 minutes, adding books with "Wanted" status.
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger("AuralArchiveLogger")

class WishlistSyncService:
    """Background service for automatic wishlist synchronization."""
    
    def __init__(self, recommendations_service, sync_interval_minutes: int = 15):
        """
        Initialize the wishlist sync service.
        
        Args:
            recommendations_service: Instance of AudibleRecommendationsService
            sync_interval_minutes: Minutes between sync attempts (default: 15)
        """
        self.recommendations_service = recommendations_service
        self.sync_interval = sync_interval_minutes * 60  # Convert to seconds
        self.running = False
        self.thread = None
        self.last_sync_time = None
        self.last_sync_result = None
        
    def start(self) -> bool:
        """Start the background sync service."""
        if self.running:
            logger.warning("Wishlist sync service is already running")
            return False
        
        try:
            self.running = True
            self.thread = threading.Thread(target=self._sync_loop, daemon=True)
            self.thread.start()
            logger.info(f"Wishlist sync service started (interval: {self.sync_interval // 60} minutes)")
            return True
        except Exception as e:
            logger.error(f"Failed to start wishlist sync service: {e}")
            self.running = False
            return False
    
    def stop(self) -> bool:
        """Stop the background sync service."""
        if not self.running:
            logger.warning("Wishlist sync service is not running")
            return False
        
        try:
            self.running = False
            if self.thread and self.thread.is_alive():
                logger.info("Stopping wishlist sync service...")
                # Give the thread a moment to finish current operation
                self.thread.join(timeout=5)
            logger.info("Wishlist sync service stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping wishlist sync service: {e}")
            return False
    
    def is_running(self) -> bool:
        """Check if the sync service is currently running."""
        return self.running and self.thread and self.thread.is_alive()
    
    def force_sync(self) -> Dict[str, Any]:
        """Force an immediate wishlist sync."""
        try:
            logger.info("Force syncing wishlist...")
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
        logger.info("Wishlist sync loop started")
        
        # Perform initial sync after 30 seconds to allow app to fully start
        time.sleep(30)
        
        while self.running:
            try:
                # Check if service is configured
                if not self.recommendations_service or not self.recommendations_service.is_configured():
                    logger.debug("Audible not configured, skipping wishlist sync")
                    time.sleep(60)  # Check again in 1 minute
                    continue
                
                # Perform sync
                logger.info("Performing scheduled wishlist sync...")
                result = self._perform_sync()
                self.last_sync_time = datetime.now()
                self.last_sync_result = result
                
                if result.get('success'):
                    added = result.get('added', 0)
                    updated = result.get('updated', 0)
                    if added > 0 or updated > 0:
                        logger.info(f"Wishlist sync: {added} new books added, {updated} updated")
                    else:
                        logger.debug("Wishlist sync: no changes")
                else:
                    logger.warning(f"Wishlist sync failed: {result.get('error', 'Unknown error')}")
                
            except Exception as e:
                logger.error(f"Error in wishlist sync loop: {e}")
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
        
        logger.info("Wishlist sync loop stopped")
    
    def _perform_sync(self) -> Dict[str, Any]:
        """Perform a single sync operation."""
        try:
            result = self.recommendations_service.sync_wishlist_to_library()
            result['sync_time'] = datetime.now().isoformat()
            return result
        except Exception as e:
            logger.error(f"Sync operation failed: {e}")
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
