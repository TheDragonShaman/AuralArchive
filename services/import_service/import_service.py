"""
Import Service - Manages audiobook file importing to library
Handles file moving, database tracking, and library organization

Location: services/import/import_service.py
Purpose: Singleton service for importing audiobooks to library directory
"""

from typing import Any, Dict, Optional, Tuple, List
import logging
import threading
import os
import shutil
from pathlib import Path

from .file_operations import FileOperations
from .database_operations import ImportDatabaseOperations
from .validation import ImportValidator
from .asin_tag_embedder import AsinTagEmbedder


class ImportService:
    """
    Main import service following DatabaseService singleton pattern.
    
    Features:
    - Atomic file moving to library directory
    - Database tracking of file locations and metadata
    - File integrity validation
    - Import history and rollback support
    - Library organization using FileNamingService
    """
    
    _instance: Optional['ImportService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logging.getLogger("ImportService.Main")
                    
                    # Initialize operation components
                    self.file_ops = FileOperations()
                    self.db_ops = ImportDatabaseOperations()
                    self.validator = ImportValidator()
                    self.asin_embedder = AsinTagEmbedder()
                    
                    # Import filename matcher for auto-matching files to database
                    from .filename_matcher import FilenameMatcher
                    self.matcher = FilenameMatcher()
                    
                    # Service dependencies (lazy loaded)
                    self._file_naming_service = None
                    self._database_service = None
                    self._config_service = None
                    self._status_service = None
                    
                    # Import settings (loaded from config)
                    self.library_base_path = None
                    self.naming_template = 'standard'
                    self.verify_after_import = True
                    self.create_backup_on_error = True
                    
                    # Initialize service
                    self._initialize_service()
                    
                    ImportService._initialized = True
    
    def _initialize_service(self):
        """Initialize the import service."""
        try:
            self.logger.debug("Initializing ImportService...")
            
            # Configuration will be loaded lazily when first needed
            # to avoid circular dependency with ServiceManager
            
            self.logger.info("ImportService initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ImportService: {e}")
            raise
    
    def _load_configuration(self):
        """Load import configuration from ConfigService (called lazily)."""
        # Skip if already loaded
        if hasattr(self, '_config_loaded') and self._config_loaded:
            return
            
        try:
            # Import here to avoid circular dependency
            from services.service_manager import ServiceManager
            
            service_manager = ServiceManager()
            config_service = service_manager.get_config_service()
            
            if config_service:
                # Load library settings
                abs_config = config_service.get_section('audiobookshelf')
                self.library_base_path = abs_config.get('library_path', '/mnt/audiobooks')
                
                # Load naming settings
                self.naming_template = abs_config.get('naming_template', 'standard')
                
                # Load import settings
                import_config = config_service.get_section('import')
                self.verify_after_import = import_config.get('verify_after_import', True)
                self.create_backup_on_error = import_config.get('create_backup_on_error', True)
                
                self._config_loaded = True
                self.logger.debug(f"Loaded import configuration - Library: {self.library_base_path}, Template: {self.naming_template}")
        except Exception as e:
            self.logger.warning(f"Could not load configuration, using defaults: {e}")
            self.library_base_path = '/mnt/audiobooks'
            self.naming_template = 'standard'
            self._config_loaded = True  # Mark as attempted even if failed
    
    def _get_file_naming_service(self):
        """Lazy load FileNamingService."""
        if self._file_naming_service is None:
            from services.service_manager import ServiceManager
            service_manager = ServiceManager()
            self._file_naming_service = service_manager.get_file_naming_service()
        return self._file_naming_service
    
    def _get_database_service(self):
        """Lazy load DatabaseService."""
        if self._database_service is None:
            from services.service_manager import ServiceManager
            service_manager = ServiceManager()
            self._database_service = service_manager.get_database_service()
        return self._database_service

    def _get_status_service(self):
        if self._status_service is None:
            try:
                from services.service_manager import ServiceManager
                service_manager = ServiceManager()
                self._status_service = service_manager.get_status_service()
            except Exception:
                self._status_service = None
        return self._status_service
    
    # Main import methods
    def import_book(self, source_file_path: str, book_data: Dict,
                    template_name: Optional[str] = None,
                    library_path: Optional[str] = None,
                    move: bool = True,
                    import_source: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Import an audiobook file to the library.
        
        Args:
            source_file_path: Path to the source audiobook file
            book_data: Dictionary containing book metadata (ASIN, title, author, etc.)
            template_name: Optional naming template to use (defaults to service default)
            library_path: Optional library base path (defaults to configured path)
            move: If True, move file (default). If False, copy file (preserves source for seeding)
            import_source: Optional explicit source label to persist once the file is imported
            
        Returns:
            Tuple of (success: bool, message: str, destination_path: Optional[str])
        """
        try:
            # Lazy load configuration on first use
            self._load_configuration()

            tracker = self._get_status_service()
            status_id = None
            if tracker:
                asin = book_data.get('ASIN') or book_data.get('asin')
                event = tracker.start_event(
                    category='import',
                    title=f"Importing {book_data.get('Title', 'Unknown')}",
                    message='Preparing files…',
                    source='Import Service',
                    entity_id=asin or source_file_path,
                    metadata={'asin': asin, 'source': source_file_path}
                )
                status_id = event['id']

            def mark_failure(message: str):
                if tracker and status_id:
                    tracker.fail_event(status_id, message=message)

            def mark_progress(message: str, progress: float = None):
                if tracker and status_id:
                    updates = {'message': message}
                    if progress is not None:
                        updates['progress'] = progress
                    tracker.update_event(status_id, **updates)

            def mark_success(message: str):
                if tracker and status_id:
                    tracker.complete_event(status_id, message=message)
            
            # Validate inputs
            is_valid, error_msg = self.validator.validate_import_request(source_file_path, book_data)
            if not is_valid:
                mark_failure(error_msg)
                return False, error_msg, None
            
            # Use defaults if not provided
            template_name = template_name or self.naming_template
            library_path = library_path or self.library_base_path
            
            # Validate library path exists
            if not os.path.exists(library_path):
                self.logger.error(f"Library path does not exist: {library_path}")
                mark_failure(f"Library path does not exist: {library_path}")
                return False, f"Library path does not exist: {library_path}", None
            
            # Get file extension from source
            file_extension = Path(source_file_path).suffix.lstrip('.')
            
            # Generate destination path using FileNamingService
            naming_service = self._get_file_naming_service()
            destination_path = naming_service.generate_file_path(
                book_data=book_data,
                base_path=library_path,
                template_name=template_name,
                file_extension=file_extension
            )
            
            operation = "Moving" if move else "Copying"
            self.logger.info(f"{operation} '{book_data.get('Title', 'Unknown')}' to {destination_path}")
            mark_progress(f"{operation} files…", progress=25.0)
            
            # Check if destination already exists
            if os.path.exists(destination_path):
                self.logger.warning(f"Destination file already exists: {destination_path}")
                mark_failure(f"File already exists at destination: {destination_path}")
                return False, f"File already exists at destination: {destination_path}", None
            
            # Perform the file operation (move or copy)
            if move:
                success, message = self.file_ops.move_file_atomic(
                    source_file_path, 
                    destination_path,
                    verify=self.verify_after_import
                )
            else:
                # Copy instead of move (preserves source for torrent seeding)
                success, message = self.file_ops.copy_file_atomic(
                    source_file_path,
                    destination_path,
                    verify=self.verify_after_import
                )
            
            if not success:
                operation_name = "move" if move else "copy"
                mark_failure(f"File {operation_name} failed: {message}")
                return False, f"File {operation_name} failed: {message}", None
            
            asin = book_data.get('ASIN', book_data.get('asin'))
            stored_record = self._persist_book_record(book_data)
            if stored_record:
                book_data = stored_record
                asin = book_data.get('ASIN', book_data.get('asin'))

            normalized_source = self._determine_import_source(import_source, book_data)
            if normalized_source and book_data.get('source') != normalized_source:
                book_data['source'] = normalized_source

            if asin and self.asin_embedder:
                embedded = self.asin_embedder.embed_asin(destination_path, asin)
                if embedded:
                    self.logger.debug("Embedded ASIN %s into %s", asin, destination_path)

            # Get file metadata
            file_size = os.path.getsize(destination_path)
            file_format = file_extension.upper()
            file_quality = self.validator.detect_file_quality(destination_path)
            
            # Update database with file information
            if asin:
                db_success = self.db_ops.update_book_import_info(
                    asin=asin,
                    file_path=destination_path,
                    file_size=file_size,
                    file_format=file_format,
                    file_quality=file_quality,
                    naming_template=template_name,
                    database_service=self._get_database_service(),
                    source_label=normalized_source
                )
                
                if not db_success:
                    self.logger.warning(f"File imported but database update failed for ASIN: {asin}")
            
            operation_past = "moved" if move else "copied"
            self.logger.info(f"Successfully {operation_past} book to {destination_path}")
            mark_success(f"Import complete → {destination_path}")
            return True, f"Import successful ({operation_past})", destination_path
            
        except Exception as e:
            self.logger.error(f"Error importing book: {e}", exc_info=True)
            if 'mark_failure' in locals():
                mark_failure(f"Import error: {str(e)}")
            return False, f"Import error: {str(e)}", None
    
    def auto_import_file(self, source_file_path: str, 
                        asin: Optional[str] = None,
                        template_name: Optional[str] = None,
                        library_path: Optional[str] = None,
                        move: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        Import a file using ASIN (extracted from filename or provided).
        
        Args:
            source_file_path: Path to the source audiobook file
            asin: Optional ASIN (if not provided, will try to extract from filename)
            template_name: Optional naming template (defaults to service default)
            library_path: Optional library base path (defaults to configured path)
            move: If True, move file (default). If False, copy file (preserves source for seeding)
            
        Returns:
            Tuple of (success: bool, message: str, destination_path: Optional[str])
        """
        try:
            # Lazy load configuration on first use
            self._load_configuration()
            
            # Extract filename
            filename = os.path.basename(source_file_path)
            self.logger.info(f"Importing file: {filename}")
            
            # Get or extract ASIN
            if not asin:
                asin = self.matcher.extract_asin_from_filename(filename)
                if not asin:
                    return False, f"No ASIN found in filename and none provided. Filename must contain ASIN in format [B0XXXXXXXXX]", None
            
            # Get book from database by ASIN
            book_data = self.matcher.get_book_by_asin(asin, self._get_database_service())
            
            if not book_data:
                return False, f"Book with ASIN {asin} not found in database. Add book to library first.", None
            
            # Import using matched metadata
            success, message, dest_path = self.import_book(
                source_file_path=source_file_path,
                book_data=book_data,
                template_name=template_name,
                library_path=library_path,
                move=move,
                import_source='manual_import'
            )
            
            return success, message, dest_path
            
        except Exception as e:
            self.logger.error(f"Error auto-importing file: {e}", exc_info=True)
            return False, f"Auto-import error: {str(e)}", None
    
    def search_books_for_import(self, search_term: str, limit: int = 10) -> List[Dict]:
        """
        Search books in database for manual import selection.
        
        Args:
            search_term: Title or author to search for
            limit: Maximum results
            
        Returns:
            List of matching books with ASIN, title, author
        """
        try:
            return self.matcher.search_books_by_title(
                search_term, 
                self._get_database_service(), 
                limit
            )
        except Exception as e:
            self.logger.error(f"Error searching books: {e}")
            return []
    
    def import_multiple_books(self, imports: list[Dict]) -> Dict[str, any]:
        """
        Import multiple audiobooks in batch.
        
        Args:
            imports: List of dicts with 'source_file_path', 'book_data', optional 'template_name'
            
        Returns:
            Dictionary with success count, failures, and results
        """
        results = {
            'total': len(imports),
            'successful': 0,
            'failed': 0,
            'results': []
        }
        
        for import_item in imports:
            source_path = import_item.get('source_file_path')
            book_data = import_item.get('book_data')
            template = import_item.get('template_name')
            library_override = import_item.get('library_path')
            move_flag = import_item.get('move')
            import_source = import_item.get('import_source')

            success, message, dest_path = self.import_book(
                source_file_path=source_path,
                book_data=book_data,
                template_name=template,
                library_path=library_override,
                move=move_flag if move_flag is not None else True,
                import_source=import_source
            )
            
            results['results'].append({
                'source': source_path,
                'destination': dest_path,
                'success': success,
                'message': message,
                'title': book_data.get('Title', 'Unknown')
            })
            
            if success:
                results['successful'] += 1
            else:
                results['failed'] += 1
        
        return results

    def _determine_import_source(self, requested_source: Optional[str], book_data: Dict[str, Any]) -> str:
        """Pick an appropriate source label once a file has been imported."""

        def normalize(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            value_str = str(value).strip().lower()
            return value_str or None

        candidate = normalize(requested_source)
        if not candidate:
            candidate = normalize(book_data.get('import_source'))
        if not candidate:
            candidate = normalize(book_data.get('source')) or normalize(book_data.get('metadata_source'))

        if not candidate or candidate in {'audible', 'audible_catalog'}:
            ownership_value = normalize(book_data.get('ownership_status')) or normalize(book_data.get('Status'))
            if ownership_value and 'download' in ownership_value:
                candidate = 'download_manager'
            else:
                candidate = 'manual_import'

        return candidate

    def _persist_book_record(self, book_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure the imported book exists in the database after transfer."""
        try:
            database_service = self._get_database_service()
        except Exception:
            database_service = None

        if not database_service:
            return None

        asin = book_data.get('ASIN') or book_data.get('asin')
        try:
            if asin:
                existing = database_service.get_book_by_asin(asin)
                if existing:
                    return existing

            added = database_service.add_book(
                book_data,
                status=book_data.get('Status') or book_data.get('status') or 'Owned'
            )
            if added:
                return added

            if asin:
                return database_service.get_book_by_asin(asin)
        except Exception as exc:
            self.logger.warning(
                "Unable to persist book metadata for '%s': %s",
                book_data.get('Title', 'Unknown'),
                exc
            )
        return None
    
    # Query methods
    def get_import_status(self, asin: str) -> Optional[Dict]:
        """
        Get import status for a book by ASIN.
        
        Args:
            asin: Book ASIN
            
        Returns:
            Dictionary with import information or None if not imported
        """
        return self.db_ops.get_book_import_info(asin, self._get_database_service())
    
    def is_book_imported(self, asin: str) -> bool:
        """
        Check if a book has been imported.
        
        Args:
            asin: Book ASIN
            
        Returns:
            True if imported, False otherwise
        """
        import_info = self.get_import_status(asin)
        return import_info is not None and import_info.get('imported_to_library', False)
    
    def get_file_path(self, asin: str) -> Optional[str]:
        """
        Get the library file path for a book.
        
        Args:
            asin: Book ASIN
            
        Returns:
            File path if imported, None otherwise
        """
        import_info = self.get_import_status(asin)
        return import_info.get('file_path') if import_info else None
    
    # Utility methods
    def verify_import(self, asin: str) -> Tuple[bool, str]:
        """
        Verify that an imported book's file still exists and is valid.
        
        Args:
            asin: Book ASIN
            
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        import_info = self.get_import_status(asin)
        
        if not import_info:
            return False, "Book not found in import records"
        
        file_path = import_info.get('file_path')
        if not file_path:
            return False, "No file path recorded"
        
        return self.validator.verify_file_exists(file_path)
    
    def remove_import_record(self, asin: str, delete_file: bool = False) -> Tuple[bool, str]:
        """
        Remove import record (and optionally the file) for a book.
        
        Args:
            asin: Book ASIN
            delete_file: If True, also delete the physical file
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Get import info first
            import_info = self.get_import_status(asin)
            if not import_info:
                return False, "Book not found in import records"
            
            # Delete physical file if requested
            if delete_file:
                file_path = import_info.get('file_path')
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        self.logger.info(f"Deleted file: {file_path}")
                    except Exception as e:
                        self.logger.error(f"Failed to delete file {file_path}: {e}")
                        return False, f"Failed to delete file: {str(e)}"
            
            # Remove database record
            success = self.db_ops.clear_book_import_info(asin, self._get_database_service())
            
            if success:
                return True, "Import record removed successfully"
            else:
                return False, "Failed to remove import record from database"
                
        except Exception as e:
            self.logger.error(f"Error removing import record: {e}")
            return False, f"Error: {str(e)}"
    
    def set_library_path(self, path: str):
        """Update the library base path."""
        if os.path.exists(path):
            self.library_base_path = path
            self.logger.info(f"Updated library path to: {path}")
        else:
            self.logger.error(f"Library path does not exist: {path}")
    
    def set_naming_template(self, template: str):
        """Update the default naming template."""
        self.naming_template = template
        self.logger.debug(f"Updated naming template to: {template}")
