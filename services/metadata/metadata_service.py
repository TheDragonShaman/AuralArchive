import logging
import threading
import time
from typing import Tuple, Dict, List, Optional, Callable

from .metadata_lookup_strategies import MetadataSearchStrategies
from .matching import MetadataMatching
from .database_updates import MetadataDatabaseUpdates
from .error_handling import MetadataErrorHandler


class CancellationContext:
    """Context object for tracking and checking operation cancellation"""
    
    def __init__(self, operation_id: str, cancellation_checker: Callable[[str], bool]):
        self.operation_id = operation_id
        self.cancellation_checker = cancellation_checker
        self.cancelled = False
    
    def check_cancellation(self) -> bool:
        """Check if the operation has been cancelled"""
        if not self.cancelled:
            self.cancelled = self.cancellation_checker(self.operation_id)
        return self.cancelled
    
    def raise_if_cancelled(self):
        """Raise exception if operation has been cancelled"""
        if self.check_cancellation():
            raise CancellationException(f"Operation {self.operation_id} was cancelled")


class CancellationException(Exception):
    """Exception raised when an operation is cancelled"""
    pass

class MetadataUpdateService:
    """Enhanced singleton service for updating book metadata with modular components"""
    
    _instance = None
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
                    self.logger = logging.getLogger("MetadataUpdateService.Main")
                    
                    # Initialize service references as None - will be lazy loaded
                    self.audible_service = None
                    self.database_service = None
                    self.search_strategies = None
                    self.database_updates = None
                    
                    # Initialize basic components that don't depend on other services
                    self.matching = MetadataMatching()
                    self.error_handler = MetadataErrorHandler()
                    
                    self.logger.info("MetadataUpdateService initialized successfully (lazy loading)")
                    MetadataUpdateService._initialized = True
    
    def _ensure_dependencies(self):
        """Lazy load dependencies when first needed"""
        if self.audible_service is None or self.database_service is None:
            try:
                from services.service_manager import get_audible_service, get_database_service
                
                if self.audible_service is None:
                    self.audible_service = get_audible_service()
                    
                if self.database_service is None:
                    self.database_service = get_database_service()
                    
                if self.search_strategies is None:
                    from .metadata_lookup_strategies import MetadataSearchStrategies
                    self.search_strategies = MetadataSearchStrategies(self.audible_service)
                    
                if self.database_updates is None:
                    from .database_updates import MetadataDatabaseUpdates
                    self.database_updates = MetadataDatabaseUpdates(self.database_service)
                
                self.logger.info("Service dependencies lazy loaded successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to lazy load dependencies: {e}")
                raise

    def _initialize_dependencies(self):
        """Initialize service dependencies via service manager"""
        # This method is now deprecated in favor of lazy loading
        self._ensure_dependencies()
    
    def _validate_service_setup(self):
        """Validate that all components are properly initialized"""
        try:
            # Ensure dependencies are loaded first
            self._ensure_dependencies()
            
            # Test database connection
            db_valid, db_message = self.database_updates.validate_database_connection()
            if not db_valid:
                self.logger.warning(f"Database validation failed: {db_message}")
            
            # Test search strategies
            search_valid = self.search_strategies.validate_search_strategy_config()
            if not search_valid:
                self.logger.warning("Search strategies validation failed")
            
            self.logger.info("Service setup validation completed")
            
        except Exception as e:
            self.logger.error(f"Service validation error: {e}")
    
    @MetadataErrorHandler().with_retry(max_retries=2, retry_delay=1.0)
    def update_single_book(self, book_id: int, cancellation_context: Optional[CancellationContext] = None) -> Tuple[bool, str]:
        """
        Update metadata for a single book from the database
        
        Args:
            book_id: Database ID of the book to update
            cancellation_context: Optional context for checking operation cancellation
            
        Returns:
            Tuple of (success: bool, message: str)
            
        Raises:
            CancellationException: If the operation is cancelled
        """
        try:
            # Check for cancellation before starting
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            # Ensure dependencies are loaded
            self._ensure_dependencies()
            
            # Check for cancellation after dependency loading
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            # Get book from database
            book_data = self.database_service.get_book_by_id(book_id)
            
            if not book_data:
                return False, f"Book with ID {book_id} not found in database"
            
            # Check for cancellation after database retrieval
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            self.logger.info(f"Updating metadata for book {book_id}: '{book_data.get('Title', 'Unknown')}' by '{book_data.get('Author', 'Unknown')}'")
            
            # Extract current book information
            current_title = book_data.get('Title', '')
            current_author = book_data.get('Author', '')
            current_asin = book_data.get('ASIN', '')
            current_status = book_data.get('Status', 'Wanted')
            
            # Check for cancellation before metadata search (most time-consuming operation)
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            # Search for fresh metadata using search strategies
            fresh_metadata = self.search_strategies.search_for_book_metadata(
                title=current_title,
                author=current_author,
                asin=current_asin,
                cancellation_context=cancellation_context  # Pass cancellation context to search
            )
            
            # Check for cancellation after metadata search
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            if not fresh_metadata:
                self.logger.warning(f"No metadata found for book {book_id}: '{current_title}' by '{current_author}'")
                return False, "No metadata found for this book"
            
            self.logger.info(f"Found fresh metadata for book {book_id}: '{fresh_metadata.get('title', 'Unknown')}' by '{fresh_metadata.get('author', 'Unknown')}'")
            
            # Check for cancellation before database update
            if cancellation_context:
                cancellation_context.raise_if_cancelled()
            
            # Update the book in database with fresh metadata
            update_success, update_message = self.database_updates.update_book_in_database(
                book_id=book_id,
                fresh_metadata=fresh_metadata,
                current_status=current_status
            )
            
            if update_success:
                self.logger.info(f"Successfully updated metadata for book {book_id}")
                return True, "Metadata updated successfully"
            else:
                self.logger.error(f"Failed to update book {book_id} in database: {update_message}")
                return False, f"Database update failed: {update_message}"
                
        except CancellationException:
            # Re-raise cancellation exceptions
            self.logger.info(f"Metadata update for book {book_id} was cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Error updating book {book_id}: {e}")
            return False, str(e)
    
    def update_multiple_books(self, book_ids: List[int]) -> Dict[str, any]:
        """Update metadata for multiple books in batch"""
        try:
            # Ensure dependencies are loaded
            self._ensure_dependencies()
            
            self.logger.info(f"Starting batch metadata update for {len(book_ids)} books")
            
            results = {
                'total': len(book_ids),
                'successful': 0,
                'failed': 0,
                'errors': [],
                'updated_books': []
            }
            
            for book_id in book_ids:
                try:
                    success, message = self.update_single_book(book_id)
                    
                    if success:
                        results['successful'] += 1
                        results['updated_books'].append({
                            'book_id': book_id,
                            'message': message
                        })
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'book_id': book_id,
                            'error': message
                        })
                        
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'book_id': book_id,
                        'error': str(e)
                    })
            
            summary_message = f"Batch update completed: {results['successful']} successful, {results['failed']} failed"
            self.logger.info(summary_message)
            results['summary'] = summary_message
            
            return results
            
        except Exception as e:
            error_message = f"Error in batch update: {e}"
            self.logger.error(error_message)
            return {
                'total': len(book_ids),
                'successful': 0,
                'failed': len(book_ids),
                'errors': [{'error': error_message}],
                'summary': error_message
            }
    
    def find_books_needing_updates(self, limit: int = 100) -> List[Dict]:
        """Find books that might benefit from metadata updates"""
        try:
            return self.database_updates.find_books_needing_metadata_updates(limit)
        except Exception as e:
            self.logger.error(f"Error finding books needing updates: {e}")
            return []
    
    def search_by_author(self, author: str, title_hint: str = "") -> List[Dict]:
        """Search for books by author (utility method)"""
        try:
            return self.search_strategies.search_by_author_only(author, title_hint)
        except Exception as e:
            self.logger.error(f"Error searching by author '{author}': {e}")
            return []
    
    def search_by_series(self, series_name: str, sequence: str = "") -> List[Dict]:
        """Search for books in series (utility method)"""
        try:
            return self.search_strategies.search_by_series(series_name, sequence)
        except Exception as e:
            self.logger.error(f"Error searching by series '{series_name}': {e}")
            return []
    
    def get_service_status(self) -> Dict[str, any]:
        """Get comprehensive service status"""
        try:
            # Component status
            components = {
                'search_strategies': bool(self.search_strategies),
                'matching': bool(self.matching),
                'database_updates': bool(self.database_updates),
                'error_handler': bool(self.error_handler)
            }
            
            # Dependency status
            dependencies = {
                'audible_service': bool(self.audible_service),
                'database_service': bool(self.database_service)
            }
            
            # Get update statistics
            if self.database_updates:
                update_stats = self.database_updates.get_update_statistics()
            else:
                update_stats = {'pending': 0, 'completed': 0, 'failed': 0}
            
            if self.search_strategies:
                search_stats = self.search_strategies.get_strategy_stats()
            else:
                search_stats = {}
            
            # Test connections
            if self.database_updates:
                db_valid, db_message = self.database_updates.validate_database_connection()
            else:
                db_valid, db_message = False, "Database updates component not initialized"
            
            if self.search_strategies:
                search_valid = self.search_strategies.validate_search_strategy_config()
            else:
                search_valid = False
            
            status = {
                'service_name': 'MetadataUpdateService',
                'initialized': self._initialized,
                'components': components,
                'dependencies': dependencies,
                'update_statistics': update_stats,
                'search_statistics': search_stats,
                'database_connection': {
                    'valid': db_valid,
                    'message': db_message
                },
                'search_strategies': {
                    'valid': search_valid
                }
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {'error': str(e)}
    
    def test_update_process(self, book_id: int) -> Dict[str, any]:
        """Test the update process without making changes (dry run)"""
        try:
            self.logger.info(f"Testing update process for book ID: {book_id}")
            
            # Get book data
            success, book_data, message = self.database_updates.get_book_from_database(book_id)
            if not success:
                return {'success': False, 'error': message}
            
            # Extract book info
            title = book_data.get('Title', '').strip()
            author = book_data.get('Author', '').strip()
            asin = book_data.get('ASIN', '').strip()
            
            # Test search
            fresh_metadata = self.search_strategies.search_for_book_metadata(title, author, asin)
            
            test_result = {
                'success': True,
                'book_id': book_id,
                'current_title': title,
                'current_author': author,
                'current_asin': asin,
                'search_successful': fresh_metadata is not None,
                'found_metadata': fresh_metadata if fresh_metadata else None,
                'would_update': fresh_metadata is not None
            }
            
            if fresh_metadata:
                test_result['potential_changes'] = {
                    'title': fresh_metadata.get('Title') != title,
                    'author': fresh_metadata.get('Author') != author,
                    'summary_available': bool(fresh_metadata.get('Summary', '').strip()),
                    'cover_available': bool(fresh_metadata.get('Cover Image', '').strip())
                }
            
            return test_result
            
        except Exception as e:
            self.logger.error(f"Error testing update process: {e}")
            return {'success': False, 'error': str(e)}
    
    def reset_service(self):
        """Reset the service (for testing or troubleshooting)"""
        with self._lock:
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("MetadataUpdateService reset")

# Legacy compatibility - maintain the original interface for existing code
def get_metadata_update_service():
    """Get MetadataUpdateService instance (legacy compatibility)"""
    return MetadataUpdateService()
