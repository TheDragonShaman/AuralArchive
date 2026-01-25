"""
Module Name: search_engine_service.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Coordinates audiobook search with fuzzy matching, quality assessment, and
    multi-indexer integration.

Location:
    /services/search_engine/search_engine_service.py

"""

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_module_logger

from .search_operations import SearchOperations
from .indexer_operations import IndexerOperations
from .result_operations import ResultOperations
from .fuzzy_matcher import FuzzyMatcher
from .quality_assessor import QualityAssessor
from .result_processor import ResultProcessor


_LOGGER = get_module_logger("Service.SearchEngine.Service")


class SearchEngineService:
    """
    Main search engine service following DatabaseService singleton pattern.
    
    Features:
    - Manual and automatic search modes
    - Fuzzy matching with Readarr's Bitap algorithm
    - Quality assessment and ranking
    - Multi-indexer coordination
    - Result processing and deduplication
    """
    
    _instance: Optional['SearchEngineService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, *, logger=None):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logger or _LOGGER
                    
                    # Initialize operation components
                    self.search_operations = None
                    self.indexer_operations = None
                    self.result_operations = None
                    self.fuzzy_matcher = None
                    self.quality_assessor = None
                    self.result_processor = None
                    
                    # Search configuration
                    self.max_search_results = 50
                    self.search_timeout = 60  # seconds
                    
                    # Test audiobooks for validation
                    self.test_audiobooks = [
                        {"title": "Anima", "author": "Blake Crouch"},
                        {"title": "The Primal Hunter", "author": "Zogarth"}
                    ]
                    
                    # Initialize service
                    self._initialize_service()
                    
                    SearchEngineService._initialized = True
    
    def _initialize_service(self):
        """Initialize the search engine service components."""
        try:
            self.logger.debug("Initializing SearchEngineService")
            
            # Initialize helper components
            self.fuzzy_matcher = FuzzyMatcher()
            self.quality_assessor = QualityAssessor()
            self.result_processor = ResultProcessor()
            
            # Initialize indexer operations first
            self.indexer_operations = IndexerOperations()
            
            # Initialize operation components (with dependency injection)
            self.search_operations = SearchOperations(
                self.fuzzy_matcher, 
                self.quality_assessor, 
                self.result_processor
            )
            
            # Inject indexer_operations into search_operations
            self.search_operations.indexer_operations = self.indexer_operations
            
            self.result_operations = ResultOperations(
                self.fuzzy_matcher,
                self.quality_assessor,
                self.result_processor
            )
            
            indexer_count = 0
            if self.indexer_operations and self.indexer_operations.indexer_service_manager:
                indexer_count = len(self.indexer_operations.indexer_service_manager.indexers)
            self.logger.success("Search engine started successfully", extra={"indexers": indexer_count})
            
        except Exception as e:
            self.logger.error(
                "Failed to initialize SearchEngineService",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
    
    # Search operation methods (delegate to search_operations)
    def search_for_audiobook(self, title: str, author: str, 
                           manual_search: bool = True) -> Dict[str, Any]:
        """Search for audiobook across all indexers."""
        return self.search_operations.search_for_audiobook(title, author, manual_search)
    
    def automatic_search_flagged_books(self) -> Dict[str, Any]:
        """Perform automatic search for all flagged books."""
        return self.search_operations.automatic_search_flagged_books()
    
    def get_search_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent search history."""
        return self.search_operations.get_search_history(limit)
    
    # Indexer operation methods (delegate to indexer_operations)
    def get_indexer_status(self) -> Dict[str, Any]:
        """Get current status of all indexers."""
        return self.indexer_operations.get_indexer_status()
    
    def refresh_indexers(self) -> bool:
        """Refresh indexer list and perform health check."""
        return self.indexer_operations.refresh_indexers()
    
    def test_indexer_search(self, indexer_id: str, title: str = "Anima", 
                           author: str = "Blake Crouch") -> Dict[str, Any]:
        """Test search functionality for a specific indexer."""
        return self.indexer_operations.test_indexer_search(indexer_id, title, author)
    
    def search_all_indexers(self, title: str, author: str, 
                           manual_search: bool = False) -> List[Dict[str, Any]]:
        """Search all active indexers for audiobook results."""
        return self.indexer_operations.search_all_indexers(title, author, manual_search)
    
    # Result operation methods (delegate to result_operations)
    def process_manual_search_results(self, raw_results: List[Dict[str, Any]], 
                                    title: str, author: str) -> List[Dict[str, Any]]:
        """Process search results for manual user selection."""
        return self.result_operations.process_manual_search_results(raw_results, title, author)
    
    def process_automatic_search_results(self, raw_results: List[Dict[str, Any]], 
                                       book_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process search results for automatic selection."""
        return self.result_operations.process_automatic_search_results(raw_results, book_info)
    
    def get_processing_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about processed results."""
        return self.result_operations.get_processing_stats(results)
    
    # Fuzzy matching methods (delegate to fuzzy_matcher)
    def fuzzy_match(self, text1: str, text2: str) -> Dict[str, Any]:
        """Perform fuzzy matching between two strings."""
        return self.fuzzy_matcher.fuzzy_match(text1, text2)
    
    def clean_title_for_matching(self, title: str) -> str:
        """Clean title for better matching accuracy."""
        return self.fuzzy_matcher.clean_title_for_matching(title)
    
    # Quality assessment methods (delegate to quality_assessor)
    def assess_result_quality(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the quality of a search result."""
        return self.quality_assessor.assess_result_quality(result)
    
    def meets_user_preferences(self, result: Dict[str, Any]) -> bool:
        """Check if result meets user quality preferences."""
        return self.quality_assessor.meets_user_preferences(result)
    
    def rank_results_by_quality(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank results by quality score."""
        return self.quality_assessor.rank_results_by_quality(results)
    
    # Test and validation methods
    def test_search_functionality(self) -> Dict[str, Any]:
        """Test search functionality with predefined audiobooks."""
        try:
            self.logger.info("Testing search functionality...")
            
            test_results = {}
            
            for test_book in self.test_audiobooks:
                title = test_book["title"]
                author = test_book["author"]
                
                self.logger.info("Testing search", extra={"title": title, "author": author})
                
                # Test search
                search_result = self.search_for_audiobook(title, author, manual_search=True)
                
                test_results[f"{title}_by_{author}"] = {
                    "title": title,
                    "author": author,
                    "search_successful": search_result.get("success", False),
                    "result_count": len(search_result.get("results", [])),
                    "search_time": search_result.get("search_time", 0),
                    "indexers_searched": search_result.get("indexers_searched", 0),
                    "sample_result": search_result.get("results", [{}])[0] if search_result.get("results") else None
                }
            
            # Test indexer status
            indexer_status = self.get_indexer_status()
            
            overall_result = {
                "success": True,
                "test_timestamp": datetime.now().isoformat(),
                "individual_tests": test_results,
                "indexer_status": indexer_status,
                "service_status": self.get_service_status()
            }
            
            self.logger.info("Search functionality test completed successfully")
            return overall_result
            
        except Exception as e:
            self.logger.error("Search functionality test failed", extra={"error": str(e)}, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "test_timestamp": datetime.now().isoformat()
            }
    
    # Service management methods
    def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status."""
        try:
            status = {
                'service_name': 'SearchEngineService',
                'initialized': self._initialized,
                'search_timeout': self.search_timeout,
                'max_search_results': self.max_search_results,
                'test_audiobooks': self.test_audiobooks,
                'components': {
                    'search_operations': bool(self.search_operations),
                    'indexer_operations': bool(self.indexer_operations),
                    'result_operations': bool(self.result_operations),
                    'fuzzy_matcher': bool(self.fuzzy_matcher),
                    'quality_assessor': bool(self.quality_assessor),
                    'result_processor': bool(self.result_processor)
                }
            }
            
            # Add component-specific status
            if self.indexer_operations:
                status['indexer_status'] = self.indexer_operations.get_indexer_status()
            
            return status
            
        except Exception as e:
            self.logger.error("Error getting service status", extra={"error": str(e)}, exc_info=True)
            return {'error': str(e)}
    
    def reset_service(self):
        """Reset the service (for testing or troubleshooting)."""
        with self._lock:
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("SearchEngineService reset")
    
    def shutdown(self):
        """Shutdown the search engine service."""
        try:
            if self.indexer_operations:
                self.indexer_operations.shutdown()
            
            self.logger.info("SearchEngineService shutdown complete")
            
        except Exception as e:
            self.logger.error("Error during SearchEngineService shutdown", extra={"error": str(e)}, exc_info=True)