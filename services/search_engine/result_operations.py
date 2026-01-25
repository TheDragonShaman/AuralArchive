"""
Module Name: result_operations.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Coordinates result ranking, filtering, and selection for manual and
    automatic modes within the search engine.

Location:
    /services/search_engine/result_operations.py

"""

from typing import Any, Dict, List, Optional

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.SearchEngine.ResultOperations")


class ResultOperations:
    """
    Handles result processing operations for the SearchEngineService.
    
    Features:
    - Result processing for manual selection
    - Automatic result selection logic
    - Quality-based filtering and ranking
    - Statistics and analytics
    """
    
    def __init__(self, fuzzy_matcher, quality_assessor, result_processor, *, logger=None):
        """Initialize result operations with injected dependencies."""
        self.logger = logger or _LOGGER
        self.fuzzy_matcher = fuzzy_matcher
        self.quality_assessor = quality_assessor
        self.result_processor = result_processor
    
    def process_manual_search_results(self, raw_results: List[Dict[str, Any]], 
                                    title: str, author: str) -> List[Dict[str, Any]]:
        """Process search results for manual user selection."""
        try:
            return self.result_processor.process_manual_search_results(raw_results, title, author)
            
        except Exception as e:
            self.logger.error(
                "Failed to process manual search results",
                extra={"error": str(e), "title": title, "author": author},
                exc_info=True,
            )
            return []
    
    def process_automatic_search_results(self, raw_results: List[Dict[str, Any]], 
                                       book_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process search results for automatic selection."""
        try:
            return self.result_processor.process_automatic_search_results(raw_results, book_info)
            
        except Exception as e:
            self.logger.error(
                "Failed to process automatic search results",
                extra={"error": str(e), "book_id": book_info.get("id")},
                exc_info=True,
            )
            return None
    
    def get_processing_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about processed results."""
        try:
            return self.result_processor.get_processing_stats(results)
            
        except Exception as e:
            self.logger.error(
                "Failed to get processing stats",
                extra={"error": str(e), "result_count": len(results)},
                exc_info=True,
            )
            return {'error': str(e)}