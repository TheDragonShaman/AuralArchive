"""
Module Name: base_indexer.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Abstract base class for all indexer implementations (Jackett, Prowlarr,
    direct providers). Defines the interface and shared helpers for Torznab
    and direct indexers.

Location:
    /services/indexers/base_indexer.py

"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Indexers.Base")


class IndexerProtocol(Enum):
    """Supported indexer protocols."""
    TORZNAB = "torznab"  # Jackett, Prowlarr (torrents)
    DIRECT = "direct"    # Custom direct provider API


class IndexerType(Enum):
    """Types of indexers."""
    PUBLIC = "public"      # Public trackers/indexers
    PRIVATE = "private"    # Private trackers requiring auth
    SEMI_PRIVATE = "semi-private"  # Mixed access


class BaseIndexer(ABC):
    """
    Abstract base class for indexer implementations.
    
    All indexer implementations must inherit from this class
    and implement all abstract methods.
    """
    
    # Standard Torznab categories
    CATEGORY_AUDIOBOOK = "3030"  # Standard audiobook category
    CATEGORY_ALL = "8000"        # All audio categories
    
    def __init__(self, config: Dict[str, Any], *, logger=None):
        """
        Initialize the indexer.
        
        Args:
            config: Indexer configuration dictionary with keys:
                - name: Indexer name (user-friendly)
                - base_url: Base URL of the indexer
                - api_key: API key for authentication
                - protocol: 'torznab' or 'direct'
                - categories: List of category IDs to search (optional)
                - timeout: Request timeout in seconds (optional, default 30)
                - verify_ssl: Whether to verify SSL certificates (optional, default True)
        """
        self.config = config
        self.name = config.get('name', self.__class__.__name__)
        self.base_url = config['base_url'].rstrip('/')
        self.api_key = config.get('api_key', '')
        protocol_value = config.get('protocol', 'torznab')
        try:
            self.protocol = IndexerProtocol(protocol_value)
        except ValueError:
            self.protocol = IndexerProtocol.TORZNAB
        self.timeout = config.get('timeout', 30)
        self.verify_ssl = config.get('verify_ssl', True)
        
        # Categories to search (default to audiobooks)
        self.categories = config.get('categories', [self.CATEGORY_AUDIOBOOK])
        
        # Health tracking
        self.available = True
        self.last_error = None
        self.last_success = None
        self.consecutive_failures = 0
        
        # Capabilities (populated by test_connection)
        self.capabilities = {}

        # Logger
        self.logger = logger or _LOGGER
        
        self.logger.debug(f"Initializing {self.name} indexer at {self.base_url}")
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the indexer and verify API key.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to the indexer and retrieve capabilities.
        
        Returns:
            Dictionary with:
                - success: bool - Whether connection test passed
                - capabilities: dict - Indexer capabilities (categories, search types)
                - version: str - Indexer version if available
                - error: str - Error message if failed
        """
        pass
    
    @abstractmethod
    def search(
        self,
        query: str,
        author: Optional[str] = None,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search the indexer for audiobooks.
        
        Args:
            query: General search query (book title, author, etc.)
            author: Author name (optional, for targeted search)
            title: Book title (optional, for targeted search)
            limit: Maximum number of results to return (default: 100)
            offset: Offset for pagination (default: 0)
            
        Returns:
            List of result dictionaries with:
                - indexer: str - Name of this indexer
                - title: str - Release title
                - download_url: str - .torrent URL
                - size_bytes: int - File size in bytes
                - publish_date: str - ISO format date
                - seeders: int - Number of seeders (torrent indexers)
                - peers: int - Number of peers (torrent indexers)
                - protocol: str - 'torrent'
                - indexer_id: str - Unique ID from indexer
                - category: str - Category ID
                - info_url: str - URL to details page (optional)
                
        Raises:
            ConnectionError: If indexer is unavailable
            ValueError: If search parameters are invalid
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get indexer capabilities from /api?t=caps endpoint.
        
        Returns:
            Dictionary with:
                - search_available: bool - General search supported
                - book_search_available: bool - Book-specific search supported
                - author_search_available: bool - Author search supported
                - categories: list - Available category IDs
                - limits: dict - Rate limits and max results
        """
        pass
    
    def get_indexer_info(self) -> Dict[str, Any]:
        """
        Get information about this indexer.
        
        Returns:
            Dictionary with:
                - name: str - Indexer name
                - protocol: str - torznab or direct
                - base_url: str - Base URL
                - available: bool - Whether indexer is currently available
                - consecutive_failures: int - Number of consecutive failures
                - last_error: str - Last error message
                - capabilities: dict - Indexer capabilities
        """
        return {
            'name': self.name,
            'protocol': self.protocol.value,
            'base_url': self.base_url,
            'available': self.available,
            'consecutive_failures': self.consecutive_failures,
            'last_error': self.last_error,
            'capabilities': self.capabilities
        }
    
    def is_available(self) -> bool:
        """
        Check if indexer is currently available.
        
        Returns:
            True if available, False otherwise
        """
        return self.available and self.consecutive_failures < 3
    
    def mark_failure(self, error: str) -> None:
        """
        Mark a failed request to this indexer.
        
        Args:
            error: Error message
        """
        self.last_error = error
        self.consecutive_failures += 1
        
        if self.consecutive_failures >= 3:
            self.available = False
            self.logger.warning(f"{self.name} marked unavailable after {self.consecutive_failures} failures")
        
        self.logger.error(f"{self.name} failure: {error}")
    
    def mark_success(self) -> None:
        """Mark a successful request to this indexer."""
        from datetime import datetime
        
        self.last_error = None
        self.consecutive_failures = 0
        self.available = True
        self.last_success = datetime.now()
        
        self.logger.debug(f"{self.name} request successful")
    
    def _build_api_url(self, endpoint: str = 'api') -> str:
        """
        Build full API URL.
        
        Args:
            endpoint: API endpoint (default: 'api')
            
        Returns:
            Full URL to API endpoint
        """
        return f"{self.base_url}/{endpoint}"
    
    def _get_standard_params(self, search_type: str = 'search') -> Dict[str, Any]:
        """
        Get standard Torznab API parameters.
        
        Args:
            search_type: Type of search (search, book, caps)
            
        Returns:
            Dictionary of standard parameters
        """
        params = {
            't': search_type,
            'apikey': self.api_key
        }
        
        # Add categories if searching
        if search_type in ['search', 'book']:
            if self.categories:
                params['cat'] = ','.join(self.categories)
        
        return params
    
    def __repr__(self) -> str:
        """String representation of the indexer."""
        return f"{self.__class__.__name__}(name={self.name}, protocol={self.protocol.value}, available={self.available})"
