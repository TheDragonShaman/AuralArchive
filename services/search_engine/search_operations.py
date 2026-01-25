"""
Module Name: search_operations.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Core search execution, history tracking, and result coordination for the
    search engine service.

Location:
    /services/search_engine/search_operations.py

"""

import re
import time
from datetime import datetime
from typing import Any, Dict, List

from utils.logger import get_module_logger
from utils.search_normalization import normalize_search_terms


_LOGGER = get_module_logger("Service.SearchEngine.SearchOperations")


class SearchOperations:
    """
    Handles core search operations for the SearchEngineService.
    
    Features:
    - Manual and automatic search coordination
    - Search history tracking
    - Result aggregation and processing
    - Integration with indexers and quality assessment
    """
    
    def __init__(self, fuzzy_matcher, quality_assessor, result_processor, *, logger=None):
        """Initialize search operations with injected dependencies."""
        self.logger = logger or _LOGGER
        self.fuzzy_matcher = fuzzy_matcher
        self.quality_assessor = quality_assessor
        self.result_processor = result_processor
        
        # Will be injected by SearchEngineService
        self.indexer_operations = None
        
        # Search configuration
        self.search_timeout = 60
        self.max_concurrent_searches = 5

    def _build_series_queries(self, title: str) -> List[str]:
        """Return additional title variants such as 'Series Name Book #'."""
        variants: List[str] = []
        if not title:
            return variants

        normalized = title.strip()
        if not normalized:
            return variants

        # Consider text before first colon - usually 'Series XX'
        head = normalized.split(':', 1)[0].strip()

        patterns = [head, normalized]

        for candidate in patterns:
            match = re.search(r'(?P<series>[^\d]+?)\s*(?:book\s*)?(?P<number>\d+)\b', candidate, re.IGNORECASE)
            if not match:
                # Look for "Series Name, Book 3" style
                match = re.search(
                    r'(?P<series>[^,]+?),\s*(?:book|volume)\s*(?P<number>\d+)\b',
                    candidate,
                    re.IGNORECASE
                )
            if match:
                series = match.group('series').strip(' ,:-')
                number = match.group('number').strip()
                if series and number:
                    variant = f"{series} {number}"
                    if variant.lower() != normalized.lower() and variant not in variants:
                        variants.append(variant)
        return variants
    
    def search_for_audiobook(self, title: str, author: str, 
                           manual_search: bool = True) -> Dict[str, Any]:
        """
        Search for audiobook across all indexers.
        
        Args:
            title: Book title to search for
            author: Author name to search for
            manual_search: Whether this is a manual search
            
        Returns:
            Search results with metadata
        """
        try:
            start_time = time.time()
            original_title = title
            original_author = author
            normalized_query, normalized_title, normalized_author = normalize_search_terms(
                title,
                title,
                author,
            )
            search_title = normalized_title or original_title
            search_author = normalized_author or original_author

            self.logger.info(
                "Starting search",
                extra={
                    "search_type": "manual" if manual_search else "automatic",
                    "title": original_title,
                    "author": original_author,
                    "normalized_title": search_title,
                    "normalized_author": search_author,
                },
            )

            queries = []
            title_seed = search_title or normalized_query
            if title_seed:
                queries.append(title_seed)
            for variant in self._build_series_queries(title_seed or ""):
                if variant not in queries:
                    queries.append(variant)
            if not queries and normalized_query:
                queries.append(normalized_query)
            if not queries and search_author:
                queries.append(search_author)

            if queries:
                self.logger.info(
                    "Search variants prepared",
                    extra={"variant_count": len(queries), "variants": queries},
                )
            else:
                self.logger.info(
                    "No title provided; using empty search query",
                    extra={"title": title, "author": author},
                )

            raw_results: List[Dict[str, Any]] = []
            seen_keys: set = set()

            if not self.indexer_operations:
                self.logger.warning(
                    "Indexer operations unavailable",
                    extra={"variant_count": len(queries)},
                )
            else:
                for idx, query_title in enumerate(queries or ['']):
                    if not query_title:
                        continue
                    self.logger.info(
                        "Running search variant",
                        extra={
                            "variant_index": idx + 1,
                            "variant_total": len(queries),
                            "query": query_title,
                        },
                    )
                    variant_results = self.indexer_operations.search_all_indexers(
                        query_title,
                        search_author,
                        manual_search
                    )
                    for result in variant_results:
                        key = result.get('download_url') or result.get('info_hash') or (
                            result.get('indexer'), result.get('title')
                        )
                        if not key:
                            key = id(result)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        result_copy = result.copy()
                        result_copy.setdefault('_search_query_used', query_title)
                        raw_results.append(result_copy)
            
            # Assess quality and rank results (adds quality_assessment with confidence to each result)
            if raw_results:
                self.logger.info(
                    "Assessing quality for search results",
                    extra={"result_count": len(raw_results), "title": title, "author": author},
                )
                scored_results = self.quality_assessor.rank_results_by_quality(
                    raw_results, 
                    search_title=title, 
                    search_author=author
                )
                self.logger.info(
                    "Quality assessment complete",
                    extra={"scored_count": len(scored_results)},
                )
            else:
                scored_results = []
            
            # Process results based on search type
            if manual_search:
                processed_results = self.result_processor.process_manual_search_results(
                    scored_results, title, author
                )
            else:
                book_info = {'id': 1, 'title': title, 'author': author}
                best_result = self.result_processor.process_automatic_search_results(
                    scored_results, book_info
                )
                processed_results = [best_result] if best_result else []
            
            search_time = time.time() - start_time
            
            return {
                'success': True,
                'search_type': 'manual' if manual_search else 'automatic',
                'query': {'title': title, 'author': author},
                'results': processed_results,
                'result_count': len(processed_results),
                'search_time': round(search_time, 2),
                'indexers_searched': len(self.indexer_operations.indexer_service_manager.indexers) if self.indexer_operations and self.indexer_operations.indexer_service_manager else 0,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(
                "Search failed",
                extra={"title": title, "author": author, "error": str(e)},
                exc_info=True,
            )
            return {
                'success': False,
                'error': str(e),
                'query': {'title': title, 'author': author},
                'timestamp': datetime.now().isoformat()
            }
    
    def automatic_search_flagged_books(self) -> Dict[str, Any]:
        """Perform automatic search for all flagged books."""
        try:
            self.logger.info("Starting automatic search for flagged books")
            
            # For Phase 1, return mock response
            return {
                'success': True,
                'books_processed': 0,
                'successful_downloads': 0,
                'failed_searches': 0,
                'timestamp': datetime.now().isoformat(),
                'message': 'Automatic search not yet implemented - Phase 1'
            }
            
        except Exception as e:
            self.logger.error(f"Automatic search failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_search_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent search history."""
        try:
            # For Phase 1, return empty history
            return []
            
        except Exception as e:
            self.logger.error(f"Failed to get search history: {e}")
            return []
    
    def _generate_mock_results(self, title: str, author: str) -> List[Dict[str, Any]]:
        """Generate mock search results for testing."""
        return [
            {
                'title': f"{title} (Unabridged)",
                'author': author,
                'format': 'm4b',
                'bitrate': 128,
                'size': 500000000,  # 500MB
                'seeders': 15,
                'indexer': 'MockIndexer1',
                'download_url': 'magnet:?xt=mock1',
                'info_hash': 'mock_hash_1',
                'quality_score': 8.5
            },
            {
                'title': title,
                'author': author,
                'format': 'mp3',
                'bitrate': 96,
                'size': 300000000,  # 300MB
                'seeders': 8,
                'indexer': 'MockIndexer2',
                'download_url': 'magnet:?xt=mock2',
                'info_hash': 'mock_hash_2',
                'quality_score': 6.5
            }
        ]