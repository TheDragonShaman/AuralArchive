"""
Module Name: audible_recommendations_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Fetch personalized recommendations and similar books via Audible API with cached results.
Location:
    /services/audible/audible_recommendations_service/audible_recommendations_service.py

"""

import os
from typing import Any, Dict, List, Tuple
from datetime import datetime, timedelta
import threading

from utils.logger import get_module_logger
from ..audible_service_manager import get_audible_manager

class AudibleRecommendationsService:
    """Service for managing Audible recommendations integration."""
    
    def __init__(self, config_service=None, logger=None):
        """
        Initialize the recommendations service.
        
        Args:
            config_service: Configuration service instance
        """
        self.logger = logger or get_module_logger("Service.Audible.Recommendations")
        self.config_service = config_service
        self.audible_manager = get_audible_manager(config_service)
        self._last_recommendations = []
        self._last_fetch_time = None
        self._cache_duration = timedelta(hours=2)  # Cache for 2 hours
        self._lock = threading.Lock()
        
    def is_configured(self) -> bool:
        """Check if Audible recommendations are properly configured."""
        return self.audible_manager.is_configured()
    
    def authenticate(self, username: str = None, password: str = None, 
                    country_code: str = "us") -> Tuple[bool, str]:
        """Authenticate with Audible using the manager."""
        return self.audible_manager.authenticate(username, password, country_code)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the Audible connection using the manager."""
        return self.audible_manager.test_connection()
    
    def get_recommendations(self, num_results: int = 20, 
                          force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get personalized recommendations from Audible.
        
        Args:
            num_results: Number of recommendations to fetch
            force_refresh: Force refresh cache
            
        Returns:
            List of recommended books
        """
        with self._lock:
            # Check cache first
            if not force_refresh and self._is_cache_valid():
                self.logger.info(
                    "Returning cached recommendations",
                    extra={"cache_size": len(self._last_recommendations), "requested": num_results},
                )
                return self._last_recommendations[:num_results]
            
            self.logger.info(
                "Fetching library-based recommendations",
                extra={"requested": num_results, "force_refresh": force_refresh},
            )
            
            try:
                recommendations = self._get_catalog_fallback(num_results)
                
                # Update cache
                self._last_recommendations = recommendations
                self._last_fetch_time = datetime.now()
                
                self.logger.info(
                    "Successfully fetched recommendations",
                    extra={"count": len(recommendations)},
                )
                return recommendations
                
            except Exception as e:
                self.logger.error(
                    "Error getting recommendations",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                return self._last_recommendations[:num_results] if self._last_recommendations else []
    
    def _get_catalog_fallback(self, num_results: int) -> List[Dict[str, Any]]:
        """Get personalized recommendations based on user's library preferences."""
        try:
            # Get user's library preferences
            preferences = self._analyze_library_preferences()
            all_books = []
            
            # Search based on favorite authors
            for author in preferences.get('top_authors', [])[:5]:
                try:
                    response = self.audible_manager.make_api_call(
                        "1.0/catalog/products",
                        num_results=5,
                        response_groups="contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media",
                        author=author,
                        sort_by="Relevance"
                    )
                    
                    if response:
                        books = response.get("products", [])
                        all_books.extend([self._format_book_data(book) for book in books])
                        
                except Exception as e:
                    self.logger.debug(
                        "Author search failed",
                        extra={"author": author, "error": str(e)},
                    )
                    continue
            
            # Search for series continuations
            for series in preferences.get('active_series', [])[:3]:
                try:
                    response = self.audible_manager.make_api_call(
                        "1.0/catalog/products", 
                        num_results=3,
                        response_groups="contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media",
                        keywords=f'"{series}"',
                        sort_by="Relevance"
                    )
                    
                    if response:
                        books = response.get("products", [])
                        all_books.extend([self._format_book_data(book) for book in books])
                        
                except Exception as e:
                    self.logger.debug(
                        "Series search failed",
                        extra={"series": series, "error": str(e)},
                    )
                    continue
            
            # Search for genre-based recommendations
            for genre in preferences.get('preferred_genres', [])[:3]:
                try:
                    response = self.audible_manager.make_api_call(
                        "1.0/catalog/products",
                        num_results=4,
                        response_groups="contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media", 
                        keywords=f"{genre} fantasy",
                        sort_by="Relevance"
                    )
                    
                    if response:
                        books = response.get("products", [])
                        all_books.extend([self._format_book_data(book) for book in books])
                        
                except Exception as e:
                    self.logger.debug(
                        "Genre search failed",
                        extra={"genre": genre, "error": str(e)},
                    )
                    continue
            
            # Filter out books already in library and remove duplicates
            owned_books = preferences.get('owned_books', set())
            seen_asins = set()
            unique_books = []
            
            for book in all_books:
                asin = book.get('asin')
                title = book.get('title', '').lower()
                
                # Skip if already owned or duplicate
                if asin in owned_books or asin in seen_asins:
                    continue
                
                # Skip if title matches something in library
                if any(title in owned_title.lower() for owned_title in preferences.get('owned_titles', [])):
                    continue
                    
                seen_asins.add(asin)
                unique_books.append(book)
                
                if len(unique_books) >= num_results:
                    break

            # If we didn't gather enough unique books, backfill with generic picks
            if len(unique_books) < num_results:
                try:
                    fallback_needed = num_results - len(unique_books)
                    fallback_books = self._get_generic_fallback(fallback_needed)

                    for book in fallback_books:
                        asin = book.get('asin')
                        title = book.get('title', '').lower()

                        if asin in owned_books or asin in seen_asins:
                            continue

                        if any(title in owned_title.lower() for owned_title in preferences.get('owned_titles', [])):
                            continue

                        seen_asins.add(asin)
                        unique_books.append(book)

                        if len(unique_books) >= num_results:
                            break
                except Exception as e:
                    self.logger.debug(
                        "Fallback padding failed",
                        extra={"error": str(e)},
                    )
            
            self.logger.info(
                "Library-based recommendations computed",
                extra={"unique_books": len(unique_books), "requested": num_results},
            )
            return unique_books
            
        except Exception as e:
            self.logger.error(
                "Library-based recommendations failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return self._get_generic_fallback(num_results)
    
    def _analyze_library_preferences(self) -> Dict[str, Any]:
        """Analyze user's library to understand reading preferences."""
        try:
            import sqlite3
            from collections import Counter
            
            # Connect to database
            db_path = "database/auralarchive_database.db"
            if not os.path.exists(db_path):
                self.logger.warning(
                    "Database not found, using generic recommendations",
                    extra={"db_path": db_path},
                )
                return {}
                
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get all books from library
            cursor.execute("""
                SELECT title, author, series, asin, summary 
                FROM books 
                WHERE author IS NOT NULL AND author != ''
            """)
            
            books = cursor.fetchall()
            conn.close()
            
            if not books:
                self.logger.warning(
                    "No books found in library",
                    extra={"db_path": db_path},
                )
                return {}
            
            # Analyze patterns
            authors = Counter()
            series = Counter()
            owned_books = set()
            owned_titles = []
            
            for title, author, series_name, asin, summary in books:
                # Count authors
                if author:
                    # Split multiple authors and count each
                    author_list = [a.strip() for a in author.split(',')]
                    for a in author_list:
                        if a and a != 'Unknown Author':
                            authors[a] += 1
                
                # Count series
                if series_name and series_name.strip():
                    series[series_name.strip()] += 1
                
                # Track owned books
                if asin:
                    owned_books.add(asin)
                if title:
                    owned_titles.append(title)
            
            # Get top preferences
            top_authors = [author for author, count in authors.most_common(10)]
            active_series = [s for s, count in series.most_common(8) if count >= 2]
            
            # Infer genres from library content
            preferred_genres = []
            total_books = len(books)
            
            # Check for common LitRPG/GameLit patterns
            litrpg_keywords = ['litrpg', 'lit rpg', 'game', 'rpg', 'level', 'system', 'dungeon', 'progression']
            fantasy_keywords = ['fantasy', 'magic', 'dragon', 'sword', 'adventure', 'quest']
            
            litrpg_count = 0
            fantasy_count = 0
            
            for title, author, _, _, summary in books:
                title_lower = (title or '').lower()
                author_lower = (author or '').lower()
                summary_lower = (summary or '').lower()
                text = f"{title_lower} {author_lower} {summary_lower}"
                
                if any(keyword in text for keyword in litrpg_keywords):
                    litrpg_count += 1
                if any(keyword in text for keyword in fantasy_keywords):
                    fantasy_count += 1
            
            # Add genres if they represent significant portion of library
            if litrpg_count / total_books > 0.3:
                preferred_genres.append('litrpg')
            if fantasy_count / total_books > 0.4:
                preferred_genres.append('fantasy')
            
            # Based on your library analysis, add known preferences
            if any('cradle' in s.lower() for s in active_series):
                preferred_genres.extend(['progression fantasy', 'cultivation'])
            if any('dragon heart' in s.lower() for s in active_series):
                preferred_genres.extend(['litrpg', 'gamelit'])
            
            preferences = {
                'top_authors': top_authors,
                'active_series': active_series,
                'preferred_genres': list(set(preferred_genres)),
                'owned_books': owned_books,
                'owned_titles': owned_titles,
                'total_books': total_books
            }
            
            self.logger.info(
                "Library analysis completed",
                extra={
                    "authors": len(top_authors),
                    "series": len(active_series),
                    "genres": len(preferred_genres),
                    "total_books": total_books,
                },
            )
            return preferences
            
        except Exception as e:
            self.logger.error(
                "Library analysis failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {}
    
    def _get_generic_fallback(self, num_results: int) -> List[Dict[str, Any]]:
        """Get generic recommendations as last resort."""
        try:
            # Try multiple search terms for variety
            search_terms = ["bestseller", "popular", "award winning", "fiction", "mystery"]
            all_books = []
            
            for term in search_terms:
                try:
                    response = self.audible_manager.make_api_call(
                        "1.0/catalog/products",
                        num_results=min(10, num_results // len(search_terms) + 5),
                        response_groups="contributors,media,price,product_attrs,product_desc,rating",
                        keywords=term,
                        sort_by="Relevance"
                    )
                    
                    if response:
                        books = response.get("products", [])
                        all_books.extend([self._format_book_data(book) for book in books])
                        
                        if len(all_books) >= num_results:
                            break
                            
                except Exception as e:
                    self.logger.debug(
                        "Search term failed",
                        extra={"term": term, "error": str(e)},
                    )
                    continue
            
            # Remove duplicates and limit results
            seen_asins = set()
            unique_books = []
            for book in all_books:
                asin = book.get('asin')
                if asin and asin not in seen_asins:
                    seen_asins.add(asin)
                    unique_books.append(book)
                    if len(unique_books) >= num_results:
                        break
            
            return unique_books
            
        except Exception as e:
            self.logger.error(
                "Generic fallback failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return []
    
    def get_similar_books(self, asin: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """Get books similar to a specific book."""
        try:
            response = self.audible_manager.make_api_call(
                f"1.0/catalog/products/{asin}/sims",
                num_results=min(num_results, 50),
                similarity_type="RawSimilarities",
                response_groups="contributors,media,price,product_attrs,product_desc,rating"
            )
            
            if response:
                similar_books = response.get("products", [])
                return [self._format_book_data(book) for book in similar_books]
            
            return []
            
        except Exception as e:
            self.logger.error(
                "Error getting similar books",
                extra={"asin": asin, "error": str(e)},
                exc_info=True,
            )
            return []
    
    def _format_book_data(self, book: Dict[str, Any]) -> Dict[str, Any]:
        """Format book data using the shared manager."""
        formatted = self.audible_manager.format_book_data(book)
        formatted['source'] = 'audible_recommendations'
        return formatted
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if not self._last_fetch_time or not self._last_recommendations:
            return False
        
        time_since_fetch = datetime.now() - self._last_fetch_time
        return time_since_fetch < self._cache_duration
    
    def clear_cache(self):
        """Clear the recommendations cache."""
        with self._lock:
            self._last_recommendations = []
            self._last_fetch_time = None
            self.logger.info("Recommendations cache cleared", extra={"event": "manual_clear"})
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status information."""
        try:
            manager_status = self.audible_manager.get_service_status()
            last_fetch = "Never"
            cache_size = len(self._last_recommendations)
            
            if self._last_fetch_time:
                last_fetch = self._last_fetch_time.strftime("%Y-%m-%d %H:%M:%S")
            
            return {
                **manager_status,
                'cache_size': cache_size,
                'last_fetch': last_fetch,
                'cache_valid': self._is_cache_valid()
            }
            
        except Exception as e:
            self.logger.error(
                "Error getting service status",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {
                'configured': False,
                'connected': False,
                'error': str(e)
            }

# Global service instance
_recommendations_service = None

def get_audible_recommendations_service(config_service=None):
    """Get the global Audible recommendations service instance."""
    global _recommendations_service
    if _recommendations_service is None:
        _recommendations_service = AudibleRecommendationsService(config_service=config_service)
    return _recommendations_service
