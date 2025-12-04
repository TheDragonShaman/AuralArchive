"""
AudioBookShelf Service - Main Coordinator
File: services/audiobookshelf/service.py
Coordinates all AudioBookShelf operations using specialized modules
"""
import logging
from typing import List, Dict, Optional, Tuple
from services.config import ConfigService

# Import specialized modules
from .connection import AudioBookShelfConnection
from .libraries import AudioBookShelfLibraries
from .syncfromabs import AudioBookShelfSync
from .serverinfo import AudioBookShelfServerInfo

class AudioBookShelfService:
    """Main AudioBookShelf service that coordinates specialized modules."""
    
    def __init__(self):
        self.logger = logging.getLogger("AudioBookShelfService")
        self.config_service = ConfigService()
        
        # Initialize specialized modules
        self.connection = AudioBookShelfConnection()
        self.libraries = AudioBookShelfLibraries(self.connection)
        self.sync = AudioBookShelfSync(self.connection, self.libraries, self.config_service)
        self.server_info = AudioBookShelfServerInfo(self.connection)
    
    # Connection methods (delegate to connection module)
    def test_connection(self, host: str = None, api_key: str = None) -> Tuple[bool, str]:
        """Test connection to AudioBookShelf server."""
        return self.connection.test_connection(host, api_key)
    
    # Library methods (delegate to libraries module)
    def get_libraries(self, host: str = None, api_key: str = None) -> List[Dict]:
        """Get list of libraries from AudioBookShelf."""
        return self.libraries.get_libraries(host, api_key)
    
    def get_library_items(self, library_id: str, limit: int = 100, page: int = 0) -> Tuple[bool, List[Dict], str]:
        """Get items from a specific library."""
        return self.libraries.get_library_items(library_id, limit, page)
    
    def search_library_items(self, library_id: str, query: str) -> Tuple[bool, List[Dict], str]:
        """Search for items in a specific library."""
        return self.libraries.search_library_items(library_id, query)
    
    # Sync methods (delegate to sync module)
    def sync_from_audiobookshelf(self) -> Dict:
        """Sync books FROM AudioBookShelf TO AuralArchive database."""
        from services.service_manager import get_database_service
        database_service = get_database_service()
        success, count, message = self.sync.sync_from_audiobookshelf(database_service)
        return {
            'success': success,
            'synced_count': count,
            'message': message
        }
    
    # Server info methods (delegate to server info module)
    def get_server_info(self) -> Tuple[bool, Dict, str]:
        """Get AudioBookShelf server information."""
        return self.server_info.get_server_info()
    
    def get_server_status(self) -> Tuple[bool, Dict, str]:
        """Get basic server status."""
        return self.server_info.get_server_status()
    
    # Legacy methods for backward compatibility
    def sync_library_to_abs(self, books: List[Dict]) -> Tuple[bool, int, str]:
        """Legacy method - redirects to sync_from_audiobookshelf."""
        self.logger.warning("sync_library_to_abs is deprecated. Use sync_from_audiobookshelf instead.")
        return False, 0, "This method is deprecated. Use sync_from_audiobookshelf to import from AudioBookShelf to AuralArchive."
    