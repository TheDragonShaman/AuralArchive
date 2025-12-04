"""
Result Processor - Search result processing, deduplication, and ranking
Handles search result aggregation, filtering, and selection logic

Location: services/search_engine/result_processor.py
Purpose: Process and rank search results for both manual and automatic selection
"""

from typing import Dict, List, Any, Optional, Tuple, Set
import logging
from datetime import datetime
import hashlib
import re
from dataclasses import asdict, is_dataclass


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
    
    def __init__(self):
        """Initialize the result processor."""
        self.logger = logging.getLogger("SearchEngineService.ResultProcessor")
        
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
            self.logger.debug("Initializing ResultProcessor...")
            self.initialized = True
            self.logger.debug("ResultProcessor initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize ResultProcessor: {e}")
            self.initialized = False
    
    def process_manual_search_results(self, raw_results: List[Dict[str, Any]], 
                                    title: str, author: str) -> List[Dict[str, Any]]:
        """Process search results for manual user selection."""
        try:
            if not raw_results:
                return []
            
            self.logger.debug(f"Processing {len(raw_results)} raw results for manual selection")
            
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
                    from dataclasses import asdict
                    processed_result['quality_assessment'] = asdict(quality_assessment)
                
                processed_results.append(processed_result)
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"Failed to process manual search results: {e}")
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
            self.logger.error(f"Failed to process automatic search results: {e}")
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