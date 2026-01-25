"""
Module Name: audible_series_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Sync Audible series metadata and books into the database using the shared Audible client.
Location:
    /services/audible/audible_series_service/audible_series_service.py

"""

from utils.logger import get_module_logger
from .series_relationship_extractor import SeriesRelationshipExtractor
from .series_data_fetcher import SeriesDataFetcher
from .series_book_processor import SeriesBookProcessor
from .series_database_sync import SeriesDatabaseSync


class AudibleSeriesService:
    """
    Main service for Audible series operations
    Orchestrates extraction, fetching, processing, and database sync
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - only one instance exists"""
        if cls._instance is None:
            cls._instance = super(AudibleSeriesService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, logger=None):
        """Initialize service components"""
        if self._initialized:
            return
        
        self.logger = logger or get_module_logger("Service.Audible.Series")
        self.extractor = SeriesRelationshipExtractor()
        self.fetcher = None  # Will be set when Audible client is available
        self.processor = None  # Will be set when database service is available
        self.sync = None  # Will be set when database service is available
        
        self._initialized = True
        self.logger.debug("Series service instantiated", extra={"instance_id": id(self)})
    
    def initialize(self, audible_client, db_service):
        """
        Initialize with required dependencies
        
        Args:
            audible_client: Authenticated Audible API client
            db_service: DatabaseService instance
        """
        self.fetcher = SeriesDataFetcher(audible_client)
        self.processor = SeriesBookProcessor(db_service)
        self.sync = SeriesDatabaseSync(db_service)
        self.logger.debug(
            "Series service dependencies initialized",
            extra={"audible_client": bool(audible_client), "db_service": bool(db_service)},
        )
    
    def sync_book_series(self, book_asin, book_metadata):
        """
        Sync series data for a single book
        
        Args:
            book_asin: The book's ASIN
            book_metadata: Full book metadata from Audible API (with relationships)
            
        Returns:
            dict: Result containing success status and series info
        """
        try:
            self.logger.info("Starting series sync for book", extra={"book_asin": book_asin})
            
            # Step 1: Extract series ASIN from book relationships
            series_metadata = self.extractor.extract_series_metadata(book_metadata)
            if not series_metadata:
                self.logger.info("No series found for book", extra={"book_asin": book_asin})
                return {'success': True, 'message': 'Book is not part of a series', 'series_count': 0}
            
            series_asin = series_metadata.get('series_asin')
            
            # Step 2: Fetch complete series data from Audible
            series_data = self.fetcher.fetch_series_metadata(series_asin)
            if not series_data:
                self.logger.error("Failed to fetch series data", extra={"series_asin": series_asin})
                return {'success': False, 'error': 'Failed to fetch series data'}
            
            # Step 3: Fetch all books in the series
            books_data = self.fetcher.fetch_series_books(series_asin)
            
            # Step 4: Process books (add library status)
            processed_books = self.processor.process_series_books(series_asin, books_data)
            
            # Step 5: Sync to database
            metadata_synced = self.sync.sync_series_metadata(series_data)
            books_synced = self.sync.sync_series_books(processed_books)
            
            # Step 6: Update book's series_asin field
            self.sync.update_book_series_asin(book_asin, series_asin)
            
            # Calculate stats
            stats = self.processor.calculate_series_stats(processed_books)
            
            self.logger.info(
                "Series sync complete",
                extra={"series_asin": series_asin, "books_synced": books_synced},
            )
            
            return {
                'success': True,
                'series_asin': series_asin,
                'series_title': series_data.get('series_title'),
                'books_synced': books_synced,
                'series_count': 1,
                'stats': stats
            }
            
        except Exception as e:
            self.logger.error(
                "Error syncing book series",
                extra={"book_asin": book_asin, "error": str(e)},
                exc_info=True,
            )
            return {'success': False, 'error': str(e)}
    
    def sync_book_series_by_asin(self, book_asin):
        """
        Fetch book metadata and sync series data for a single book
        Convenience method that handles the metadata fetching internally
        
        Args:
            book_asin: ASIN of the book
            
        Returns:
            dict: Result with series data and sync status
        """
        try:
            self.logger.info(
                "Fetching book metadata for series sync",
                extra={"book_asin": book_asin},
            )
            
            # Fetch book metadata to get series info
            book_metadata = self.fetcher.fetch_book_metadata(book_asin)
            
            if not book_metadata:
                self.logger.error(
                    "Failed to fetch metadata for book",
                    extra={"book_asin": book_asin},
                )
                return {'success': False, 'error': 'Failed to fetch book metadata', 'series_count': 0}
            
            # Use main sync method
            result = self.sync_book_series(book_asin, book_metadata)
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Error in sync_book_series_by_asin",
                extra={"book_asin": book_asin, "error": str(e)},
                exc_info=True,
            )
            return {'success': False, 'error': str(e), 'series_count': 0}
    
    def sync_series_by_series_asin(self, series_asin):
        """
        Sync a series directly using its series ASIN
        More efficient than fetching book metadata first
        
        Args:
            series_asin: ASIN of the series itself
            
        Returns:
            dict: Result with series data and sync status
        """
        try:
            self.logger.info("Starting direct series sync", extra={"series_asin": series_asin})
            
            # Step 1: Fetch complete series data from Audible
            series_data = self.fetcher.fetch_series_metadata(series_asin)
            if not series_data:
                self.logger.error("Failed to fetch series data", extra={"series_asin": series_asin})
                return {'success': False, 'error': 'Failed to fetch series data'}
            
            # Step 2: Fetch all books in the series
            books_data = self.fetcher.fetch_series_books(series_asin)
            
            # Step 3: Process books (add library status)
            processed_books = self.processor.process_series_books(series_asin, books_data)
            
            # Step 4: Sync to database
            metadata_synced = self.sync.sync_series_metadata(series_data)
            books_synced = self.sync.sync_series_books(processed_books)
            
            # Step 5: Calculate stats
            stats = self.processor.calculate_series_stats(processed_books)
            
            self.logger.info(
                "Series sync complete",
                extra={"series_asin": series_asin, "books_synced": books_synced},
            )
            
            return {
                'success': True,
                'series_asin': series_asin,
                'series_title': series_data.get('series_title'),
                'books_synced': books_synced,
                'series_count': 1,
                'stats': stats
            }
            
        except Exception as e:
            self.logger.error(
                "Error syncing series",
                extra={"series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return {'success': False, 'error': str(e)}
    
    def sync_all_series(self, limit=None):
        """
        Sync series data for all unique series in the library
        Now that books have series_asin populated during add/import, this is efficient
        
        Args:
            limit: Optional limit on number of series to process
            
        Returns:
            dict: Summary of sync operation
        """
        try:
            self.logger.info(
                "Starting batch series sync for all library series",
                extra={"limit": limit},
            )
            
            # Get all unique series ASINs from books that have them
            series_asins = self.sync.db.series.get_all_series_asins(limit=limit)
            
            if not series_asins:
                self.logger.info(
                    "No books with series information found in library",
                    extra={"limit": limit},
                )
                return {
                    'success': True,
                    'message': 'No series found in library',
                    'series_processed': 0
                }
            
            total_series = len(series_asins)
            successful = 0
            failed = 0
            results = []
            
            self.logger.info("Found unique series to sync", extra={"count": total_series})
            
            # Process each series
            for idx, series_asin in enumerate(series_asins, 1):
                try:
                    self.logger.info(
                        "Syncing series",
                        extra={"index": idx, "total": total_series, "series_asin": series_asin},
                    )
                    # Use direct series sync instead of book-based sync
                    result = self.sync_series_by_series_asin(series_asin)
                    
                    if result.get('success'):
                        successful += 1
                        results.append({
                            'series_asin': series_asin,
                            'series_title': result.get('series_title', 'Unknown'),
                            'status': 'success',
                            'books_synced': result.get('books_synced', 0)
                        })
                    else:
                        failed += 1
                        results.append({
                            'series_asin': series_asin,
                            'status': 'failed',
                            'error': result.get('error', 'Unknown error')
                        })
                        
                except Exception as e:
                    self.logger.error(
                        "Error syncing series in batch",
                        extra={"series_asin": series_asin, "error": str(e)},
                        exc_info=True,
                    )
                    failed += 1
                    results.append({
                        'series_asin': series_asin,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            self.logger.info(
                "Batch series sync complete",
                extra={"successful": successful, "failed": failed, "total": total_series},
            )
            
            return {
                'success': True,
                'message': f'Synced {successful} of {total_series} series',
                'total_series': total_series,
                'successful': successful,
                'failed': failed,
                'results': results
            }
            
        except Exception as e:
            self.logger.error(
                "Error in batch series sync",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {'success': False, 'error': str(e)}
    
    def refresh_series(self, series_asin):
        """
        Refresh data for a specific series
        
        Args:
            series_asin: The series ASIN to refresh
            
        Returns:
            dict: Result of refresh operation
        """
        try:
            self.logger.info("Refreshing series", extra={"series_asin": series_asin})
            
            # Fetch fresh data from Audible
            series_data = self.fetcher.fetch_series_metadata(series_asin)
            if not series_data:
                return {'success': False, 'error': 'Failed to fetch series data'}
            
            books_data = self.fetcher.fetch_series_books(series_asin)
            processed_books = self.processor.process_series_books(series_asin, books_data)
            
            # Sync to database
            self.sync.sync_series_metadata(series_data)
            books_synced = self.sync.sync_series_books(processed_books)
            
            stats = self.processor.calculate_series_stats(processed_books)
            
            return {
                'success': True,
                'series_title': series_data.get('series_title'),
                'books_synced': books_synced,
                'stats': stats
            }
            
        except Exception as e:
            self.logger.error(
                "Error refreshing series",
                extra={"series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return {'success': False, 'error': str(e)}
