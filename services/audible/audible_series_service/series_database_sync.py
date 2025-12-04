"""
Series Database Sync
Syncs series data to database using SeriesOperations
"""

from utils.logger import get_module_logger

LOGGER_NAME = "SeriesDatabaseSync"
logger = get_module_logger(LOGGER_NAME)


class SeriesDatabaseSync:
    """Syncs series data to database"""
    
    def __init__(self, db_service):
        """
        Initialize with database service
        
        Args:
            db_service: DatabaseService instance with series operations
        """
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
            logger.info(f"Syncing series metadata: {series_data.get('series_title')}")
            
            # The DatabaseService.series.upsert_series_metadata expects a dict
            result = self.db.series.upsert_series_metadata(series_data)
            
            if result:
                logger.info(f"Successfully synced series: {series_data.get('series_asin')}")
            return result
            
        except Exception as e:
            logger.error(f"Error syncing series metadata: {e}")
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
                                logger.debug(f"Cached cover for book: {book.get('book_title')}")
                        except Exception as e:
                            logger.warning(f"Failed to cache cover for {book.get('book_title')}: {e}")
                    
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
                    logger.error(f"Error syncing book {book.get('book_asin')}: {e}")
                    continue
            
            logger.info(f"Successfully synced {synced_count}/{len(processed_books)} books")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing series books: {e}")
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
            
            logger.debug(f"Updated series_asin for book {book_asin}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating book series_asin: {e}")
            return False
