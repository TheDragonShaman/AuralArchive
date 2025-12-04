"""
File Naming Service Package
Provides AudioBookShelf-compatible file naming and path generation

Components:
- FileNamingService: Main service coordinator (singleton)
- TemplateParser: Template validation and parsing
- PathGenerator: Complete path generation
- PathSanitizer: Cross-platform path sanitization
"""

from .file_naming_service import FileNamingService

__all__ = ['FileNamingService']
