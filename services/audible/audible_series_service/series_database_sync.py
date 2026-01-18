"""
Module Name: series_database_sync.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Persist series metadata and books into the database and cache covers when available.
Location:
    /services/audible/audible_series_service/series_database_sync.py

"""

from utils.logger import get_module_logger


class SeriesDatabaseSync:
    """Syncs series data to database."""
    
    def __init__(self, db_service, logger=None):
        """
        Initialize with database service
        
        Args:
            db_service: DatabaseService instance with series operations
        """
        self.logger = logger or get_module_logger("Service.Audible.Series.DatabaseSync")
        self.db = db_service
    
    def sync_series_metadata(self, series_data):
        """
        Sync series metadata to database
        
        Args:
            series_data: Dict containing series metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info(
                "Syncing series metadata",
                extra={"series_asin": series_data.get('series_asin'), "series_title": series_data.get('series_title')},
            )
            
            # The DatabaseService.series.upsert_series_metadata expects a dict
            result = self.db.series.upsert_series_metadata(series_data)
            
            if result:
                self.logger.info(
                    "Successfully synced series",
                    extra={"series_asin": series_data.get('series_asin')},
                )
            return result
            
        except Exception as e:
            self.logger.error(
                "Error syncing series metadata",
                extra={"series_asin": series_data.get('series_asin'), "error": str(e)},
                exc_info=True,
            )
            return False
    
    def sync_series_books(self, processed_books):
        """
        Sync series books to database with complete metadata and cache cover images
        
        Args:
            processed_books: List of processed book dicts with full metadata
            
        Returns:
            int: Number of books successfully synced
        """
        try:
            synced_count = 0
            
            for book in processed_books:
                try:
                    # Cache the cover image if available
                    cover_image_url = book.get('cover_image')
                    cached_cover_url = cover_image_url
                    
                    if cover_image_url:
                        try:
                            from services.image_cache import cache_book_cover
                            cached_url = cache_book_cover(cover_image_url)
                            if cached_url:
                                cached_cover_url = cached_url
                                self.logger.debug(
                                    "Cached cover for book",
                                    extra={"book_title": book.get('book_title'), "book_asin": book.get('book_asin')},
                                )
                        except Exception as e:
                            self.logger.warning(
                                "Failed to cache cover",
                                extra={"book_title": book.get('book_title'), "book_asin": book.get('book_asin'), "error": str(e)},
                            )
                    
                    # Prepare book data dict with ALL metadata fields
                    series_book_data = {
                        'series_asin': book.get('series_asin'),
                        'book_asin': book.get('book_asin'),
                        'book_title': book.get('book_title', ''),
                        'sequence': book.get('sequence'),
                        'sort_order': book.get('sort_order'),
                        'relationship_type': 'child',
                        'in_audiobookshelf': book.get('in_audiobookshelf', False),
                        # Add all metadata fields
                        'author': book.get('author'),
                        'narrator': book.get('narrator'),
                        'publisher': book.get('publisher'),
                        'release_date': book.get('release_date'),
                        'runtime': book.get('runtime'),
                        'rating': book.get('rating'),
                        'num_ratings': book.get('num_ratings'),
                        'summary': book.get('summary'),
                        'cover_image': cached_cover_url,  # Use cached URL
                        'language': book.get('language')
                    }
                    
                    result = self.db.series.upsert_series_book(series_book_data)
                    if result:
                        synced_count += 1
                except Exception as e:
                    self.logger.error(
                        "Error syncing series book",
                        extra={"book_asin": book.get('book_asin'), "error": str(e)},
                        exc_info=True,
                    )
                    continue
            
            self.logger.info(
                "Series book sync complete",
                extra={"synced": synced_count, "total": len(processed_books)},
            )
            return synced_count
            
        except Exception as e:
            self.logger.error("Error syncing series books", extra={"error": str(e)}, exc_info=True)
            return 0
    
    def update_book_series_asin(self, book_asin, series_asin):
        """
        Update the series_asin field for a book in the books table
        
        Args:
            book_asin: The book's ASIN
            series_asin: The series ASIN to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn, cursor = self.db.connect_db()
            cursor.execute(
                "UPDATE books SET series_asin = ? WHERE asin = ?",
                (series_asin, book_asin)
            )
            conn.commit()
            conn.close()
            
            self.logger.debug("Updated series_asin for book", extra={"book_asin": book_asin, "series_asin": series_asin})
            return True
            
        except Exception as e:
            self.logger.error(
                "Error updating book series_asin",
                extra={"book_asin": book_asin, "series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return False
