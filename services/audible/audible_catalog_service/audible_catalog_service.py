import logging
import threading
from typing import List, Dict, Optional, Any, Set, Tuple

from .catalog_search import AudibleSearch
from .formatting import AudibleFormatter
from .cover_utils import CoverImageUtils
from .error_handling import AudibleErrorHandler
from .author_scraper import AudibleAuthorScraper

class AudibleService:
    """Enhanced singleton service for Audible API operations with modular components"""
    
    _instance: Optional['AudibleService'] = None
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
                    self.logger = logging.getLogger("AudibleService.Main")
                    
                    # Initialize modular components
                    self.search = AudibleSearch()
                    self.formatter = AudibleFormatter()
                    self.cover_utils = CoverImageUtils()
                    self.error_handler = AudibleErrorHandler()
                    self.author_scraper = AudibleAuthorScraper()
                    
                    self.logger.info("AudibleService initialized successfully")
                    AudibleService._initialized = True
    
    def search_books(self, query: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """Search for books on Audible and return formatted results"""
        try:
            self.logger.info(f"Starting book search for: {query}")
            
            # Perform search using search module
            raw_results = self.search.search_books(query, region, num_results)
            
            if not raw_results:
                self.logger.warning(f"No results found for query: {query}")
                return []
            
            # Process results using formatter
            processed_books = self.formatter.process_search_results(raw_results, region)
            
            self.logger.info(f"Successfully processed {len(processed_books)} books for query: {query}")
            return processed_books
            
        except Exception as e:
            self.logger.error(f"Error in search_books for query '{query}': {e}")
            return []
    
    def get_book_details(self, asin: str, region: str = "us") -> Optional[Dict]:
        """Get detailed information for a specific book"""
        try:
            self.logger.info(f"Getting book details for ASIN: {asin}")
            
            # Get raw book data
            raw_book = self.search.get_book_details(asin, region)
            
            if not raw_book:
                self.logger.warning(f"No book found for ASIN: {asin}")
                return None
            
            # Process single book result
            processed_books = self.formatter.process_search_results([raw_book], region)
            
            if processed_books:
                book = processed_books[0]
                self.logger.info(f"Successfully retrieved details for: {book.get('Title', 'Unknown')}")
                return book
            else:
                self.logger.error(f"Failed to process book data for ASIN: {asin}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error getting book details for ASIN '{asin}': {e}")
            return None
    
    def search_by_author(self, author: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """Search for books by a specific author"""
        try:
            self.logger.info(f"Searching books by author: {author}")
            
            # Use specialized author search
            raw_results = self.search.search_by_author(author, region, num_results)
            
            if not raw_results:
                self.logger.warning(f"No books found for author: {author}")
                return []
            
            # Process results
            processed_books = self.formatter.process_search_results(raw_results, region)
            
            self.logger.info(f"Found {len(processed_books)} books by author: {author}")
            return processed_books
            
        except Exception as e:
            self.logger.error(f"Error searching by author '{author}': {e}")
            return []
    
    def search_by_series(self, series: str, region: str = "us", num_results: int = 25) -> List[Dict]:
        """Search for books in a specific series"""
        try:
            self.logger.info(f"Searching books in series: {series}")
            
            # Use specialized series search
            raw_results = self.search.search_by_series(series, region, num_results)
            
            if not raw_results:
                self.logger.warning(f"No books found in series: {series}")
                return []
            
            # Process results
            processed_books = self.formatter.process_search_results(raw_results, region)
            
            # Sort by sequence if available
            processed_books.sort(key=lambda x: self._parse_sequence(x.get('Sequence', 'N/A')))
            
            self.logger.info(f"Found {len(processed_books)} books in series: {series}")
            return processed_books
            
        except Exception as e:
            self.logger.error(f"Error searching by series '{series}': {e}")
            return []
    
    def get_cover_info(self, asin: str, book_data: Dict = None) -> Dict:
        """Get comprehensive cover image information for a book"""
        try:
            if book_data:
                return self.cover_utils.get_cover_info(book_data, asin)
            else:
                # If no book data provided, create minimal data for cover extraction
                minimal_data = {'asin': asin}
                return self.cover_utils.get_cover_info(minimal_data, asin)
            
        except Exception as e:
            self.logger.error(f"Error getting cover info for ASIN {asin}: {e}")
            return {
                'primary_url': self.cover_utils._get_placeholder_url(),
                'is_placeholder': True,
                'error': str(e)
            }
    
    def format_for_display(self, book_data: Dict) -> Dict:
        """Format book data for UI display"""
        try:
            return self.formatter.format_book_for_display(book_data)
        except Exception as e:
            self.logger.error(f"Error formatting book for display: {e}")
            return book_data
    
    def get_service_status(self) -> Dict:
        """Get comprehensive service status and API connectivity"""
        try:
            # Get API status
            api_status = self.search.get_api_status()
            
            # Get component status
            component_status = {
                'search_module': bool(self.search),
                'formatter_module': bool(self.formatter),
                'cover_utils_module': bool(self.cover_utils),
                'error_handler_module': bool(self.error_handler)
            }
            
            # Combine status information
            status = {
                'service_name': 'AudibleService',
                'initialized': self._initialized,
                'api_status': api_status,
                'components': component_status,
                'base_url': self.search.base_url if self.search else None
            }
            
            # Add performance info if available
            if hasattr(self.error_handler, 'last_request_time'):
                status['last_request_time'] = self.error_handler.last_request_time
                status['rate_limit_active'] = True
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {'error': str(e)}
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to Audible API"""
        try:
            self.logger.info("Testing Audible API connection...")
            
            # Perform a minimal search to test connectivity
            test_results = self.search_books("test", num_results=1)
            
            if test_results is not None:  # Empty list is also a valid response
                self.logger.info("Audible API connection test successful")
                return True, f"API accessible - test returned {len(test_results)} results"
            else:
                self.logger.error("Audible API connection test failed")
                return False, "API connection failed"
            
        except Exception as e:
            self.logger.error(f"Audible API connection test error: {e}")
            return False, f"Connection error: {str(e)}"
    
    def _parse_sequence(self, sequence: str) -> float:
        """Parse sequence string to float for sorting"""
        try:
            if sequence == 'N/A' or not sequence:
                return 999.0  # Put N/A at the end
            
            # Handle various sequence formats
            sequence_clean = sequence.replace('Book ', '').replace('#', '').strip()
            return float(sequence_clean)
        
        except (ValueError, TypeError):
            return 999.0
    
    def reset_service(self):
        """Reset the service (for testing or troubleshooting)"""
        with self._lock:
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("AudibleService reset")
    
    # Legacy method compatibility - maintain existing interface
    def get_book_by_asin(self, asin: str, region: str = "us") -> Optional[Dict]:
        """Legacy method name for get_book_details"""
        return self.get_book_details(asin, region)
    
    # Author-related methods
    
    def search_author_page(self, author_name: str) -> Optional[Dict]:
        """Search for an author's page on Audible and return author information"""
        try:
            self.logger.info(f"Searching for author: {author_name}")
            return self.author_scraper.search_author_page(author_name)
        
        except Exception as e:
            self.logger.error(f"Error searching for author {author_name}: {e}")
            return None
    
    def fetch_author_catalog(
        self,
        author_name: str,
        region: str = "us",
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch raw and formatted catalog data for an author without persistence."""

        self.logger.info(f"Fetching author catalog for: {author_name}")

        requested_results = limit if limit is not None else 200
        if requested_results <= 0:
            requested_results = 50

        raw_results: List[Dict[str, Any]] = []
        formatted_books: List[Dict[str, Any]] = []

        try:
            raw_results = self.search.search_by_author(
                author_name,
                region=region,
                num_results=requested_results,
                response_groups="contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships,customer_rights",
            )

            if raw_results:
                raw_results = self._filter_buyable_products(raw_results)

                if not raw_results:
                    self.logger.info(f"All catalog entries for {author_name} were filtered due to customer rights restrictions")
                    return [], []

                formatted_books = self.formatter.process_search_results(raw_results, region)

                if limit is not None:
                    formatted_books = formatted_books[:limit]
                    allowed_asins = {
                        book.get('ASIN')
                        for book in formatted_books
                        if book.get('ASIN')
                    }
                    if allowed_asins:
                        raw_results = [
                            product
                            for product in raw_results
                            if product.get('asin') in allowed_asins
                        ]

                return raw_results, formatted_books

            self.logger.info(
                f"Author search returned no results for {author_name}, attempting scraper fallback"
            )

            author_data = self.search_author_page(author_name)
            if author_data and 'books' in author_data:
                books = author_data.get('books', [])
                for book in books:
                    formatted_books.append({
                        'Title': book.get('title', ''),
                        'Author': author_name,
                        'Series': 'N/A',
                        'Sequence': 'N/A',
                        'ASIN': book.get('asin', ''),
                        'Cover Image': book.get('cover_image', ''),
                        'Runtime': book.get('runtime', ''),
                        'Overall Rating': book.get('rating', ''),
                        'Summary': '',
                        'Status': 'Available on Audible'
                    })

                if limit is not None:
                    formatted_books = formatted_books[:limit]

                return [], formatted_books

            self.logger.info(
                f"No author page found, falling back to keyword search for: {author_name}"
            )

            search_query = f"author:{author_name}"
            keyword_results = self.search_books(search_query, num_results=requested_results)

            if limit is not None:
                keyword_results = keyword_results[:limit]

            return [], keyword_results

        except Exception as exc:
            self.logger.error(f"Error fetching catalog for author {author_name}: {exc}")
            return [], []

    def _filter_buyable_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove products that are no longer purchasable on Audible."""
        filtered = []
        for product in products or []:
            if self._is_product_buyable(product):
                filtered.append(product)
            else:
                asin = product.get('asin')
                title = product.get('title') or product.get('product_title')
                self.logger.debug(f"Skipping unbuyable catalog entry: {title} ({asin})")
        return filtered

    def _is_product_buyable(self, product: Dict[str, Any]) -> bool:
        """Check Audible customer_rights fields for purchasability."""
        try:
            customer_rights = product.get('customer_rights') or {}
            is_buyable = product.get('is_buyable')
            if is_buyable is None:
                is_buyable = customer_rights.get('is_buyable')

            if is_buyable is False:
                return False

            product_state = product.get('product_state') or customer_rights.get('product_state')
            if product_state:
                normalized = str(product_state).strip().upper()
                unavailable_states = {
                    'NOT_FOR_SALE',
                    'NO_LONGER_AVAILABLE',
                    'UNAVAILABLE',
                    'UNAVAILABLE_FOR_PURCHASE',
                    'REMOVED',
                    'WITHDRAWN',
                    'ARCHIVED'
                }
                if normalized in unavailable_states:
                    return False

            return True

        except Exception as exc:
            self.logger.debug(f"Failed to evaluate catalog product purchasability: {exc}")
            return True
    def get_author_books_from_audible(
        self,
        author_name: str,
        region: str = "us",
        limit: Optional[int] = None,
        persist: bool = False
    ) -> List[Dict]:
        """Get all books by an author from Audible using the catalog API.

        Args:
            author_name: Author name used in the catalog lookup.
            region: Audible region code (currently informational).
            limit: Optional maximum number of items to return (API fetches a larger batch when None).
            persist: When True, upsert book and series data into the local database tables.

        Returns:
            List of formatted book dictionaries suitable for UI consumption.
        """
        try:
            raw_books, formatted_books = self.fetch_author_catalog(
                author_name,
                region=region,
                limit=limit
            )

            if persist and raw_books:
                self.persist_author_catalog(author_name, raw_books, formatted_books)

            if limit is not None and formatted_books:
                formatted_books = formatted_books[:limit]

            self.logger.info(
                f"Returning {len(formatted_books)} books for {author_name}"
            )
            return formatted_books

        except Exception as e:
            self.logger.error(f"Error getting books for author {author_name}: {e}")
            return []

    def persist_author_catalog(
        self,
        author_name: str,
        raw_books: List[Dict[str, Any]],
        formatted_books: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Persist author catalog results into the database for books and series tables."""
        try:
            from services.service_manager import get_database_service
        except Exception as import_error:
            self.logger.debug(f"Database persistence skipped (service manager unavailable): {import_error}")
            return {'books_successful': 0, 'books_failed': 0, 'series_successful': 0, 'series_failed': 0}

        db_service = get_database_service()
        if not db_service:
            self.logger.debug("DatabaseService not available; skipping persistence")
            return {'books_successful': 0, 'books_failed': 0, 'series_successful': 0, 'series_failed': 0}

        books_for_db = self._prepare_books_for_database(raw_books, formatted_books)
        books_successful = 0
        books_failed = 0
        if books_for_db:
            try:
                books_successful, books_failed = db_service.books.bulk_insert_or_update_books(books_for_db)
                self.logger.info(
                    f"Persisted {books_successful} author catalog entries for {author_name} (failed: {books_failed})"
                )
            except Exception as db_error:
                books_failed = len(books_for_db)
                self.logger.warning(f"Failed to persist author catalog for {author_name}: {db_error}")

        series_entries = self._prepare_series_entries(raw_books, formatted_books)
        series_successful = 0
        series_failed = 0
        if series_entries:
            for entry in series_entries:
                try:
                    db_service.series.upsert_series_book(entry)
                    series_successful += 1
                except Exception as series_error:
                    series_failed += 1
                    self.logger.debug(
                        f"Failed to upsert series mapping for {entry.get('book_asin')}: {series_error}"
                    )

        return {
            'books_successful': books_successful,
            'books_failed': books_failed,
            'series_successful': series_successful,
            'series_failed': series_failed,
        }

    def _prepare_books_for_database(
        self,
        raw_books: List[Dict[str, Any]],
        formatted_books: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Translate Audible catalog results into the normalized format expected by the books table"""

        formatted_lookup = {
            book.get('ASIN'): book
            for book in formatted_books
            if book.get('ASIN')
        }

        prepared: List[Dict[str, Any]] = []
        seen_asins: Set[str] = set()

        for product in raw_books:
            asin = product.get('asin')
            if not asin or asin in seen_asins:
                continue

            if not self._is_product_buyable(product):
                self.logger.debug(f"Skipping persistence for unbuyable catalog entry: {product.get('title')} ({asin})")
                continue

            seen_asins.add(asin)
            formatted = formatted_lookup.get(asin, {})

            author_value = formatted.get('Author') or self._format_contributor_names(product.get('authors'))
            if not author_value:
                author_value = 'Unknown Author'

            narrator_value = formatted.get('Narrator') or self._format_contributor_names(product.get('narrators'))
            if not narrator_value:
                narrator_value = 'Unknown Narrator'

            prepared.append({
                'asin': asin,
                'title': product.get('title') or formatted.get('Title') or 'Unknown Title',
                'author': author_value,
                'narrator': narrator_value,
                'runtime_length_min': product.get('runtime_length_min') or 0,
                'release_date': product.get('release_date') or formatted.get('Release Date'),
                'language': product.get('language') or formatted.get('Language'),
                'publisher': product.get('publisher_name') or formatted.get('Publisher'),
                'rating': self._extract_rating_value(product),
                'num_ratings': self._extract_num_ratings_from_product(product),
                'summary': formatted.get('Summary') or '',
                'cover_image_url': formatted.get('Cover Image') or '',
                'series_title': formatted.get('Series') or 'N/A',
                'series_sequence': formatted.get('Sequence') or 'N/A',
                'series_asin': formatted.get('series_asin'),
                'status': 'Wanted',
                'ownership_status': 'wanted',
                'source': 'audible_catalog',
            })

        return prepared

    def _prepare_series_entries(
        self,
        raw_books: List[Dict[str, Any]],
        formatted_books: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prepare series linkage data for the series_books table"""

        formatted_lookup = {
            book.get('ASIN'): book
            for book in formatted_books
            if book.get('ASIN') and book.get('series_asin')
        }

        raw_lookup = {
            book.get('asin'): book
            for book in raw_books
            if book.get('asin')
        }

        entries: List[Dict[str, Any]] = []

        for asin, formatted in formatted_lookup.items():
            series_asin = formatted.get('series_asin')
            if not series_asin:
                continue

            raw_product = raw_lookup.get(asin, {})
            sequence = formatted.get('Sequence', 'N/A')

            entries.append({
                'series_asin': series_asin,
                'book_asin': asin,
                'book_title': formatted.get('Title') or raw_product.get('title'),
                'sequence': sequence,
                'sort_order': self._normalize_sequence(sequence) or sequence,
                'relationship_type': 'child',
                'in_audiobookshelf': False,
                'author': formatted.get('Author'),
                'narrator': formatted.get('Narrator') or self._format_contributor_names(raw_product.get('narrators')),
                'publisher': formatted.get('Publisher') or raw_product.get('publisher_name'),
                'release_date': formatted.get('Release Date') or raw_product.get('release_date'),
                'runtime': raw_product.get('runtime_length_min') or 0,
                'rating': formatted.get('Overall Rating'),
                'num_ratings': formatted.get('num_ratings'),
                'summary': formatted.get('Summary'),
                'cover_image': formatted.get('Cover Image'),
                'language': formatted.get('Language') or raw_product.get('language'),
            })

        return entries

    def _extract_rating_value(self, product: Dict[str, Any]) -> Optional[float]:
        """Extract numeric rating value from Audible product data"""
        rating_info = product.get('rating') or {}

        if not isinstance(rating_info, dict):
            return None

        overall_dist = rating_info.get('overall_distribution') or {}
        if isinstance(overall_dist, dict):
            value = overall_dist.get('display_average_rating') or overall_dist.get('average_rating')
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                pass

        fallback_value = rating_info.get('overall_rating') or rating_info.get('rating')
        try:
            return float(fallback_value) if fallback_value is not None else None
        except (TypeError, ValueError):
            return None

    def _extract_num_ratings_from_product(self, product: Dict[str, Any]) -> int:
        """Extract number of ratings from Audible product data"""
        rating_info = product.get('rating') or {}

        if not isinstance(rating_info, dict):
            return 0

        overall_dist = rating_info.get('overall_distribution') or {}
        if isinstance(overall_dist, dict):
            try:
                ratings = overall_dist.get('num_ratings', 0)
                return int(ratings) if ratings is not None else 0
            except (TypeError, ValueError):
                return 0

        return 0

    def _format_contributor_names(self, contributors: Any) -> str:
        """Utility to convert contributor objects into a comma-separated name string"""
        if not contributors:
            return ''

        names = []
        for contributor in contributors:
            if isinstance(contributor, dict):
                name = contributor.get('name')
                if name:
                    names.append(name)
            elif isinstance(contributor, str):
                names.append(contributor)

        return ", ".join(names)

    def _normalize_sequence(self, sequence: Any) -> Optional[float]:
        """Attempt to normalize a sequence identifier into a sortable float"""
        if sequence is None:
            return None

        if isinstance(sequence, (int, float)):
            return float(sequence)

        try:
            cleaned = str(sequence).strip().lstrip('#').replace('Book', '').strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None
