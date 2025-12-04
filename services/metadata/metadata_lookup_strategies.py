import logging
from typing import List, Dict, Optional, TYPE_CHECKING
from .matching import matcher

if TYPE_CHECKING:
    from .metadata_service import CancellationContext

class MetadataSearchStrategies:
    """Handles different search strategies for finding book metadata"""
    
    def __init__(self, audible_service):
        self.audible_service = audible_service
        self.logger = logging.getLogger("MetadataUpdateService.SearchStrategies")
    
    def search_for_book_metadata(self, title: str, author: str, asin: str, 
                                cancellation_context: Optional['CancellationContext'] = None) -> Optional[Dict]:
        """Search for book metadata using multiple strategies"""
        try:
            self.logger.info(f"Searching for metadata: '{title}' by '{author}' (ASIN: {asin})")
            
            # Check for cancellation before starting search
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            # Strategy 1: Search by ASIN if available
            if asin and asin not in ['N/A', '']:
                if cancellation_context:
                    cancellation_context.raise_if_cancelled()
                result = self._search_by_asin_strategy(asin, cancellation_context)
                if result:
                    return result
            
            # Strategy 2: Search by title + author
            if title and author:
                if cancellation_context:
                    cancellation_context.raise_if_cancelled()
                result = self._search_by_title_author_strategy(title, author, asin, cancellation_context)
                if result:
                    return result
            
            # Strategy 3: Search by title only
            if title:
                if cancellation_context:
                    cancellation_context.raise_if_cancelled()
                result = self._search_by_title_only_strategy(title, author, asin, cancellation_context)
                if result:
                    return result
            
            self.logger.warning(f"No suitable matches found for: '{title}' by '{author}'")
            return None
            
        except Exception as e:
            # Re-raise cancellation exceptions
            if "cancelled" in str(e).lower():
                raise
            self.logger.error(f"Error searching for book metadata: {e}")
            return None
    
    def _search_by_asin_strategy(self, asin: str, cancellation_context: Optional['CancellationContext'] = None) -> Optional[Dict]:
        """Strategy 1: Search by ASIN"""
        try:
            self.logger.info(f"Strategy 1: Searching by ASIN: {asin}")
            
            # Check for cancellation before making API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            search_results = self.audible_service.search_books(asin, region="us", num_results=10)
            
            # Check for cancellation after API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            if not search_results:
                self.logger.info(f"No results found for ASIN: {asin}")
                return None
            
            # Look for exact ASIN match first
            exact_match = matcher.find_exact_asin_match(search_results, asin)
            if exact_match:
                self.logger.info(f"Found exact ASIN match: {exact_match.get('Title')}")
                return exact_match
            
            # If no exact match, check if any result is close enough
            for result in search_results:
                result_asin = result.get('ASIN', '')
                if result_asin and result_asin == asin:
                    self.logger.info(f"Found ASIN match in results: {result.get('Title')}")
                    return result
            
            self.logger.info(f"No exact ASIN match found in {len(search_results)} results")
            return None
            
        except Exception as e:
            self.logger.error(f"Error in ASIN search strategy: {e}")
            return None
    
    def _search_by_title_author_strategy(self, title: str, author: str, asin: str, 
                                        cancellation_context: Optional['CancellationContext'] = None) -> Optional[Dict]:
        """Strategy 2: Search by title + author"""
        try:
            search_query = f"{title} {author}"
            self.logger.info(f"Strategy 2: Searching by title + author: {search_query}")
            
            # Check for cancellation before API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            search_results = self.audible_service.search_books(search_query, region="us", num_results=15)
            
            # Check for cancellation after API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            if not search_results:
                self.logger.info(f"No results found for title + author search")
                return None
            
            # If we have an ASIN, try to find exact match first
            if asin and asin not in ['N/A', '']:
                exact_match = matcher.find_exact_asin_match(search_results, asin)
                if exact_match:
                    self.logger.info(f"Found exact ASIN match in title/author search: {exact_match.get('Title')}")
                    return exact_match
            
            # Look for best title/author match
            best_match = matcher.find_best_match(search_results, title, author)
            if best_match:
                self.logger.info(f"Found best match in title/author search: {best_match.get('Title')} by {best_match.get('Author')}")
                return best_match
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in title + author search strategy: {e}")
            return None
    
    def _search_by_title_only_strategy(self, title: str, author: str, asin: str, 
                                      cancellation_context: Optional['CancellationContext'] = None) -> Optional[Dict]:
        """Strategy 3: Search by title only"""
        try:
            self.logger.info(f"Strategy 3: Searching by title only: {title}")
            
            # Check for cancellation before API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            search_results = self.audible_service.search_books(title, region="us", num_results=10)
            
            # Check for cancellation after API call
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            if not search_results:
                self.logger.info(f"No results found for title-only search")
                return None
            
            # If we have an ASIN, try to find exact match first
            if asin and asin not in ['N/A', '']:
                exact_match = matcher.find_exact_asin_match(search_results, asin)
                if exact_match:
                    self.logger.info(f"Found exact ASIN match in title-only search: {exact_match.get('Title')}")
                    return exact_match
            
            # Look for best match considering both title and author if available
            best_match = matcher.find_best_match(search_results, title, author)
            if best_match:
                self.logger.info(f"Found match by title: {best_match.get('Title')} by {best_match.get('Author')}")
                return best_match
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in title-only search strategy: {e}")
            return None
    
    def search_by_author_only(self, author: str, title_hint: str = "") -> List[Dict]:
        """Additional strategy: Search by author only (for finding related books)"""
        try:
            self.logger.info(f"Searching by author only: {author}")
            
            if not author or author.lower() in ['unknown author', 'unknown']:
                return []
            
            search_results = self.audible_service.search_by_author(author, num_results=20)
            
            if not search_results:
                # Fallback to regular search with author name
                search_results = self.audible_service.search_books(author, num_results=15)
            
            # If we have a title hint, prioritize results that match
            if title_hint and search_results:
                title_hint_lower = title_hint.lower()
                prioritized_results = []
                other_results = []
                
                for result in search_results:
                    result_title = result.get('Title', '').lower()
                    if title_hint_lower in result_title or result_title in title_hint_lower:
                        prioritized_results.append(result)
                    else:
                        other_results.append(result)
                
                search_results = prioritized_results + other_results
            
            self.logger.info(f"Found {len(search_results)} books by author: {author}")
            return search_results
            
        except Exception as e:
            self.logger.error(f"Error in author-only search: {e}")
            return []
    
    def search_by_series(self, series_name: str, sequence: str = "") -> List[Dict]:
        """Additional strategy: Search by series name"""
        try:
            self.logger.info(f"Searching by series: {series_name}")
            
            if not series_name or series_name.lower() in ['n/a', 'unknown']:
                return []
            
            search_results = self.audible_service.search_by_series(series_name, num_results=25)
            
            if not search_results:
                # Fallback to regular search with series name
                search_results = self.audible_service.search_books(f'"{series_name}" series', num_results=15)
            
            # Sort by sequence if available
            if sequence and sequence not in ['N/A', '']:
                try:
                    target_sequence = float(sequence)
                    search_results.sort(key=lambda x: abs(self._parse_sequence(x.get('Sequence', '')) - target_sequence))
                except:
                    pass
            
            self.logger.info(f"Found {len(search_results)} books in series: {series_name}")
            return search_results
            
        except Exception as e:
            self.logger.error(f"Error in series search: {e}")
            return []
    
    def _parse_sequence(self, sequence_str: str) -> float:
        """Parse sequence string to float for sorting"""
        try:
            if not sequence_str or sequence_str in ['N/A', '']:
                return 999.0
            
            # Clean up sequence string
            cleaned = sequence_str.replace('Book ', '').replace('#', '').strip()
            return float(cleaned)
        except:
            return 999.0
    
    def validate_search_strategy_config(self) -> bool:
        """Validate that search strategies can be executed"""
        try:
            if not self.audible_service:
                self.logger.error("No AudibleService available for search strategies")
                return False
            
            # Test basic search functionality
            test_results = self.audible_service.search_books("test", num_results=1)
            if test_results is None:
                self.logger.error("AudibleService search test failed")
                return False
            
            self.logger.info("Search strategies validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Search strategies validation failed: {e}")
            return False
    
    def get_strategy_stats(self) -> Dict[str, int]:
        """Get statistics about search strategy usage (placeholder for future implementation)"""
        # This could track which strategies are most successful
        return {
            'asin_searches': 0,
            'title_author_searches': 0,
            'title_only_searches': 0,
            'successful_matches': 0,
            'failed_matches': 0
        }

# This will be instantiated by the main service with dependency injection
