"""
Module Name: audnexus_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Access the Audnexus API for author and book metadata with structured logging and fallbacks.
Location:
    /services/audnexus/audnexus_service.py

"""

import requests
import threading
from typing import List, Dict, Optional, Any
from datetime import datetime

from utils.logger import get_module_logger

class AudnexusService:
    """
    Service for interacting with the Audnexus API
    Provides author search, author details, and book metadata
    """
    
    _instance: Optional['AudnexusService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, logger=None):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logger or get_module_logger("Service.Audnexus.Service")
                    self.base_url = "https://api.audnex.us"
                    # Keep connect/read timeouts short so UI doesn't hang on upstream slowness
                    self.request_timeout = (5, 8)  # (connect, read)
                    self.session = self._setup_session()
                    self.logger.success("Audnexus service started successfully")
                    AudnexusService._initialized = True
    
    def _setup_session(self) -> requests.Session:
        """Setup requests session with proper headers"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "AuralArchive/1.0 (Python Requests)",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        return session
    
    def search_authors(self, name: str, region: str = "us", num_results: int = 20) -> List[Dict]:
        """
        Search for authors by name
        
        Args:
            name: Author name to search for
            region: Region code (us, uk, ca, etc.)
            num_results: Maximum number of results to return (for compatibility)
            
        Returns:
            List of author objects with basic information
        """
        try:
            self.logger.info("Searching authors", extra={"author_name": name, "region": region})
            
            params = {
                "name": name,
                "region": region
            }
            
            response = self.session.get(
                f"{self.base_url}/authors",
                params=params,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                authors = response.json()
                self.logger.info("Author search succeeded", extra={"author_name": name, "result_count": len(authors)})
                # Limit results to num_results for compatibility
                return authors[:num_results] if num_results else authors
            elif response.status_code == 400:
                self.logger.warning("Bad request for author search", extra={"author_name": name, "region": region})
                return []
            else:
                body_preview = response.text[:200] if response.text else ''
                self.logger.error(
                    "Author search failed",
                    extra={
                        'status_code': response.status_code,
                        'author_name': name,
                        'body': body_preview
                    }
                )
                return []
                
        except Exception as exc:
            self.logger.error(
                "Error searching authors",
                extra={"author_name": name, "exc": exc}
            )
            return []
    
    def get_author_details(self, asin: str, region: str = "us", update: bool = False) -> Optional[Dict]:
        """
        Get detailed author information by ASIN
        
        Args:
            asin: Author ASIN
            region: Region code
            update: Force update from upstream
            
        Returns:
            Author object with full details
        """
        try:
            self.logger.info("Getting author details", extra={"author_asin": asin, "region": region, "force_update": update})
            
            params = {
                "region": region,
                "update": "1" if update else "0"
            }
            
            response = self.session.get(
                f"{self.base_url}/authors/{asin}",
                params=params,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                author = response.json()
                self.logger.info("Author details retrieved", extra={"author_asin": asin, "author_name": author.get("name", asin)})
                return author
            elif response.status_code == 404:
                self.logger.warning("Author not found", extra={"author_asin": asin})
                return None
            else:
                body_preview = response.text[:200] if response.text else ''
                self.logger.error(
                    "Author details request failed",
                    extra={
                        'status_code': response.status_code,
                        'author_asin': asin,
                        'body': body_preview
                    }
                )
                return None
                
        except Exception as exc:
            self.logger.error(
                "Error getting author details",
                extra={"author_asin": asin, "exc": exc}
            )
            return None
    
    def get_book_details(self, asin: str, region: str = "us", seed_authors: bool = True, update: bool = False) -> Optional[Dict]:
        """
        Get detailed book information by ASIN
        
        Args:
            asin: Book ASIN
            region: Region code
            seed_authors: Whether to include author details
            update: Force update from upstream
            
        Returns:
            Book object with full details
        """
        try:
            self.logger.info("Getting book details", extra={"book_asin": asin, "region": region, "seed_authors": seed_authors, "force_update": update})
            
            params = {
                "region": region,
                "seedAuthors": "1" if seed_authors else "0",
                "update": "1" if update else "0"
            }
            
            response = self.session.get(
                f"{self.base_url}/books/{asin}",
                params=params,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                book = response.json()
                self.logger.info("Book details retrieved", extra={"book_asin": asin, "title": book.get("title", asin)})
                return book
            elif response.status_code == 404:
                self.logger.warning("Book not found", extra={"book_asin": asin})
                return None
            else:
                body_preview = response.text[:200] if response.text else ''
                self.logger.error(
                    "Book details request failed",
                    extra={
                        'status_code': response.status_code,
                        'book_asin': asin,
                        'body': body_preview
                    }
                )
                return None
        except Exception as exc:
            self.logger.error(
                "Error getting book details",
                extra={"book_asin": asin, "exc": exc}
            )
            return None
    
    def get_book_chapters(self, asin: str, region: str = "us", update: bool = False) -> Optional[Dict]:
        """
        Get chapter information for a book
        
        Args:
            asin: Book ASIN
            region: Region code
            update: Force update from upstream
            
        Returns:
            Chapter data with timing information
        """
        try:
            self.logger.info("Getting chapters", extra={"book_asin": asin, "region": region, "force_update": update})
            
            params = {
                "region": region,
                "update": "1" if update else "0"
            }
            
            response = self.session.get(
                f"{self.base_url}/books/{asin}/chapters",
                params=params,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                chapters = response.json()
                self.logger.info("Chapters retrieved", extra={"book_asin": asin})
                return chapters
            elif response.status_code == 404:
                self.logger.warning("Chapters not found", extra={"book_asin": asin})
                return None
            else:
                body_preview = response.text[:200] if response.text else ''
                self.logger.error(
                    "Chapters request failed",
                    extra={
                        'status_code': response.status_code,
                        'book_asin': asin,
                        'body': body_preview
                    }
                )
                return None
                
        except Exception as exc:
            self.logger.error(
                "Error getting chapters",
                extra={"book_asin": asin, "exc": exc}
            )
            return None
    
    def find_author_by_name(self, author_name: str, region: str = "us") -> Optional[Dict]:
        """
        Find the best matching author by name and return full details
        
        Args:
            author_name: Name to search for
            region: Region code
            
        Returns:
            Full author details for best match
        """
        try:
            # First search for authors
            authors = self.search_authors(author_name, region)
            
            if not authors:
                return None
            
            # Find best match (exact name match preferred)
            best_match = None
            exact_match = None
            
            for author in authors:
                if author.get('name', '').lower() == author_name.lower():
                    exact_match = author
                    break
                elif author_name.lower() in author.get('name', '').lower():
                    if not best_match:
                        best_match = author
            
            target_author = exact_match or best_match or authors[0]
            
            # Get full details for the best match
            if target_author and target_author.get('asin'):
                return self.get_author_details(target_author['asin'], region)
            
            return target_author
            
        except Exception as exc:
            self.logger.error(
                "Error finding author",
                extra={"author_name": author_name, "exc": exc}
            )
            return None
    
    def format_author_for_compatibility(self, author_data: Dict) -> Dict:
        """
        Format Audnexus author data to match existing application expectations
        
        Args:
            author_data: Raw author data from Audnexus
            
        Returns:
            Formatted author data compatible with existing code
        """
        try:
            formatted = {
                'asin': author_data.get('asin', ''),
                'name': author_data.get('name', ''),
                'author_image': author_data.get('image', ''),
                'author_bio': author_data.get('description', ''),
                'author_page_url': f"https://www.audible.com/author/{author_data.get('name', '').replace(' ', '-')}/{author_data.get('asin', '')}",
                'genres': author_data.get('genres', []),
                'similar_authors': author_data.get('similar', []),
                'region': author_data.get('region', 'us'),
                'last_updated': datetime.now().isoformat()
            }
            
            return formatted
            
        except Exception as exc:
            self.logger.error(
                "Error formatting author data",
                extra={"exc": exc}
            )
            return author_data
    
    def format_book_for_compatibility(self, book_data: Dict) -> Dict:
        """
        Format Audnexus book data to match existing application expectations
        
        Args:
            book_data: Raw book data from Audnexus
            
        Returns:
            Formatted book data compatible with existing code
        """
        try:
            # Extract author names
            authors = book_data.get('authors', [])
            author_name = authors[0].get('name', '') if authors else ''
            
            # Extract narrator names
            narrators = book_data.get('narrators', [])
            narrator_name = narrators[0].get('name', '') if narrators else ''
            
            # Convert runtime from minutes to hours/minutes format
            runtime_min = book_data.get('runtimeLengthMin', 0)
            hours = runtime_min // 60
            minutes = runtime_min % 60
            runtime_str = f"{hours} hrs {minutes} mins" if hours > 0 else f"{minutes} mins"
            
            # Extract release year from date
            release_date = book_data.get('releaseDate', '')
            release_year = ''
            if release_date:
                try:
                    release_year = release_date[:4]
                except:
                    pass
            
            formatted = {
                'ASIN': book_data.get('asin', ''),
                'Title': book_data.get('title', ''),
                'Author': author_name,
                'Authors': [author.get('name', '') for author in authors],
                'Narrator': narrator_name,
                'Narrators': [narrator.get('name', '') for narrator in narrators],
                'Publisher': book_data.get('publisherName', ''),
                'Release Date': release_year,
                'Runtime': runtime_str,
                'RuntimeMin': runtime_min,
                'Cover Image': book_data.get('image', ''),
                'Overall Rating': book_data.get('rating', ''),
                'Summary': book_data.get('summary', ''),
                'Description': book_data.get('description', ''),
                'ISBN': book_data.get('isbn', ''),
                'Language': book_data.get('language', ''),
                'Format': book_data.get('formatType', ''),
                'Genres': book_data.get('genres', []),
                'Copyright': book_data.get('copyright', ''),
                'IsAdult': book_data.get('isAdult', False),
                'LiteratureType': book_data.get('literatureType', ''),
                'Series': 'N/A',  # Will need to be extracted from title or description
                'Sequence': 'N/A',  # Will need to be extracted from title or description
                'Status': 'Available',
                'Region': book_data.get('region', 'us')
            }
            
            return formatted
            
        except Exception as exc:
            self.logger.error(
                "Error formatting book data",
                extra={"exc": exc}
            )
            return book_data
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to Audnexus API"""
        try:
            self.logger.info("Testing Audnexus API connection")
            
            # Simple test search
            response = self.session.get(
                f"{self.base_url}/authors",
                params={"name": "Andy Weir", "region": "us"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info(
                    "Audnexus API connection test successful",
                    extra={"author_count": len(data)}
                )
                return True, f"API accessible - found {len(data)} authors"
            else:
                self.logger.error(
                    "Audnexus API test failed",
                    extra={"status_code": response.status_code}
                )
                return False, f"API returned status {response.status_code}"
                
        except Exception as exc:
            self.logger.error(
                "Audnexus API connection test error",
                extra={"exc": exc}
            )
            return False, f"Connection error: {exc}"
    
    def get_service_status(self) -> Dict:
        """Get comprehensive service status"""
        try:
            is_connected, message = self.test_connection()
            
            return {
                'service_name': 'AudnexusService',
                'base_url': self.base_url,
                'initialized': self._initialized,
                'connected': is_connected,
                'status_message': message,
                'endpoints': {
                    'authors_search': f"{self.base_url}/authors",
                    'author_details': f"{self.base_url}/authors/{{asin}}",
                    'book_details': f"{self.base_url}/books/{{asin}}",
                    'book_chapters': f"{self.base_url}/books/{{asin}}/chapters"
                }
            }
            
        except Exception as exc:
            self.logger.error(
                "Error getting service status",
                extra={"exc": exc}
            )
            return {'error': str(exc)}
    
    def reset_service(self):
        """Reset the service (for testing or troubleshooting)"""
        with self._lock:
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("AudnexusService reset")
