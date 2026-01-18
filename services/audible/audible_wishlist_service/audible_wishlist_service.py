"""
Module Name: audible_wishlist_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Manage Audible wishlist integration and auto-sync; uses shared AudibleManager for auth and API calls.
Location:
    /services/audible/audible_wishlist_service/audible_wishlist_service.py

"""

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.logger import get_module_logger
from ..audible_service_manager import get_audible_manager

class AudibleWishlistService:
    """Service for managing Audible wishlist integration and auto-sync."""
    
    def __init__(self, config_service=None, sync_interval_minutes: int = 15, auto_start: bool = False, logger=None):
        """
        Initialize the Audible wishlist service.
        
        Args:
            config_service: Configuration service instance
            sync_interval_minutes: Minutes between sync attempts (default: 15)
            auto_start: Whether to automatically start sync on initialization (default: False)
        """
        self.logger = logger or get_module_logger("Service.Audible.Wishlist")
        self.config_service = config_service
        self.audible_manager = get_audible_manager(config_service)
        self.sync_interval = sync_interval_minutes * 60  # Convert to seconds
        self.running = False
        self.thread = None
        self.last_sync_time = None
        self.last_sync_result = None
        self._lock = threading.Lock()
        self._sync_in_progress = False  # Flag to prevent overlapping syncs
        self._series_service_ready = False
        
        self.logger.success(
            "Audible wishlist service started successfully",
            extra={"auto_start": auto_start, "interval_minutes": sync_interval_minutes},
        )
        
        # Auto-start sync if requested and service is configured
        if auto_start and self.audible_manager.is_configured():
            self.start_auto_sync("auto")
    
    def start_auto_sync(self, startup_context: str = "manual") -> bool:
        """Start the background auto-sync service.
        
        Args:
            startup_context: Context for logging - "manual", "startup", "auto"
        """
        with self._lock:
            if self.running:
                self.logger.warning("Wishlist auto-sync is already running", extra={"running": True})
                return False
            
            try:
                self.running = True
                self.thread = threading.Thread(target=self._sync_loop, daemon=True)
                self.thread.start()
                
                self.logger.success(
                    "Wishlist auto-sync started successfully",
                    extra={"context": startup_context, "interval_minutes": self.sync_interval // 60},
                )
                    
                return True
            except Exception as e:
                self.logger.error("Failed to start wishlist auto-sync", extra={"error": str(e)}, exc_info=True)
                self.running = False
                return False
    
    def stop_auto_sync(self) -> bool:
        """Stop the background auto-sync service."""
        with self._lock:
            if not self.running:
                self.logger.warning("Wishlist auto-sync is not running", extra={"running": False})
                return False
            
            try:
                self.running = False
                if self.thread and self.thread.is_alive():
                    self.logger.info("Stopping wishlist auto-sync", extra={"joining": True})
                    # Give the thread a moment to finish current operation
                    self.thread.join(timeout=5)
                self.logger.info("Wishlist auto-sync stopped", extra={"running": False})
                return True
            except Exception as e:
                self.logger.error("Error stopping wishlist auto-sync", extra={"error": str(e)}, exc_info=True)
                return False
    
    def is_auto_sync_running(self) -> bool:
        """Check if the auto-sync service is currently running."""
        return self.running and self.thread and self.thread.is_alive()
    
    def sync_now(self) -> Dict[str, Any]:
        """Perform an immediate wishlist sync."""
        # Check if a sync is already in progress
        with self._lock:
            if self._sync_in_progress:
                self.logger.warning(
                    "Wishlist sync already in progress; skipping manual request",
                    extra={"skipped": True},
                )
                return {
                    'success': False,
                    'error': 'Sync already in progress',
                    'sync_time': datetime.now().isoformat()
                }
            self._sync_in_progress = True
        
        try:
            if not self.audible_manager.is_configured():
                self.logger.warning("Manual wishlist sync blocked; Audible not configured", extra={"configured": False})
                return {
                    'success': False,
                    'error': 'Audible not configured'
                }
            
                self.logger.info("Manual wishlist sync initiated", extra={"manual": True})
            result = self.sync_wishlist_to_library()
            
            with self._lock:
                self.last_sync_time = datetime.now()
                self.last_sync_result = result
            
            if result.get('success'):
                added = result.get('added', 0)
                updated = result.get('updated', 0)
                skipped = result.get('skipped', 0)
                self.logger.info(
                    "Manual wishlist sync complete",
                    extra={"added": added, "updated": updated, "skipped": skipped},
                )
            else:
                self.logger.warning(
                    "Manual wishlist sync failed",
                    extra={"error": result.get('error', 'Unknown error')},
                )
            
            return result
            
        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e),
                'sync_time': datetime.now().isoformat()
            }
            
            with self._lock:
                self.last_sync_result = error_result
                
            self.logger.error("Manual wishlist sync failed", extra={"error": str(e)}, exc_info=True)
            return error_result
        finally:
            with self._lock:
                self._sync_in_progress = False
    
    def get_wishlist(self) -> Dict[str, Any]:
        """Get current wishlist items."""
        try:
            if not self.audible_manager.is_configured():
                return {
                    'success': False,
                    'error': 'Audible not configured',
                    'wishlist': []
                }
            
            wishlist_items = self._get_audible_wishlist()
            
            return {
                'success': True,
                'wishlist': wishlist_items,
                'count': len(wishlist_items)
            }
            
        except Exception as e:
            self.logger.error("Error getting wishlist", extra={"error": str(e)})
            return {
                'success': False,
                'error': str(e),
                'wishlist': []
            }
    
    def _get_audible_wishlist(self):
        """Get wishlist items from Audible API."""
        try:
            self.logger.debug("Fetching Audible wishlist")
            
            # Try different wishlist endpoints
            wishlist_endpoints = [
                "1.0/wishlist",
                "1.0/customer/wishlist",
                "1.0/library/wishlist"
            ]
            
            response = self.audible_manager.try_multiple_endpoints(
                wishlist_endpoints,
                num_results=50,
                response_groups=(
                    "contributors,media,price,product_attrs,product_desc,"
                    "product_extended_attrs,rating,series,relationships"
                )
            )
            
            if response:
                wishlist_items = response.get("items", []) or response.get("products", [])
                if wishlist_items:
                    self.logger.debug("Found wishlist items", extra={"count": len(wishlist_items)})
                    return [self._format_wishlist_item(item) for item in wishlist_items]
            
                self.logger.debug("Wishlist endpoints returned no items")
            return []
            
        except Exception as e:
            self.logger.error("Error fetching Audible wishlist", extra={"error": str(e)}, exc_info=True)
            return []
    
    def _format_wishlist_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Format wishlist item using the shared manager."""
        # Extract the actual book/product data
        book_data = item.get("product", item)
        
        formatted = self.audible_manager.format_book_data(book_data)
        normalized_series = self._normalize_series_value(formatted.get('series'))
        formatted['series'] = normalized_series
        formatted['Series'] = normalized_series
        formatted['source'] = 'audible_wishlist'
        formatted['status'] = 'Wanted'
        formatted['wishlist_date'] = item.get("date_added", "")
        
        return formatted
    
    def sync_wishlist_to_library(self) -> Dict[str, Any]:
        """Sync Audible wishlist to local library with 'Wanted' status."""
        try:
            import sqlite3
            import os
            
            # Get wishlist items
            wishlist_items = self._get_audible_wishlist()
            if not wishlist_items:
                return {
                    'success': True,
                    'added': 0,
                    'updated': 0,
                    'skipped': 0,
                    'message': 'No wishlist items found'
                }
            
            # Connect to database
            db_path = "database/auralarchive_database.db"
            if not os.path.exists(db_path):
                self.logger.error("Database not found", extra={"db_path": db_path})
                return {
                    'success': False,
                    'error': 'Database not found'
                }
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get all existing books to check for duplicates
            cursor.execute("SELECT asin, title, author FROM books WHERE asin IS NOT NULL OR (title IS NOT NULL AND author IS NOT NULL)")
            existing_books = cursor.fetchall()
            
            # Create lookup sets for faster duplicate detection
            existing_asins = {asin.lower() for asin, _, _ in existing_books if asin}
            existing_titles = {(title.lower().strip(), author.lower().strip()) for _, title, author in existing_books if title and author}
            
            added = 0
            updated = 0
            skipped = 0
            series_sync_asins = set()
            
            for item in wishlist_items:
                asin = item.get('asin', '').strip()
                title = item.get('title', '').strip()
                author = item.get('author', '').strip()
                series_value = self._normalize_series_value(item.get('series'))
                
                if not asin and not (title and author):
                    skipped += 1
                    self.logger.debug(
                        "Skipped wishlist item with no ASIN or title/author",
                        extra={"item": item},
                    )
                    continue
                
                # Check for duplicates
                is_duplicate = False
                
                # Check ASIN first (most reliable)
                if asin and asin.lower() in existing_asins:
                    is_duplicate = True
                    self.logger.debug("Skipped duplicate ASIN", extra={"title": title, "asin": asin})
                
                # Check title + author combination
                elif title and author and (title.lower(), author.lower()) in existing_titles:
                    is_duplicate = True
                    self.logger.debug(
                        "Skipped duplicate title/author",
                        extra={"title": title, "author": author},
                    )
                
                if is_duplicate:
                    skipped += 1
                    continue
                
                try:
                    # Check if book exists by ASIN (for status updates)
                    existing_book = None
                    if asin:
                        cursor.execute("SELECT id, status, series, COALESCE(series_asin, '') FROM books WHERE asin = ?", (asin,))
                        existing_book = cursor.fetchone()
                    
                    if existing_book:
                        book_id, current_status, current_series, current_series_asin = existing_book
                        needs_series_sync = False
                        if series_value:
                            existing_normalized = self._normalize_series_value(current_series)
                            if existing_normalized == '':
                                cursor.execute(
                                    "UPDATE books SET series = ? WHERE id = ?",
                                    (series_value, book_id)
                                )
                                needs_series_sync = True
                            elif not current_series_asin:
                                needs_series_sync = True
                        
                        # Only update if current status is not 'Owned' or 'Downloading'
                        if current_status.lower() not in ['owned', 'downloading']:
                            cursor.execute(
                                "UPDATE books SET status = 'Wanted' WHERE id = ?",
                                (book_id,)
                            )
                            updated += 1
                            self.logger.debug(
                                "Updated book status to Wanted",
                                extra={"title": title, "asin": asin},
                            )
                        else:
                            skipped += 1
                            self.logger.debug(
                                "Skipped updating book",
                                extra={"title": title, "status": current_status},
                            )

                        if needs_series_sync and asin:
                            series_sync_asins.add(asin)
                    else:
                        # Add new book from wishlist with proper source and ownership_status
                        cursor.execute("""
                            INSERT INTO books (
                                title, author, series, narrator, runtime, release_date,
                                language, publisher, overall_rating, status, asin, summary, cover_image,
                                source, ownership_status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            title or 'Unknown Title',
                            author or 'Unknown Author',
                                series_value,
                            item.get('narrator', 'Unknown Narrator'),
                            item.get('runtime', ''),
                            item.get('release_date', ''),
                            item.get('language', 'english'),
                            item.get('publisher', ''),
                            item.get('rating', ''),
                            'Wanted',  # Legacy status field
                            asin or None,
                            item.get('summary', ''),
                            item.get('cover_image', ''),
                            'audible',  # Source: from Audible wishlist
                            'wanted'    # Ownership status: user wants this book
                        ))
                        added += 1
                        self.logger.info(
                            "Added new book from wishlist",
                            extra={"title": title, "author": author, "asin": asin},
                        )
                        if asin:
                            series_sync_asins.add(asin)
                
                except Exception as e:
                    self.logger.error(
                        "Error processing wishlist item",
                        extra={"asin": asin or None, "title": title or None, "error": str(e)},
                        exc_info=True,
                    )
                    skipped += 1
                    continue
            
            conn.commit()
            conn.close()

            if series_sync_asins:
                self.logger.info(
                    "Scheduling series sync for wishlist titles",
                    extra={"count": len(series_sync_asins)},
                )
                for asin in series_sync_asins:
                    self._sync_series_for_book(asin)
            
            self.logger.info(
                "Wishlist sync complete",
                extra={"added": added, "updated": updated, "skipped": skipped, "processed": len(wishlist_items)},
            )
            
            return {
                'success': True,
                'added': added,
                'updated': updated,
                'skipped': skipped,
                'total_processed': len(wishlist_items),
                'message': f'Sync complete: {added} new books added, {updated} updated to Wanted status, {skipped} skipped'
            }
            
        except Exception as e:
            self.logger.error("Wishlist sync failed", extra={"error": str(e)}, exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _ensure_series_service_ready(self) -> bool:
        """Initialize the series service once so wishlist imports can sync metadata."""
        if self._series_service_ready:
            return True

        try:
            if not self.audible_manager or not self.audible_manager.is_configured():
                return False

            from services.service_manager import get_database_service

            db_service = get_database_service()
            if not db_service:
                return False

            self._series_service_ready = self.audible_manager.initialize_series_service(db_service)
            return self._series_service_ready
        except Exception as e:
            self.logger.debug("Unable to initialize series service for wishlist imports", extra={"error": str(e)})
            return False

    def _sync_series_for_book(self, asin: str):
        """Trigger a series sync for a specific ASIN if possible."""
        if not asin or not self._ensure_series_service_ready():
            return

        try:
            result = self.audible_manager.series_service.sync_book_series_by_asin(asin)
            if not result.get('success'):
                self.logger.debug(
                    "Series sync skipped",
                    extra={"asin": asin, "error": result.get('error', result.get('message'))},
                )
        except Exception as e:
            self.logger.warning(
                "Series sync failed for wishlist book",
                extra={"asin": asin, "error": str(e)},
                exc_info=True,
            )

    def _normalize_series_value(self, series_value: Optional[str]) -> str:
        """Normalize series strings and drop placeholder values."""
        if not series_value:
            return ''

        normalized = str(series_value).strip()
        if not normalized:
            return ''

        placeholder_values = {
            'n/a',
            'standalone',
            'none',
            'unknown',
            'unknown series'
        }

        return '' if normalized.lower() in placeholder_values else normalized
    
    def get_status(self) -> Dict[str, Any]:
        """Get current service status."""
        with self._lock:
            manager_status = self.audible_manager.get_service_status()
            
            return {
                **manager_status,
                'auto_sync_running': self.is_auto_sync_running(),
                'sync_interval_minutes': self.sync_interval // 60,
                'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
                'last_sync_result': self.last_sync_result,
                'next_sync_in_seconds': self._get_next_sync_seconds(),
                'service_configured': manager_status.get('configured', False)  # For backward compatibility
            }
    
    def update_sync_interval(self, minutes: int) -> bool:
        """Update the sync interval."""
        try:
            if minutes < 1:
                self.logger.warning("Sync interval must be at least 1 minute", extra={"requested": minutes})
                return False
            
            old_interval = self.sync_interval // 60
            self.sync_interval = minutes * 60
            
            self.logger.info(
                "Sync interval updated",
                extra={"previous_minutes": old_interval, "new_minutes": minutes},
            )
            return True
            
        except Exception as e:
            self.logger.error("Error updating sync interval", extra={"error": str(e)}, exc_info=True)
            return False
    
    def _sync_loop(self):
        """Main sync loop that runs in background thread."""
        # Loop start is already implied by the SUCCESS start log; keep this at debug to reduce noise
        self.logger.debug("Wishlist auto-sync loop started", extra={"interval_minutes": self.sync_interval // 60})
        
        # Wait for app to fully start
        time.sleep(30)
        
        while self.running:
            try:
                # Check if service is configured
                if not self.audible_manager.is_configured():
                    self.logger.debug("Audible not configured, skipping auto-sync")
                    time.sleep(60)  # Check again in 1 minute
                    continue
                
                # Check if a sync is already in progress
                with self._lock:
                    if self._sync_in_progress:
                        self.logger.debug("Sync already in progress, skipping scheduled sync")
                        time.sleep(60)  # Check again in 1 minute
                        continue
                    self._sync_in_progress = True
                
                try:
                    # Perform scheduled sync
                    self.logger.debug("Performing scheduled wishlist sync")
                    result = self.sync_wishlist_to_library()
                    
                    with self._lock:
                        self.last_sync_time = datetime.now()
                        self.last_sync_result = result
                    
                    if result.get('success'):
                        added = result.get('added', 0)
                        updated = result.get('updated', 0)
                        skipped = result.get('skipped', 0)
                        
                        if added > 0 or updated > 0:
                            self.logger.info(
                                "Scheduled wishlist sync",
                                extra={"added": added, "updated": updated, "skipped": skipped},
                            )
                        else:
                            self.logger.debug(
                                "Scheduled wishlist sync: no changes",
                                extra={"skipped": skipped},
                            )
                    else:
                        self.logger.warning(
                            "Scheduled wishlist sync failed",
                            extra={"error": result.get('error', 'Unknown error')},
                        )
                finally:
                    with self._lock:
                        self._sync_in_progress = False
                
            except Exception as e:
                self.logger.error("Error in wishlist auto-sync loop", extra={"error": str(e)}, exc_info=True)
                with self._lock:
                    self.last_sync_result = {
                        'success': False,
                        'error': str(e),
                        'sync_time': datetime.now().isoformat()
                    }
                    self._sync_in_progress = False  # Reset flag on error
            
            # Wait for next sync
            sleep_time = 0
            while sleep_time < self.sync_interval and self.running:
                time.sleep(min(10, self.sync_interval - sleep_time))  # Check every 10 seconds if we should stop
                sleep_time += 10
        self.logger.info("Wishlist auto-sync loop stopped")
        
    
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
# - Sync uses direct sqlite connections per run; move to shared DatabaseService for pooling and transactional consistency.
# - Duplicate detection loads all books into memory; switch to indexed queries or hash lookups from the DB layer.
# - Auto-sync loops poll every 10 seconds; consider event-driven scheduling and exponential backoff on failures.
# - Series sync triggering is per-asin; batch series syncs via the series service to avoid redundant API calls.

# Global service instance
_wishlist_service = None

def get_audible_wishlist_service(config_service=None, sync_interval_minutes: int = 15, auto_start: bool = False):
    """Get the global Audible wishlist service instance."""
    global _wishlist_service
    if _wishlist_service is None:
        _wishlist_service = AudibleWishlistService(
            config_service=config_service,
            sync_interval_minutes=sync_interval_minutes,
            auto_start=auto_start
        )
    return _wishlist_service
