"""
Module Name: result_processor.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Processes, deduplicates, and ranks search results for manual and automatic
    selection.

Location:
    /services/search_engine/result_processor.py

"""

from datetime import datetime
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.SearchEngine.ResultProcessor")


class ResultProcessor:
    """
    Process and rank search results for optimal selection.
    
    Features:
    - Result deduplication based on similarity
    - Quality-based ranking
    - Manual vs automatic selection logic
    - Series detection and handling
    - Result filtering and validation
    """
    
    def __init__(self, *, logger=None):
        """Initialize the result processor."""
        self.logger = logger or _LOGGER
        
        # Deduplication thresholds
        self.similarity_threshold = 0.9
        self.title_similarity_threshold = 0.85
        
        # Result limits
        self.max_results_manual = 20
        self.max_results_automatic = 50
        
        self.initialized = False
        self._initialize()
    
    def _initialize(self):
        """Initialize the result processor components."""
        try:
            self.logger.debug("Initializing ResultProcessor")
            self.initialized = True
            self.logger.debug("ResultProcessor initialized successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize ResultProcessor", extra={"error": str(e)}, exc_info=True)
            self.initialized = False
    
    def process_manual_search_results(self, raw_results: List[Dict[str, Any]], 
                                    title: str, author: str) -> List[Dict[str, Any]]:
        """Process search results for manual user selection."""
        try:
            if not raw_results:
                return []
            
            self.logger.debug(
                "Processing manual search results",
                extra={"raw_count": len(raw_results), "title": title, "author": author},
            )
            
            # Basic processing for now
            processed_results = []
            for i, result in enumerate(raw_results[:self.max_results_manual]):
                processed_result = {
                    'id': i + 1,
                    'title': result.get('title', 'Unknown Title'),
                    'author': result.get('author', 'Unknown Author'),
                    'indexer': result.get('indexer', 'Unknown'),
                    'format': result.get('format', 'unknown').upper(),
                    'bitrate': result.get('bitrate', 0),
                    'size': self._format_file_size(result.get('size', 0)),
                    'size_bytes': result.get('size', 0),  # Include raw bytes for frontend
                    'seeders': result.get('seeders', 0),
                    'peers': result.get('peers', 0),  # Include peers for health display
                    'download_url': result.get('download_url', ''),
                    'info_hash': result.get('info_hash', ''),
                    'quality_score': result.get('quality_score', 0.0)
                }
                
                # Include quality_assessment if available
                if 'quality_assessment' in result:
                    quality_assessment = result['quality_assessment']
                    # Convert dataclass to dict for JSON serialization
                    processed_result['quality_assessment'] = asdict(quality_assessment)
                
                processed_results.append(processed_result)
            
            return processed_results
            
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
            if not raw_results:
                return None
            
            # For now, just return the first result that meets basic criteria
            for result in raw_results:
                if (result.get('title') and result.get('author') and 
                    result.get('download_url')):
                    quality_dict = self._extract_quality_dict(result)
                    confidence = 0.0
                    if quality_dict:
                        confidence = float(quality_dict.get('confidence', 0) or 0)
                        result = result.copy()
                        result['quality_assessment'] = quality_dict
                    if 'confidence_score' not in result:
                        result['confidence_score'] = confidence
                    return {
                        'book_id': book_info.get('id'),
                        'selected_result': result,
                        'selection_timestamp': datetime.now().isoformat(),
                        'confidence_score': result.get('confidence_score', confidence)
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Failed to process automatic search results",
                extra={"error": str(e), "book_id": book_info.get("id")},
                exc_info=True,
            )
            return None

    def _extract_quality_dict(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize quality_assessment to a plain dict if possible."""
        qa = result.get('quality_assessment')
        if qa is None:
            return None
        if isinstance(qa, dict):
            return qa
        if is_dataclass(qa):
            try:
                return asdict(qa)
            except Exception:
                return None
        return None
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        if size_bytes <= 0:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.1f} TB"
    
    def get_processing_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about processed results."""
        if not results:
            return {'total_results': 0}
        
        stats = {
            'total_results': len(results),
            'formats': {},
            'average_quality': 0.0
        }
        
        # Format distribution
        for result in results:
            format_str = result.get('format', 'unknown').lower()
            stats['formats'][format_str] = stats['formats'].get(format_str, 0) + 1
        
        return stats