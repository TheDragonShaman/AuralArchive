"""
Services Package - AuralArchive

Exports commonly-used service classes and the shared `ServiceManager` so other
modules can import from a single namespace.

Author: AuralArchive Development Team
Updated: December 4, 2025
"""

from .database import DatabaseService
from .audible.audible_catalog_service.audible_catalog_service import AudibleService
from .audiobookshelf import AudioBookShelfService
from .config import ConfigService
from .metadata import MetadataUpdateService
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