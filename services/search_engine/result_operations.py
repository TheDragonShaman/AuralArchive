"""
Result Operations - Advanced result processing and selection logic
Handles result ranking, filtering, and selection for both manual and automatic modes

Location: services/search_engine/result_operations.py
Purpose: Result processing operations for SearchEngineService
"""

from typing import Dict, List, Any, Optional
import logging
from datetime import datetime


class ResultOperations:
    """
    Handles result processing operations for the SearchEngineService.
    
    Features:
    - Result processing for manual selection
    - Automatic result selection logic
    - Quality-based filtering and ranking
    - Statistics and analytics
    """
    
    def __init__(self, fuzzy_matcher, quality_assessor, result_processor):
        """Initialize result operations with injected dependencies."""
        self.logger = logging.getLogger("SearchEngineService.ResultOperations")
        self.fuzzy_matcher = fuzzy_matcher
        self.quality_assessor = quality_assessor
        self.result_processor = result_processor
    
    def process_manual_search_results(self, raw_results: List[Dict[str, Any]], 
                                    title: str, author: str) -> List[Dict[str, Any]]:
        """Process search results for manual user selection."""
        try:
            return self.result_processor.process_manual_search_results(raw_results, title, author)
            
        except Exception as e:
            self.logger.error(f"Failed to process manual search results: {e}")
            return []
    
    def process_automatic_search_results(self, raw_results: List[Dict[str, Any]], 
                                       book_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process search results for automatic selection."""
        try:
            return self.result_processor.process_automatic_search_results(raw_results, book_info)
            
        except Exception as e:
            self.logger.error(f"Failed to process automatic search results: {e}")
            return None
    
    def get_processing_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about processed results."""
        try:
            return self.result_processor.get_processing_stats(results)
            
        except Exception as e:
            self.logger.error(f"Failed to get processing stats: {e}")
            return {'error': str(e)}