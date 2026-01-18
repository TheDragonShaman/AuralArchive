"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
	Package initializer for the import service. Exposes the main import
	service, metadata extraction helpers, and high-level local importer
	coordinator used by manual and automated workflows.

Location:
	/services/import_service/__init__.py

"""

from .import_service import ImportService
from .local_metadata_extractor import LocalMetadataExtractor
from .local_file_importer import LocalFileImportCoordinator

__all__ = ['ImportService', 'LocalMetadataExtractor', 'LocalFileImportCoordinator']
