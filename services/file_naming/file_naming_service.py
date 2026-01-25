"""
Module Name: file_naming_service.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Singleton service for generating AudioBookShelf-compatible file paths and
    filenames using user-configurable templates and sanitization helpers.

Location:
    /services/file_naming/file_naming_service.py

"""

from typing import Dict, Optional, List
import threading

from .template_parser import TemplateParser
from .path_generator import PathGenerator
from .sanitizer import PathSanitizer
from utils.logger import get_module_logger

_LOGGER = get_module_logger("Service.FileNaming.Main")


class FileNamingService:
    """
    Main file naming service following DatabaseService singleton pattern.
    
    Features:
    - AudioBookShelf naming convention support
    - User-configurable naming templates
    - ASIN bracket notation support
    - Path sanitization for cross-platform compatibility
    - Author/Series/Title organization
    """
    
    _instance: Optional['FileNamingService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, *_, logger=None, **__):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logger or _LOGGER
                    
                    # Initialize operation components
                    self.template_parser = TemplateParser()
                    self.path_generator = PathGenerator()
                    self.sanitizer = PathSanitizer()
                    
                    # Default naming templates (can be overridden by config)
                    # Only keep the minimal simple variants per user request.
                    self.templates = {
                        'simple': '{author}/{series}/{title}/{title}',
                        'simple_asin': '{author}/{series}/{title}/{title} [{asin}]'
                    }
                    
                    # ABS-specific settings
                    self.include_asin = False  # Will be set by config
                    self.create_author_folders = True
                    self.create_series_folders = True
                    
                    # Initialize service
                    self._initialize_service()
                    
                    FileNamingService._initialized = True
    
    def _initialize_service(self):
        """Initialize the file naming service."""
        try:
            self.logger.debug("Initializing FileNamingService...")
            
            # Configuration will be loaded lazily when first needed
            # to avoid circular dependency with ServiceManager
            
            self.logger.success("File naming service started successfully")
        except Exception as e:
            self.logger.error("Failed to initialize FileNamingService", extra={"error": str(e)})
            raise
    
    def _load_configuration(self):
        """Load naming configuration from ConfigService (called lazily)."""
        # Skip if already loaded
        if hasattr(self, '_config_loaded') and self._config_loaded:
            return
            
        try:
            # Import here to avoid circular dependency
            from services.service_manager import ServiceManager
            
            service_manager = ServiceManager()
            config_service = service_manager.get_config_service()
            
            if config_service:
                abs_config = config_service.get_section('audiobookshelf')
                
                # Load naming settings
                self.include_asin = abs_config.get('include_asin_in_path', False)
                self.create_author_folders = abs_config.get('create_author_folders', True)
                self.create_series_folders = abs_config.get('create_series_folders', True)
                
                # Load custom templates if defined
                custom_templates = abs_config.get('naming_templates', {})
                if custom_templates:
                    self.templates.update(custom_templates)
                
                self._config_loaded = True
                self.logger.debug("Loaded naming configuration", extra={"include_asin": self.include_asin, "create_author_folders": self.create_author_folders, "create_series_folders": self.create_series_folders})
        except Exception as e:
            self.logger.warning("Could not load configuration, using defaults", extra={"error": str(e)})
            self._config_loaded = True  # Mark as attempted even if failed
    
    # Template management methods
    def get_template(self, template_name: str = 'simple') -> str:
        """Get a naming template by name."""
        return self.template_parser.get_template(template_name, self.templates)
    
    def add_custom_template(self, name: str, template: str) -> bool:
        """Add or update a custom naming template."""
        return self.template_parser.add_custom_template(name, template, self.templates)
    
    def validate_template(self, template: str) -> tuple[bool, Optional[str]]:
        """Validate a naming template."""
        return self.template_parser.validate_template(template)
    
    # Path generation methods
    def generate_file_path(self, book_data: Dict, base_path: str, template_name: str = 'simple', 
                          file_extension: str = 'm4b') -> str:
        """
        Generate a complete file path for an audiobook.
        
        Args:
            book_data: Dictionary containing book metadata (title, author, series, etc.)
            base_path: Base directory path (e.g., /audiobooks)
            template_name: Name of the template to use
            file_extension: File extension (default: m4b)
            
        Returns:
            Complete sanitized file path
        """
        # Lazy load configuration on first use
        self._load_configuration()
        
        return self.path_generator.generate_file_path(
            book_data=book_data,
            base_path=base_path,
            template=self.get_template(template_name),
            file_extension=file_extension,
            include_asin=self.include_asin,
            sanitizer=self.sanitizer
        )
    
    def generate_folder_path(self, book_data: Dict, base_path: str) -> str:
        """
        Generate just the folder path (no filename).
        
        Args:
            book_data: Dictionary containing book metadata
            base_path: Base directory path
            
        Returns:
            Complete sanitized folder path
        """
        # Lazy load configuration on first use
        self._load_configuration()
        
        return self.path_generator.generate_folder_path(
            book_data=book_data,
            base_path=base_path,
            create_author_folders=self.create_author_folders,
            create_series_folders=self.create_series_folders,
            sanitizer=self.sanitizer
        )
    
    def generate_filename(self, book_data: Dict, template_name: str = 'simple', 
                         file_extension: str = 'm4b') -> str:
        """
        Generate just the filename (no path).
        
        Args:
            book_data: Dictionary containing book metadata
            template_name: Name of the template to use
            file_extension: File extension (default: m4b)
            
        Returns:
            Sanitized filename
        """
        # Lazy load configuration on first use
        self._load_configuration()
        
        return self.path_generator.generate_filename(
            book_data=book_data,
            template=self.get_template(template_name),
            file_extension=file_extension,
            include_asin=self.include_asin,
            sanitizer=self.sanitizer
        )
    
    # Path sanitization methods
    def sanitize_path(self, path: str) -> str:
        """Sanitize a file path for cross-platform compatibility."""
        return self.sanitizer.sanitize_path(path)
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename for cross-platform compatibility."""
        return self.sanitizer.sanitize_filename(filename)
    
    # Utility methods
    def parse_abs_path(self, file_path: str) -> Dict[str, Optional[str]]:
        """
        Parse an existing ABS file path to extract metadata.
        
        Args:
            file_path: Full file path following ABS conventions
            
        Returns:
            Dictionary with extracted metadata (author, series, title, asin, etc.)
        """
        return self.path_generator.parse_abs_path(file_path, self.sanitizer)
    
    def get_available_templates(self) -> List[str]:
        """Get list of available template names."""
        return list(self.templates.keys())
    
    def get_template_preview(self, template_name: str, sample_book_data: Dict) -> str:
        """
        Generate a preview of what a filename would look like with a template.
        
        Args:
            template_name: Template to preview
            sample_book_data: Sample book data for preview
            
        Returns:
            Preview filename
        """
        try:
            return self.generate_filename(sample_book_data, template_name, 'm4b')
        except Exception as e:
            self.logger.error("Error generating template preview", extra={"error": str(e)})
            return f"Error: {str(e)}"
    
    def set_include_asin(self, include: bool):
        """Update the include_asin setting."""
        self.include_asin = include
        self.logger.debug("Updated include_asin setting", extra={"include_asin": include})
    
    def set_folder_creation(self, create_author: bool, create_series: bool):
        """Update folder creation settings."""
        self.create_author_folders = create_author
        self.create_series_folders = create_series
        self.logger.debug("Updated folder settings", extra={"create_author_folders": create_author, "create_series_folders": create_series})
