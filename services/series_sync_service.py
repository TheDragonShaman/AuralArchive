"""
Series Sync Service - Fetches and syncs series data from Audible API
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class SeriesSyncService:
    """Service for syncing series data from Audible API"""
    
    def __init__(self, audible_client, database_service):
        """
        Initialize the series sync service
        
        Args:
            audible_client: Authenticated Audible API client
            database_service: Database service instance
        """
        self.client = audible_client
        self.db = database_service
        self.logger = logging.getLogger("SeriesSyncService")
    
    def extract_series_from_relationships(self, product_data: Dict) -> Optional[Dict]:
        """
        Extract series information from product relationships
        
        Args:
            product_data: Product data from Audible API with relationships response group
            
        Returns:
            Dict with series info or None if no series found
        """
        try:
            relationships = product_data.get('relationships', [])
            
            for relationship in relationships:
                if relationship.get('relationship_type') == 'series':
                    return {
                        'series_asin': relationship.get('asin'),
                        'series_title': relationship.get('title'),
                        'series_url': relationship.get('url'),
                        'sku': relationship.get('sku'),
                        'sku_lite': relationship.get('sku_lite'),
                        'sequence': relationship.get('sequence'),
                        'sort_order': relationship.get('sort')
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting series from relationships: {e}")
            return None
    
    def fetch_series_books(self, series_asin: str) -> Tuple[bool, List[Dict], str]:
        """
        Fetch all books in a series from Audible API
        
        Args:
            series_asin: The ASIN of the series
            
        Returns:
            Tuple of (success, books_list, error_message)
        """
        try:
            self.logger.info(f"Fetching series books for ASIN: {series_asin}")
            
            # Query Audible API for the series product
            # This will return all child books in the relationships
            params = {
                'asin': series_asin,
                'response_groups': 'contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships'
            }
            
            response = self.client.get(
                f"1.0/catalog/products/{series_asin}",
                params=params
            )
            
            if response.status_code != 200:
                error_msg = f"API error: {response.status_code}"
                self.logger.error(error_msg)
                return False, [], error_msg
            
            product = response.json().get('product', {})
            
            # Extract series metadata
            series_metadata = {
                'series_asin': series_asin,
                'series_title': product.get('title', 'Unknown Series'),
                'series_url': f"/pd/{product.get('title', '').replace(' ', '-')}-Audiobook/{series_asin}",
                'sku': product.get('sku'),
                'sku_lite': product.get('sku_lite'),
                'description': product.get('publisher_summary', ''),
                'cover_url': None
            }
            
            # Extract cover URL if available
            if 'product_images' in product:
                images = product.get('product_images', {})
                series_metadata['cover_url'] = images.get('500') or images.get('1000') or images.get('2000')
            
            # Extract child books from relationships
            relationships = product.get('relationships', [])
            books = []
            
            for relationship in relationships:
                # Look for child books (not parent series)
                if relationship.get('relationship_to_product') == 'child' and \
                   relationship.get('content_delivery_type') in ['SingleASIN', 'MultiPartBook']:
                    
                    book_data = {
                        'book_asin': relationship.get('asin'),
                        'book_title': relationship.get('title'),
                        'sequence': relationship.get('sequence'),
                        'sort_order': relationship.get('sort'),
                        'relationship_type': 'child',
                        'url': relationship.get('url')
                    }
                    books.append(book_data)
            
            self.logger.info(f"Found {len(books)} books in series {series_metadata['series_title']}")
            
            return True, books, series_metadata
            
        except Exception as e:
            error_msg = f"Error fetching series books: {e}"
            self.logger.error(error_msg)
            return False, [], error_msg
    
    def sync_series(self, series_asin: str) -> Tuple[bool, str]:
        """
        Sync a complete series to the database
        
        Args:
            series_asin: The ASIN of the series to sync
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Fetch series data from Audible
            success, books, series_metadata = self.fetch_series_books(series_asin)
            
            if not success:
                return False, series_metadata  # series_metadata contains error message in this case
            
            # Upsert series metadata
            if not self.db.series.upsert_series_metadata(series_metadata):
                return False, "Failed to save series metadata"
            
            # Upsert all books in the series
            books_added = 0
            for book in books:
                book['series_asin'] = series_asin
                if self.db.series.upsert_series_book(book):
                    books_added += 1
            
            # Update book counts
            self.db.series.update_series_book_counts(series_asin)
            
            message = f"Synced series '{series_metadata['series_title']}': {books_added} books"
            self.logger.info(message)
            
            return True, message
            
        except Exception as e:
            error_msg = f"Error syncing series: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def sync_book_series(self, book_asin: str) -> Tuple[bool, str]:
        """
        Sync series data for a specific book
        
        Args:
            book_asin: The ASIN of the book
            
        Returns:
            Tuple of (success, message)
        """
        try:
            self.logger.info(f"Syncing series for book: {book_asin}")
            
            # Fetch book metadata with relationships
            params = {
                'asin': book_asin,
                'response_groups': 'contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships'
            }
            
            response = self.client.get(
                f"1.0/catalog/products/{book_asin}",
                params=params
            )
            
            if response.status_code != 200:
                return False, f"API error: {response.status_code}"
            
            product = response.json().get('product', {})
            
            # Extract series info from relationships
            series_info = self.extract_series_from_relationships(product)
            
            if not series_info:
                return False, "No series found for this book"
            
            series_asin = series_info['series_asin']
            
            # Update the book's series_asin in the books table
            self.db.series.update_book_series_asin(book_asin, series_asin)
            
            # Sync the entire series
            success, message = self.sync_series(series_asin)
            
            if success:
                # Mark this book as owned in series_books
                self.db.series.mark_series_book_as_owned(series_asin, book_asin)
            
            return success, message
            
        except Exception as e:
            error_msg = f"Error syncing book series: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def sync_all_books_series(self, limit: Optional[int] = None) -> Tuple[int, int, List[str]]:
        """
        Sync series data for all books in the library
        
        Args:
            limit: Optional limit on number of books to process
            
        Returns:
            Tuple of (successful_syncs, failed_syncs, error_messages)
        """
        try:
            # Get all books from library that have ASINs
            books = self.db.get_all_books()
            
            if limit:
                books = books[:limit]
            
            successful = 0
            failed = 0
            errors = []
            processed_series = set()  # Track which series we've already synced
            
            self.logger.info(f"Starting series sync for {len(books)} books")
            
            for book in books:
                book_asin = book.get('asin')
                
                if not book_asin or book_asin == 'N/A':
                    continue
                
                try:
                    # Check if book already has series_asin
                    if book.get('series_asin') and book['series_asin'] in processed_series:
                        # Series already processed, just mark book as owned
                        self.db.series.mark_series_book_as_owned(book['series_asin'], book_asin)
                        successful += 1
                        continue
                    
                    # Sync this book's series
                    success, message = self.sync_book_series(book_asin)
                    
                    if success:
                        successful += 1
                        if book.get('series_asin'):
                            processed_series.add(book['series_asin'])
                    else:
                        failed += 1
                        errors.append(f"{book.get('title', book_asin)}: {message}")
                    
                except Exception as e:
                    failed += 1
                    error_msg = f"{book.get('title', book_asin)}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(error_msg)
            
            self.logger.info(f"Series sync complete: {successful} successful, {failed} failed")
            
            return successful, failed, errors
            
        except Exception as e:
            error_msg = f"Error in bulk series sync: {e}"
            self.logger.error(error_msg)
            return 0, 0, [error_msg]
    
    def sync_library_status(self) -> int:
        """
        Update in_library status for all series books based on current library
        
        Returns:
            Number of records updated
        """
        try:
            updated = self.db.series.sync_library_status()
            self.logger.info(f"Synced library status for {updated} series books")
            return updated
            
        except Exception as e:
            self.logger.error(f"Error syncing library status: {e}")
            return 0
