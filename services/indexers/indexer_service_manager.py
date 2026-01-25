"""
Module Name: indexer_service_manager.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Coordinates all indexer instances with priority-based selection and
    parallel search execution. Implements singleton pattern and integrates
    with search engine workflows.

Location:
    /services/indexers/indexer_service_manager.py

"""

import threading
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .base_indexer import BaseIndexer, IndexerProtocol
from .jackett_indexer import JackettIndexer
from .direct_indexer import DirectIndexer
from services.config.management import ConfigService
from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Indexers.Manager")


class IndexerServiceManager:
    """
    Singleton service manager for all indexer operations.
    
    Responsibilities:
    - Load and manage multiple indexers from configuration
    - Priority-based indexer selection (1-10, lower = higher priority)
    - Parallel search execution across all enabled indexers
    - Result aggregation and deduplication
    - Health monitoring and automatic failover
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config_service=None):
        """Ensure singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_service=None, *, logger=None):
        """Initialize the indexer service manager."""
        if self._initialized:
            return

        self.logger = logger or _LOGGER
        self.config_service = config_service or ConfigService()
        self.indexers = {}  # name -> indexer instance
        self.indexer_configs = {}  # name -> config dict
        
        # Load indexers from config
        self._load_indexers()
        
        self._initialized = True
        self.logger.debug("IndexerServiceManager initialized with %d indexer(s)", len(self.indexers))
    
    def _load_indexers(self):
        """Load and initialize indexers from configuration."""
        indexer_configs = {}

        try:
            indexer_configs = self.config_service.list_indexers_config()
            if indexer_configs:
                self.logger.debug("Loaded indexer configuration from config.txt")
        except Exception as exc:
            self.logger.error("Failed to load indexers from config service: %s", exc)

        if not indexer_configs:
            indexer_configs = self._load_from_config_py()
        
        if not indexer_configs:
            self.logger.warning("No indexers configured")
            return
        
        # Sort by priority (lower number = higher priority)
        sorted_configs = sorted(
            indexer_configs.items(),
            key=lambda x: x[1].get('priority', 999)
        )
        
        for name, config in sorted_configs:
            # Skip disabled indexers
            if not config.get('enabled', False):
                self.logger.debug("Skipping disabled indexer", extra={"indexer": name})
                continue
            
            try:
                # Add name to config if not already set (preserve user-defined names)
                if 'name' not in config or not config['name']:
                    config['name'] = name
                
                # Determine indexer type and create instance
                indexer_type = config.get('type', 'jackett').lower()
                
                if indexer_type == 'jackett':
                    indexer = JackettIndexer(config)
                elif indexer_type == 'prowlarr':
                    # Prowlarr uses same Torznab API as Jackett
                    indexer = JackettIndexer(config)
                elif indexer_type == 'nzbhydra2':
                    # Future: NZBHydra2Indexer
                    self.logger.warning("NZBHydra2 indexer not yet implemented, skipping", extra={"indexer": name})
                    continue
                elif indexer_type == 'direct':
                    indexer = DirectIndexer(config)
                else:
                    self.logger.error("Unknown indexer type", extra={"indexer": name, "indexer_type": indexer_type})
                    continue
                
                # Store indexer
                self.indexers[name] = indexer
                self.indexer_configs[name] = config
                
                self.logger.debug(
                    "Loaded indexer",
                    extra={
                        "indexer": name,
                        "priority": config.get('priority'),
                        "protocol": config.get('protocol'),
                    },
                )
                
            except Exception as e:
                self.logger.error("Failed to load indexer", extra={"indexer": name, "error": str(e)})
                continue
    
    def _load_from_config_py(self):
        """Load indexer config from config.py"""
        self.logger.debug("Loading indexers from config.py")
        from config.config import Config
        return getattr(Config, 'INDEXERS', {})
    
    def test_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """
        Test connections to all configured indexers.
        
        Returns:
            Dictionary mapping indexer names to test results
        """
        results = {}
        
        for name, indexer in self.indexers.items():
            self.logger.debug("Testing connection to %s...", name)
            result = indexer.test_connection()
            results[name] = result
            
            if result['success']:
                self.logger.info("%s connection successful", name)
            else:
                self.logger.error("%s connection failed: %s", name, result.get('error'))
        
        return results
    
    def search(
        self,
        query: str,
        author: Optional[str] = None,
        title: Optional[str] = None,
        limit_per_indexer: int = 100,
        parallel: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search all available indexers for audiobooks.
        
        Args:
            query: General search query
            author: Author name (optional)
            title: Book title (optional)
            limit_per_indexer: Max results per indexer (default: 100)
            parallel: Whether to search indexers in parallel (default: True)
            
        Returns:
            Aggregated list of results from all indexers
        """
        if not self.indexers:
            self.logger.warning("No indexers available for search")
            return []
        
        # Get available indexers
        available_indexers = [
            (name, indexer) for name, indexer in self.indexers.items()
            if indexer.is_available()
        ]
        
        if not available_indexers:
            self.logger.warning("No available indexers for search")
            return []
        
        self.logger.info(
            "Searching %d indexer(s) for query='%s' author='%s' title='%s'",
            len(available_indexers),
            query,
            author,
            title,
        )
        
        all_results = []
        
        if parallel and len(available_indexers) > 1:
            # Parallel search
            all_results = self._search_parallel(
                available_indexers, query, author, title, limit_per_indexer
            )
        else:
            # Sequential search
            for name, indexer in available_indexers:
                try:
                    results = indexer.search(
                        query=query,
                        author=author,
                        title=title,
                        limit=limit_per_indexer
                    )
                    self.logger.debug(
                        "Indexer returned results (sequential)",
                        extra={"indexer": name, "result_count": len(results) if results is not None else 0},
                    )
                    all_results.extend(results)
                except Exception as e:
                    self.logger.error("Error searching indexer", extra={"indexer": name, "error": str(e)})
                    continue
        
        self.logger.info("Total results from all indexers", extra={"result_count": len(all_results)})
        return all_results
    
    def _search_parallel(
        self,
        indexers: List[tuple],
        query: str,
        author: Optional[str],
        title: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Search multiple indexers in parallel using ThreadPoolExecutor.
        
        Args:
            indexers: List of (name, indexer) tuples
            query: Search query
            author: Author name
            title: Book title
            limit: Results limit per indexer
            
        Returns:
            Aggregated results from all indexers
        """
        all_results = []
        
        with ThreadPoolExecutor(max_workers=min(len(indexers), 5)) as executor:
            # Submit all search tasks
            future_to_indexer = {
                executor.submit(
                    indexer.search,
                    query=query,
                    author=author,
                    title=title,
                    limit=limit
                ): name
                for name, indexer in indexers
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_indexer):
                indexer_name = future_to_indexer[future]
                try:
                    results = future.result(timeout=60)  # 60 second timeout per indexer
                    all_results.extend(results)
                    self.logger.debug(
                        "Indexer returned results (parallel)",
                        extra={"indexer": indexer_name, "result_count": len(results)},
                    )
                except Exception as e:
                    self.logger.error("Error in parallel search", extra={"indexer": indexer_name, "error": str(e)})
        
        return all_results
    
    def get_indexer(self, name: str) -> Optional[BaseIndexer]:
        """
        Get a specific indexer by name.
        
        Args:
            name: Indexer name
            
        Returns:
            Indexer instance or None if not found
        """
        return self.indexers.get(name)
    
    def get_all_indexers(self) -> Dict[str, BaseIndexer]:
        """
        Get all loaded indexers.
        
        Returns:
            Dictionary mapping names to indexer instances
        """
        return self.indexers.copy()
    
    def get_indexer_status(self) -> List[Dict[str, Any]]:
        """
        Get status of all indexers.
        
        Returns:
            List of indexer status dictionaries
        """
        status_list = []
        
        for name, indexer in self.indexers.items():
            config = self.indexer_configs.get(name, {})
            info = indexer.get_indexer_info()
            
            status_list.append({
                'name': name,
                'priority': config.get('priority', 999),
                'enabled': config.get('enabled', False),
                'available': info['available'],
                'protocol': info['protocol'],
                'base_url': info['base_url'],
                'consecutive_failures': info['consecutive_failures'],
                'last_error': info['last_error'],
                'capabilities': info['capabilities']
            })
        
        return status_list
    
    def reload_indexers(self):
        """
        Reload indexers from configuration.
        Useful for applying config changes without restarting.
        """
        self.logger.info("Reloading indexers from configuration...")
        
        # Clear existing
        self.indexers.clear()
        self.indexer_configs.clear()
        
        # Reload
        self._load_indexers()
        
        self.logger.info("Reloaded %d indexer(s)", len(self.indexers))
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get overall service status.
        
        Returns:
            Dictionary with service health information
        """
        total_indexers = len(self.indexers)
        available_indexers = sum(1 for idx in self.indexers.values() if idx.is_available())
        
        return {
            'total_indexers': total_indexers,
            'available_indexers': available_indexers,
            'unavailable_indexers': total_indexers - available_indexers,
            'indexers': self.get_indexer_status()
        }


# Global singleton instance
_indexer_service_manager = None


def get_indexer_service_manager(config_service=None) -> IndexerServiceManager:
    """
    Get the global IndexerServiceManager instance.
    
    Args:
        config_service: Optional config service for initialization
        
    Returns:
        IndexerServiceManager singleton instance
    """
    global _indexer_service_manager
    if _indexer_service_manager is None:
        _indexer_service_manager = IndexerServiceManager(config_service)
    return _indexer_service_manager
