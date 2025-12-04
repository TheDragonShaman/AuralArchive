"""
Indexer Operations - Manages indexer connections and search distribution
Coordinates with indexer services and handles health monitoring

Location: services/search_engine/indexer_operations.py
Purpose: Indexer management for SearchEngineService
"""

from typing import Dict, List, Any, Optional
import time

from utils.logger import get_module_logger


class IndexerOperations:
    """
    Handles indexer management for the SearchEngineService.
    
    Features:
    - Indexer health monitoring
    - Search distribution across indexers
    - Indexer configuration management
    - Failover and retry logic
    """
    
    def __init__(self):
        """Initialize indexer operations."""
        self.logger = get_module_logger("SearchEngine.IndexerOperations")
        
        # Get the real IndexerServiceManager
        self.indexer_service_manager = None
        self._init_indexer_service_manager()
        
        self.search_timeout = 30
    
    def _init_indexer_service_manager(self):
        """Initialize connection to IndexerServiceManager."""
        try:
            from services.indexers import get_indexer_service_manager
            self.indexer_service_manager = get_indexer_service_manager()
            self.logger.info(f"Connected to IndexerServiceManager with {len(self.indexer_service_manager.indexers)} indexer(s)")
        except Exception as e:
            self.logger.error(f"Failed to initialize IndexerServiceManager: {e}")
            self.indexer_service_manager = None
    
    def get_indexer_status(self) -> Dict[str, Any]:
        """Get current status of all indexers."""
        try:
            if not self.indexer_service_manager:
                return {
                    'total_indexers': 0,
                    'healthy_indexers': 0,
                    'unhealthy_indexers': 0,
                    'error': 'IndexerServiceManager not available'
                }
            
            # Use the real indexer service manager
            return self.indexer_service_manager.get_service_status()
            
        except Exception as e:
            self.logger.error(f"Failed to get indexer status: {e}")
            return {'error': str(e)}
    
    def refresh_indexers(self) -> bool:
        """Refresh indexer list and perform health check."""
        try:
            self.logger.info("Refreshing indexer list...")
            
            if not self.indexer_service_manager:
                self.logger.warning("IndexerServiceManager not available, reinitializing...")
                self._init_indexer_service_manager()
                return self.indexer_service_manager is not None
            
            # Reload indexers from configuration
            self.indexer_service_manager.reload_indexers()
            
            self.logger.info(f"Indexer refresh complete: {len(self.indexer_service_manager.indexers)} indexers loaded")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to refresh indexers: {e}")
            return False
    
    def test_indexer_search(self, indexer_id: str, title: str = "Anima", 
                           author: str = "Blake Crouch") -> Dict[str, Any]:
        """Test search functionality for a specific indexer."""
        try:
            if not self.indexer_service_manager:
                return {
                    'success': False,
                    'error': 'IndexerServiceManager not available'
                }
            
            if indexer_id not in self.indexer_service_manager.indexers:
                return {
                    'success': False,
                    'error': f'Indexer {indexer_id} not found'
                }
            
            indexer = self.indexer_service_manager.indexers[indexer_id]
            
            self.logger.info(f"Testing search for indexer: {indexer.name}")
            
            start_time = time.time()
            
            # Use real indexer search
            results = indexer.search(
                query=f"{title} {author}",
                title=title,
                author=author,
                limit=10
            )
            
            search_time = time.time() - start_time
            
            return {
                'success': True,
                'indexer_name': indexer.name,
                'search_time': round(search_time, 2),
                'result_count': len(results),
                'sample_results': results[:3],  # First 3 results
                'test_query': f"{title} by {author}"
            }
            
        except Exception as e:
            self.logger.error(f"Indexer test failed for {indexer_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def search_all_indexers(self, title: str, author: str, 
                           manual_search: bool = False) -> List[Dict[str, Any]]:
        """Search all active indexers for audiobook results."""
        try:
            if not self.indexer_service_manager:
                self.logger.error("IndexerServiceManager not available for search")
                return []
            
            indexer_count = len(self.indexer_service_manager.indexers)
            self.logger.info(f"Searching {indexer_count} indexers for: {title} by {author}")
            
            # Use the real IndexerServiceManager's parallel search
            results = self.indexer_service_manager.search(
                query=f"{title} {author}",
                author=author,
                title=title,
                limit_per_indexer=50,
                parallel=True
            )
            
            self.logger.info(f"Total results from all indexers: {len(results)}")
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to search indexers: {e}", exc_info=True)
            return []
    
    def shutdown(self):
        """Shutdown indexer operations."""
        try:
            self.logger.debug("IndexerOperations shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during IndexerOperations shutdown: {e}")