"""
Module Name: audiobookshelf_service.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Coordinate AudioBookShelf operations across connection, libraries, sync, server info, and matching helpers.
Location:
    /services/audiobookshelf/audiobookshelf_service.py

"""
from typing import Dict, List, Optional, Tuple

from services.config import ConfigService
from utils.logger import get_module_logger

from .connection import AudioBookShelfConnection
from .libraries import AudioBookShelfLibraries
from .matcher import AudioBookShelfMatcher
from .serverinfo import AudioBookShelfServerInfo
from .syncfromabs import AudioBookShelfSync

class AudioBookShelfService:
    """Main AudioBookShelf service that coordinates specialized modules."""

    def __init__(
        self,
        *,
        config_service: Optional[ConfigService] = None,
        connection: Optional[AudioBookShelfConnection] = None,
        libraries: Optional[AudioBookShelfLibraries] = None,
        sync: Optional[AudioBookShelfSync] = None,
        server_info: Optional[AudioBookShelfServerInfo] = None,
        matcher: Optional[AudioBookShelfMatcher] = None,
        logger=None,
    ) -> None:
        self.logger = logger or get_module_logger("Service.AudioBookShelf.Main")
        self.config_service = config_service or ConfigService()

        # Initialize specialized modules with optional overrides
        self.connection = connection or AudioBookShelfConnection(config_service=self.config_service)
        self.libraries = libraries or AudioBookShelfLibraries(self.connection)
        self.sync = sync or AudioBookShelfSync(self.connection, self.libraries, self.config_service)
        self.server_info = server_info or AudioBookShelfServerInfo(self.connection)
        self.matcher = matcher or AudioBookShelfMatcher(self.connection)
    
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

    # Matching helpers
    def auto_match_imported_item(
        self,
        asin: str,
        title: str = "",
        library_id: str = "",
        delay_seconds: int = 10,
    ) -> Tuple[bool, str]:
        """Wrapper to trigger post-import ABS matching."""

        return self.matcher.match_imported_item(
            asin=asin,
            title=title,
            library_id=library_id,
            delay_seconds=delay_seconds,
        )
    
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
        self.logger.warning(
            "sync_library_to_abs is deprecated; use sync_from_audiobookshelf instead",
            extra={"method": "sync_library_to_abs", "replacement": "sync_from_audiobookshelf"},
        )
        return False, 0, "This method is deprecated. Use sync_from_audiobookshelf to import from AudioBookShelf to AuralArchive."
    