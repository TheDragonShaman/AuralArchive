"""
Module Name: audible_metadata_sync_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Synchronize Audible library metadata to the database with API-based fetch, enrichment, and batching.
Location:
    /services/audible/audible_metadata_sync_service/audible_metadata_sync_service.py

"""

import threading
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Tuple, Callable
from utils.logger import get_module_logger

from services.database.database_service import DatabaseService
from services.image_cache.image_cache_service import ImageCacheService
from services.service_manager import get_config_service
from services.metadata.metadata_service import MetadataUpdateService

from .audible_api_helper import AudibleApiHelper
from .metadata_processor import MetadataProcessor


class SyncMode:
    """Sync mode constants following OpenAudible pattern"""
    QUICK = "quick"  # Only sync new/changed books (like OpenAudible's Quick_Refresh)
    FULL = "full"    # Full library sync (like OpenAudible's Rescan_Library)


class AudibleMetadataSyncService:
    """
    Service for efficiently synchronizing Audible library metadata with the database.
    
    Singleton pattern to prevent multiple expensive instances.
    
    Features:
    - Fetches library data from Audible Python API with pagination
    - Uses MetadataUpdateService for complete metadata enrichment
    - Parallel metadata processing using ThreadPoolExecutor
    - Intelligent caching and rate limiting
    - Progress tracking and real-time updates via SocketIO
    - Efficient database batch operations with ASIN primary key
    - Automatic image caching for covers
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, logger=None, socketio=None):
        """Singleton pattern - only create one instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AudibleMetadataSyncService, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, logger=None, socketio=None):
        """
        Initialize the metadata sync service (only once for singleton).
        
        Args:
            logger: Logger instance
            socketio: SocketIO instance for real-time updates
        """
        # Only initialize once
        if self._initialized:
            # Update socketio if provided
            if socketio is not None:
                self.socketio = socketio
            return
            
        self.logger = logger or get_module_logger("Service.Audible.MetadataSync")
        self.socketio = socketio
        
        # Initialize dependencies
        self.db_service = DatabaseService()
        self.image_cache = ImageCacheService()
        self.config_service = get_config_service()
        self.metadata_service = MetadataUpdateService()
        
        # Initialize helpers
        self.api_helper = AudibleApiHelper()
        self.metadata_processor = MetadataProcessor(logger=self.logger)
        
        # Sync state management
        self._sync_lock = threading.Lock()
        self._is_syncing = False
        self._sync_progress = {
            'total_books': 0,
            'processed_books': 0,
            'successful_books': 0,
            'failed_books': 0,
            'current_book': None,
            'start_time': None,
            'estimated_completion': None,
            'status': 'idle',
            'message': 'Ready to sync'
        }
        
        # Performance settings
        self.max_workers = 8  # Maximum concurrent threads
        self.batch_size = 20  # Books per database batch
        self.request_delay = 0.1  # Delay between API requests to avoid rate limiting
        self.cache_duration_hours = 6  # How long to consider cached data valid
        
        self._initialized = True
        self.logger.info("Audible Metadata Sync Service initialized (singleton)")
    
    @classmethod
    def get_instance(cls, logger=None, socketio=None):
        """Get the singleton instance"""
        return cls(logger=logger, socketio=socketio)
    
    def sync_library(self, mode: str = SyncMode.FULL, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Synchronize Audible library with database using specified mode.
        
        Following OpenAudible pattern:
        - QUICK: Only sync new/changed books (like Quick_Refresh)
        - FULL: Complete library sync (like Rescan_Library)
        
        Args:
            mode: Sync mode (QUICK or FULL)
            force_refresh: Force refresh even if recently synced
            
        Returns:
            Dictionary with sync results and statistics
        """
        with self._sync_lock:
            if self._is_syncing:
                return {
                    'success': False,
                    'error': 'Sync already in progress',
                    'progress': self._sync_progress.copy()
                }
            
            self._is_syncing = True
            self._reset_progress()
        
        try:
            start_time = datetime.now()
            self._sync_progress['start_time'] = start_time
            self._sync_progress['status'] = 'fetching_library'
            self._sync_progress['message'] = 'Fetching basic library from Audible API...'
            self._emit_progress_update()
            
            # Step 1: Get books to process based on sync mode
            if mode == SyncMode.QUICK:
                self.logger.info("Quick Sync: Fetching only outdated books")
                basic_library = self._get_quick_sync_books()
                sync_type = "Quick Sync"
            else:
                self.logger.info("Full Sync: Fetching complete library from Audible API")
                basic_library = self.api_helper.get_library_list()
                sync_type = "Full Sync"
            
            if not basic_library:
                if mode == SyncMode.QUICK:
                    # Quick sync with no books is OK - means nothing needs updating
                    return {
                        'success': True,
                        'message': 'Quick Sync complete - no books need updating',
                        'stats': {
                            'total_books': 0,
                            'processed_books': 0,
                            'successful_books': 0,
                            'failed_books': 0,
                            'sync_mode': mode,
                            'duration_seconds': 0
                        }
                    }
                else:
                    # Full sync with no books means API issue
                    raise Exception(f"Failed to fetch library for {sync_type}. Audible API may not be available or configured.")
            
            self._sync_progress['total_books'] = len(basic_library)
            self._sync_progress['status'] = 'processing_metadata'
            self._sync_progress['sync_mode'] = mode
            self._sync_progress['message'] = f'{sync_type}: Processing metadata for {len(basic_library)} books...'
            self._emit_progress_update()
            
            if not basic_library:
                return {
                    'success': True,
                    'message': 'No books found in library',
                    'stats': self._sync_progress.copy()
                }
            
            self.logger.info(
                "Processing books",
                extra={"book_count": len(basic_library), "max_workers": self.max_workers}
            )
            
            # Step 2: Process books in parallel batches with metadata enrichment
            processed_books = []
            failed_books = []
            
            # Process books in chunks to manage memory and database load
            for i in range(0, len(basic_library), self.batch_size):
                batch = basic_library[i:i + self.batch_size]
                batch_results = self._process_book_batch(batch, force_refresh)
                
                # Separate successful and failed results
                for result in batch_results:
                    if result['success']:
                        processed_books.append(result['book_data'])
                    else:
                        failed_books.append(result)
                
                # Update progress
                self._sync_progress['processed_books'] = len(processed_books) + len(failed_books)
                self._sync_progress['successful_books'] = len(processed_books)
                self._sync_progress['failed_books'] = len(failed_books)
                
                # Calculate estimated completion
                if self._sync_progress['processed_books'] > 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = self._sync_progress['processed_books'] / elapsed
                    remaining = self._sync_progress['total_books'] - self._sync_progress['processed_books']
                    eta_seconds = remaining / rate if rate > 0 else 0
                    self._sync_progress['estimated_completion'] = datetime.now() + timedelta(seconds=eta_seconds)
                
                self._sync_progress['message'] = f'Processed {self._sync_progress["processed_books"]}/{self._sync_progress["total_books"]} books...'
                self._emit_progress_update()
                
                # Small delay between batches to prevent overwhelming the system
                time.sleep(0.1)
            
            # Step 3: Bulk insert/update processed books into main books table
            if processed_books:
                self._sync_progress['status'] = 'saving_to_database'
                self._sync_progress['message'] = f'Saving {len(processed_books)} books to database...'
                self._emit_progress_update()
                
                self.logger.info(
                    "Saving books to database",
                    extra={"books": len(processed_books)}
                )
                # Persist a minimal audible_library row (includes purchase_date) for ownership validation
                try:
                    library_rows = []
                    for book in processed_books:
                        asin_value = book.get('asin')
                        if not asin_value:
                            continue
                        library_rows.append({
                            'asin': asin_value,
                            'title': book.get('title'),
                            'author': book.get('author'),
                            'authors': book.get('authors'),
                            'narrator': book.get('narrator'),
                            'narrators': book.get('narrators'),
                            'series_title': book.get('series_title'),
                            'series_sequence': book.get('series_sequence'),
                            'publisher': book.get('publisher'),
                            'release_date': book.get('release_date'),
                            'runtime_length_min': book.get('runtime_length_min'),
                            'summary': book.get('summary') or book.get('description'),
                            'genres': book.get('genres'),
                            'language': book.get('language'),
                            'rating': book.get('rating'),
                            'num_ratings': book.get('num_ratings'),
                            'purchase_date': book.get('purchase_date'),
                            'cover_image_url': book.get('cover_image_url'),
                            'local_cover_path': book.get('local_cover_path'),
                            'metadata_source': book.get('metadata_source'),
                            'sync_status': book.get('sync_status') or 'completed',
                        })
                    if library_rows:
                        try:
                            self.db_service.audible_library.bulk_insert_or_update_books(library_rows)
                        except Exception as lib_exc:
                            self.logger.debug(
                                "Audible library upsert skipped",
                                extra={"exc": lib_exc}
                            )
                except Exception as lib_wrap_exc:
                    self.logger.debug(
                        "Audible library row prep failed",
                        extra={"exc": lib_wrap_exc}
                    )
                successful_db, failed_db = self.db_service.books.bulk_insert_or_update_books(processed_books)
                
                self.logger.info(
                    "Database operations completed",
                    extra={"successful": successful_db, "failed": failed_db}
                )
            
            # Final results
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self._sync_progress['status'] = 'completed'
            self._sync_progress['message'] = 'Sync completed successfully'
            self._sync_progress['duration'] = duration
            self._emit_progress_update()
            
            # Emit completion event
            if self.socketio:
                self.socketio.emit('audible_sync_complete', {
                    'success': True,
                    'message': f'Library sync completed: {len(processed_books)} books processed',
                    'stats': self._sync_progress.copy()
                })
            
            result = {
                'success': True,
                'message': f'Sync completed successfully',
                'stats': {
                    'total_books': len(basic_library),
                    'processed_books': len(processed_books),
                    'failed_books': len(failed_books),
                    'duration_seconds': duration,
                    'books_per_second': len(processed_books) / duration if duration > 0 else 0,
                    'completion_time': end_time.isoformat()
                },
                'failed_asins': [f.get('asin') for f in failed_books if f.get('asin')]
            }
            
            self.logger.info(
                "Sync completed",
                extra=result['stats']
            )
            return result
            
        except Exception as exc:
            self.logger.error(
                "Library sync failed",
                extra={"exc": exc}
            )
            self._sync_progress['status'] = 'failed'
            self._sync_progress['error'] = str(exc)
            self._sync_progress['message'] = f'Sync failed: {exc}'
            self._emit_progress_update()
            
            return {
                'success': False,
                'error': str(exc),
                'progress': self._sync_progress.copy()
            }
        finally:
            self._is_syncing = False
    
    def _process_book_batch(self, books_batch: List[Dict], force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Process a batch of books using parallel threading.
        
        Args:
            books_batch: List of basic book dictionaries (asin, title, author)
            force_refresh: Force refresh cached data
            
        Returns:
            List of processing results
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(books_batch))) as executor:
            # Submit all books for processing
            future_to_book = {
                executor.submit(self._process_single_book, book, force_refresh): book 
                for book in books_batch
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_book):
                book = future_to_book[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    self.logger.error(
                        "Failed to process book",
                        extra={"asin": book.get('asin'), "exc": exc}
                    )
                    results.append({
                        'success': False,
                        'asin': book.get('asin'),
                        'error': str(exc)
                    })
        
        return results
    
    def _process_single_book(self, basic_book: Dict[str, str], force_refresh: bool = False) -> Dict[str, Any]:
        """
        Process a single book's metadata using MetadataUpdateService.
        
        Args:
            basic_book: Basic book data (asin, title, author) from API
            force_refresh: Force refresh cached data
            
        Returns:
            Processing result dictionary
        """
        try:
            asin = basic_book.get('asin')
            title = basic_book.get('title', '')
            author = basic_book.get('author', '')
            
            if not asin:
                return {
                    'success': False,
                    'error': 'No ASIN found'
                }
            
            # Update progress tracking
            self._sync_progress['current_book'] = title
            
            # Check if we need to update this book
            if not force_refresh:
                existing_book = self.db_service.audible_library.get_book_by_asin(asin)
                if existing_book and existing_book.get('last_updated'):
                    try:
                        last_update = datetime.fromisoformat(existing_book['last_updated'])
                        if datetime.now() - last_update < timedelta(hours=self.cache_duration_hours):
                            # Book is recently synced, skip unless forced
                            return {
                                'success': True,
                                'book_data': existing_book,
                                'cached': True
                            }
                    except (ValueError, TypeError):
                        # Invalid date format, proceed with refresh
                        pass
            
            # Use MetadataUpdateService to get full metadata
            self.logger.debug(
                "Getting metadata",
                extra={"asin": asin, "title": title}
            )
            
            # Ensure metadata service dependencies
            self.metadata_service._ensure_dependencies()
            
            # Search for book metadata using ASIN
            metadata = self.metadata_service.search_strategies.search_for_book_metadata(
                title=title,
                author=author,
                asin=asin
            )
            
            if not metadata:
                # Fallback to basic book info if metadata service fails
                self.logger.warning(
                    "No metadata found; using basic info",
                    extra={"asin": asin}
                )
                normalized_book = self.metadata_processor.create_basic_book_entry(basic_book)
            else:
                # Convert metadata to database format
                normalized_book = self.metadata_processor.normalize_metadata_to_db_format(metadata, asin)

            # Preserve purchase_date from the library payload for ownership validation
            purchase_date = basic_book.get('purchase_date')
            if purchase_date and 'purchase_date' not in normalized_book:
                normalized_book['purchase_date'] = self.metadata_processor._normalize_date(purchase_date)
            
            # Cache cover image if available
            cover_url = normalized_book.get('cover_image_url')
            if cover_url:
                try:
                    cached_cover_path = self.image_cache.get_cached_image_url(cover_url)
                    if cached_cover_path:
                        normalized_book['local_cover_path'] = cached_cover_path
                        self.logger.debug(
                            "Cached cover image",
                            extra={"asin": asin, "cover_path": cached_cover_path}
                        )
                except Exception as exc:
                    self.logger.warning(
                        "Failed to cache cover",
                        extra={"asin": asin, "exc": exc}
                    )
            
            # Add sync metadata
            normalized_book['last_updated'] = datetime.now().isoformat()
            normalized_book['sync_status'] = 'completed'
            normalized_book['metadata_source'] = 'metadata_service' if metadata else 'basic_api'
            
            # Add rate limiting delay
            time.sleep(self.request_delay)
            
            return {
                'success': True,
                'book_data': normalized_book,
                'cached': False
            }
            
        except Exception as exc:
            self.logger.error(
                "Error processing book",
                extra={"asin": basic_book.get('asin'), "exc": exc}
            )
            return {
                'success': False,
                'asin': basic_book.get('asin'),
                'error': str(exc)
            }
    
    def _get_quick_sync_books(self) -> List[Dict[str, Any]]:
        """
        Get books for quick sync - only new or outdated books.
        Following OpenAudible's Quick_Refresh pattern.
        
        Returns:
            List of basic book dictionaries that need syncing
        """
        try:
            # Get all books from API
            full_library = self.api_helper.get_library_list()
            if not full_library:
                self.logger.warning(
                    "API returned empty library; quick sync will refresh only outdated books",
                    extra={"cache_hours": self.cache_duration_hours}
                )
                
                # If API is not available, we can still do a limited quick sync
                # by just getting books from database that need refresh
                outdated_asins = self.db_service.audible_library.get_outdated_books(self.cache_duration_hours)
                
                if not outdated_asins:
                    self.logger.info(
                        "No outdated books found in database. Quick sync complete.",
                        extra={"cache_hours": self.cache_duration_hours}
                    )
                    return []
                
                # Get the outdated books from database to refresh their metadata
                outdated_books = []
                for asin in outdated_asins[:10]:  # Limit to 10 books for quick sync
                    book_data = self.db_service.audible_library.get_book_by_asin(asin)
                    if book_data:
                        # Convert database format to API format for processing
                        api_format = {
                            'asin': book_data.get('asin'),
                            'title': book_data.get('title'),
                            'author': book_data.get('author')
                        }
                        outdated_books.append(api_format)
                
                self.logger.info(
                    "Quick sync will refresh outdated books",
                    extra={"count": len(outdated_books)}
                )
                return outdated_books
            
            # Get outdated ASINs from database (books older than cache_duration_hours)
            outdated_asins = set(self.db_service.audible_library.get_outdated_books(self.cache_duration_hours))
            
            # Get ASINs already in database
            existing_asins = set(self.db_service.audible_library.get_all_asins())
            
            # Filter to only include books that are new or outdated
            books_to_sync = []
            for book in full_library:
                asin = book.get('asin')
                if not asin:
                    continue
                
                # Include if: new book (not in DB) or outdated book
                if asin not in existing_asins or asin in outdated_asins:
                    books_to_sync.append(book)
            
            self.logger.info(
                "Quick sync book selection",
                extra={
                    "to_process": len(books_to_sync),
                    "new": len(full_library) - len(existing_asins),
                    "outdated": len(outdated_asins)
                }
            )
            
            return books_to_sync
            
        except Exception as exc:
            self.logger.error(
                "Failed to get quick sync books",
                extra={"exc": exc}
            )
            return []
    
    def _reset_progress(self):
        """Reset progress tracking."""
        self._sync_progress = {
            'total_books': 0,
            'processed_books': 0,
            'successful_books': 0,
            'failed_books': 0,
            'current_book': None,
            'start_time': None,
            'estimated_completion': None,
            'status': 'starting',
            'message': 'Initializing sync...'
        }
    
    def _emit_progress_update(self):
        """Emit progress update via SocketIO."""
        if self.socketio:
            try:
                self.socketio.emit('audible_sync_progress', self._sync_progress)
            except Exception as exc:
                self.logger.warning(
                    "Failed to emit progress update",
                    extra={"exc": exc}
                )
    
    def get_sync_progress(self) -> Dict[str, Any]:
        """Get current sync progress."""
        return self._sync_progress.copy()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Return sync state and a copy of the current progress details."""
        with self._sync_lock:
            return {
                'is_syncing': self._is_syncing,
                'progress': self._sync_progress.copy()
            }

    def is_sync_needed(self) -> bool:
        """
        Check if a sync is needed based on the last sync time.
        
        Returns:
            True if sync is needed, False otherwise
        """
        try:
            # Check if any books are outdated
            outdated_asins = self.db_service.audible_library.get_outdated_books(self.cache_duration_hours)
            return len(outdated_asins) > 0
        except Exception as exc:
            self.logger.error(
                "Error checking sync status",
                extra={"exc": exc}
            )
            return True  # Default to needing sync if we can't determine