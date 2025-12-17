# Services package for AuralArchive Flask app
# Clean modular structure - all services are now in subdirectories

# Import from modular service directories that exist
from .database import DatabaseService
from .audible.audible_catalog_service.audible_catalog_service import AudibleService
from .audiobookshelf import AudioBookShelfService
from .config import ConfigService
from .metadata import MetadataUpdateService

# Import service manager
from .service_manager import ServiceManager, service_manager

__all__ = [
    # Core services
    'DatabaseService',
    'AudibleService', 
    'AudioBookShelfService',
    'ConfigService',
    'MetadataUpdateService',
    
    # Service manager
    'ServiceManager',
    'service_manager'
]