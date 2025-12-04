"""
Import Service Package
Provides audiobook file importing to library with database tracking

Components:
- ImportService: Main service coordinator (singleton)
- LocalMetadataExtractor: ID3/path metadata reader
- LocalFileImportCoordinator: High-level helper for manual imports
- FileOperations: Atomic file moving and verification
- ImportDatabaseOperations: Database tracking of imports
- ImportValidator: Validation and quality detection
"""

from .import_service import ImportService
from .local_metadata_extractor import LocalMetadataExtractor
from .local_file_importer import LocalFileImportCoordinator

__all__ = ['ImportService', 'LocalMetadataExtractor', 'LocalFileImportCoordinator']
