"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
	Package init for the file naming service. Provides AudioBookShelf-compatible
	file naming and path generation with template parsing and sanitization.

Location:
	/services/file_naming/__init__.py

"""

from .file_naming_service import FileNamingService

__all__ = ['FileNamingService']
