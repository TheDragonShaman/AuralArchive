import logging
import threading
from typing import List, Dict, Optional, Any, Tuple

from ..audible.audible_catalog_service.audible_catalog_service import AudibleService
from .audnexus_service import AudnexusService

class HybridAudiobookService:
    """
    Hybrid service that combines Audnexus and Audible APIs
    - Uses Audnexus for author-centric operations (better data, no rate limits)
    - Uses Audible API for general book search and discovery
    - Provides fallback mechanisms for robust operation
    """
    
    _instance: Optional['HybridAudiobookService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logging.getLogger("HybridAudiobookService")
                    
                    # Initialize both services
                    self.audnexus = AudnexusService()
                    self.audible = AudibleService()
                    
                    self.logger.info("HybridAudiobookService initialized successfully")
                    HybridAudiobookService._initialized = True
    
    # ========================================================================
    # AUTHOR OPERATIONS (Primary: Audnexus, Fallback: Audible)
    # ========================================================================
    
    def search_author_page(self, author_name: str, region: str = "us") -> Optional[Dict]:
        """
        Search for author information with Audnexus first, fallback to Audible.
        """
        try:
            self.logger.info(f"Searching for author: {author_name}")

            # Primary: Audnexus
            author_data = self.audnexus.find_author_by_name(author_name, region)

            if author_data:
                formatted_author = self.audnexus.format_author_for_compatibility(author_data)

                formatted_author['source'] = 'audnexus'
                formatted_author['audible_author_id'] = author_data.get('asin', '')
                formatted_author['total_books_count'] = 0
                formatted_author['audible_books_count'] = 0

                self.logger.info(f"Found author via Audnexus: {author_name}")
                return formatted_author

            # Fallback: Audible scraping
            self.logger.info(f"Audnexus failed, trying Audible for: {author_name}")
            audible_data = self.audible.search_author_page(author_name)

            if audible_data:
                audible_data['source'] = 'audible'
                self.logger.info(f"Found author via Audible: {author_name}")
                return audible_data

            self.logger.warning(f"Author not found in either service: {author_name}")
            return None

        except Exception as e:
            self.logger.error(f"Error searching for author '{author_name}': {e}")
            return None
    
    def get_author_books_from_audible(
        self,
        author_name: str,
        region: str = "us",
        enrich_with_audnexus: bool = False,
        limit: Optional[int] = None,
        persist_to_database: bool = False
    ) -> List[Dict]:
        """
        Get books by author using Audible as the primary data source
        
        Args:
            author_name: Author name to get books for
            region: Region code
            enrich_with_audnexus: Whether to enrich results with Audnexus metadata
            limit: Optional maximum number of results to return
            persist_to_database: Persist catalog results into books/series tables when True
            
        Returns:
            List of books by the author
        """
        try:
            self.logger.info(f"Getting books for author: {author_name}")
            
            # Use Audible API for book search (primary source)
            audible_books = self.audible.get_author_books_from_audible(
                author_name,
                region=region,
                limit=limit,
                persist=persist_to_database
            )

            if limit is not None:
                audible_books = audible_books[:limit]
            
            books = []
            
            # Enhance each book with Audnexus data if available
            for book in audible_books:
                if not enrich_with_audnexus or not book.get('ASIN'):
                    book.setdefault('enhanced_by', 'audible_only')
                    books.append(book)
                    continue

                try:
                    enhanced_book = self.audnexus.get_book_details(book['ASIN'], region)
                except Exception as enhancement_error:
                    self.logger.debug(f"Audnexus enhancement failed for {book.get('ASIN')}: {enhancement_error}")
                    enhanced_book = None
                
                if enhanced_book:
                    audnexus_formatted = self.audnexus.format_book_for_compatibility(enhanced_book)
                    book.update({k: v for k, v in audnexus_formatted.items() if v and v != 'N/A'})
                    book['enhanced_by'] = 'audnexus'
                else:
                    book['enhanced_by'] = 'audible_only'
                
                books.append(book)
            
            # Fallback: if Audible returned nothing, try limited Audnexus data
            if not books and enrich_with_audnexus:
                self.logger.info(f"Audible returned no books for {author_name}; attempting Audnexus fallback")
                author_details = self.audnexus.find_author_by_name(author_name, region)
                titles = author_details.get('titles', []) if author_details else []
                for title in titles:
                    formatted = self.audnexus.format_book_for_compatibility(title)
                    formatted['enhanced_by'] = 'audnexus_only'
                    books.append(formatted)
                if books:
                    self.logger.info(f"Audnexus fallback supplied {len(books)} titles for {author_name}")
            
            self.logger.info(f"Retrieved {len(books)} books for {author_name}")
            return books
            
        except Exception as e:
            self.logger.error(f"Error getting books for author '{author_name}': {e}")
            return []

    def fetch_author_catalog(
        self,
        author_name: str,
        region: str = "us",
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch raw and formatted catalog data directly from Audible."""

        return self.audible.fetch_author_catalog(author_name, region=region, limit=limit)
    
    # ========================================================================
    # BOOK OPERATIONS (Primary: Audible, Enhancement: Audnexus)
    # ========================================================================
    
    def search_books(self, query: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """
        Search for books using Audible API with Audnexus enhancement
        
        Args:
            query: Search query
            region: Region code
            num_results: Number of results to return
            
        Returns:
            List of books matching the query
        """
        try:
            self.logger.info(f"Searching books for: {query}")
            
            # Use Audible for general search capability
            books = self.audible.search_books(query, region, num_results)
            
            # Enhance results with Audnexus data where possible
            enhanced_books = []
            for book in books:
                if book.get('ASIN'):
                    # Try to enhance with Audnexus
                    audnexus_book = self.audnexus.get_book_details(book['ASIN'], region)
                    if audnexus_book:
                        audnexus_formatted = self.audnexus.format_book_for_compatibility(audnexus_book)
                        # Merge better data from Audnexus
                        book.update({k: v for k, v in audnexus_formatted.items() if v and v != 'N/A'})
                        book['enhanced_by'] = 'audnexus'
                    else:
                        book['enhanced_by'] = 'audible_only'
                
                enhanced_books.append(book)
            
            self.logger.info(f"Enhanced {len(enhanced_books)} books from search")
            return enhanced_books
            
        except Exception as e:
            self.logger.error(f"Error searching books for '{query}': {e}")
            return []
    
    def get_book_details(self, asin: str, region: str = "us") -> Optional[Dict]:
        """
        Get detailed book information, preferring Audnexus data
        
        Args:
            asin: Book ASIN
            region: Region code
            
        Returns:
            Detailed book information
        """
        try:
            self.logger.info(f"Getting book details for ASIN: {asin}")
            
            # Try Audnexus first for better data quality
            audnexus_book = self.audnexus.get_book_details(asin, region, seed_authors=True)
            
            if audnexus_book:
                book_data = self.audnexus.format_book_for_compatibility(audnexus_book)
                book_data['enhanced_by'] = 'audnexus'
                book_data['source'] = 'audnexus'
                self.logger.info(f"Retrieved book details from Audnexus: {book_data.get('Title', asin)}")
                return book_data
            
            # Fallback to Audible
            self.logger.info(f"Audnexus failed, trying Audible for: {asin}")
            audible_book = self.audible.get_book_details(asin, region)
            
            if audible_book:
                audible_book['enhanced_by'] = 'audible_only'
                audible_book['source'] = 'audible'
                self.logger.info(f"Retrieved book details from Audible: {audible_book.get('Title', asin)}")
                return audible_book
            
            self.logger.warning(f"Book not found in either service: {asin}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting book details for '{asin}': {e}")
            return None
    
    def search_by_author(self, author: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """
        Search for books by author using hybrid approach
        """
        return self.get_author_books_from_audible(author, region)
    
    def search_by_series(self, series: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """
        Search for books in a series using Audible API
        """
        try:
            # Use Audible for series search since Audnexus doesn't have this
            books = self.audible.search_by_series(series, region, num_results)
            
            # Enhance with Audnexus data
            enhanced_books = []
            for book in books:
                if book.get('ASIN'):
                    audnexus_book = self.audnexus.get_book_details(book['ASIN'], region)
                    if audnexus_book:
                        audnexus_formatted = self.audnexus.format_book_for_compatibility(audnexus_book)
                        book.update({k: v for k, v in audnexus_formatted.items() if v and v != 'N/A'})
                        book['enhanced_by'] = 'audnexus'
                    else:
                        book['enhanced_by'] = 'audible_only'
                
                enhanced_books.append(book)
            
            return enhanced_books
            
        except Exception as e:
            self.logger.error(f"Error searching series '{series}': {e}")
            return []
    
    # ========================================================================
    # SERVICE MANAGEMENT
    # ========================================================================
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to both services"""
        try:
            audnexus_ok, audnexus_msg = self.audnexus.test_connection()
            audible_ok, audible_msg = self.audible.test_connection()
            
            if audnexus_ok and audible_ok:
                return True, f"Both services OK - Audnexus: {audnexus_msg}, Audible: {audible_msg}"
            elif audnexus_ok:
                return True, f"Audnexus OK (primary), Audible issues: {audible_msg}"
            elif audible_ok:
                return True, f"Audible OK (fallback), Audnexus issues: {audnexus_msg}"
            else:
                return False, f"Both services failed - Audnexus: {audnexus_msg}, Audible: {audible_msg}"
                
        except Exception as e:
            return False, f"Service test error: {str(e)}"
    
    def get_service_status(self) -> Dict:
        """Get status of both services"""
        try:
            audnexus_status = self.audnexus.get_service_status()
            audible_status = self.audible.get_service_status()
            
            return {
                'service_name': 'HybridAudiobookService',
                'audnexus': audnexus_status,
                'audible': audible_status,
                'strategy': {
                    'authors': 'Audnexus primary, Audible fallback',
                    'books': 'Audible search, Audnexus enhancement',
                    'series': 'Audible only',
                    'general_search': 'Audible only'
                }
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_book_chapters(self, asin: str, region: str = "us") -> Optional[Dict]:
        """Get book chapters from Audnexus"""
        return self.audnexus.get_book_chapters(asin, region)
    
    # ========================================================================
    # LEGACY COMPATIBILITY
    # ========================================================================
    
    def get_book_by_asin(self, asin: str, region: str = "us") -> Optional[Dict]:
        """Legacy method name compatibility"""
        return self.get_book_details(asin, region)
    
    def format_for_display(self, book_data: Dict) -> Dict:
        """Format book data for UI display"""
        # Use existing Audible formatter if available
        try:
            return self.audible.format_for_display(book_data)
        except:
            return book_data
    
    def reset_service(self):
        """Reset both services"""
        with self._lock:
            try:
                self.audnexus.reset_service()
            except:
                pass
            try:
                self.audible.reset_service()
            except:
                pass
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("HybridAudiobookService reset")
