import os
import logging
import threading
from typing import List, Dict, Optional

from .connection import DatabaseConnection
from .migrations import DatabaseMigrations
from .books import BookOperations
from .authors import AuthorOperations
from .author_overrides import AuthorOverrideOperations
from .audible_library import AudibleLibraryOperations
from .stats import DatabaseStats
from .series import SeriesOperations

DEFAULT_DB_FILENAME = "auralarchive_database.db"
DEFAULT_DB_PATH = os.path.join("database", DEFAULT_DB_FILENAME)

class DatabaseService:
    """Enhanced singleton service for database operations with modular components"""
    
    _instance: Optional['DatabaseService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls, db_file: str = DEFAULT_DB_PATH):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_file: str = DEFAULT_DB_PATH):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = logging.getLogger("DatabaseService.Main")
                    self.db_file = self._normalize_db_file(db_file)
                    os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
                    
                    # Initialize modular components
                    self.connection_manager = DatabaseConnection(self.db_file)
                    self.migrations = DatabaseMigrations(self.connection_manager)
                    self.author_overrides = AuthorOverrideOperations(self.connection_manager)
                    self.books = BookOperations(self.connection_manager, self.author_overrides)
                    self.authors = AuthorOperations(self.connection_manager, self.author_overrides)
                    self.audible_library = AudibleLibraryOperations(self.connection_manager)
                    self.stats = DatabaseStats(self.connection_manager)
                    self.series = SeriesOperations(self.connection_manager, self.author_overrides)
                    
                    # Initialize database and run migrations
                    self._initialize_service()
                    
                    DatabaseService._initialized = True

    def _normalize_db_file(self, db_file: Optional[str]) -> str:
        """Force all database operations to use the canonical filename."""
        target = db_file or DEFAULT_DB_PATH
        normalized = os.path.normpath(target)
        filename = os.path.basename(normalized)

        if filename != DEFAULT_DB_FILENAME:
            preferred_dir = os.path.dirname(DEFAULT_DB_PATH) or ""
            corrected_path = os.path.normpath(os.path.join(preferred_dir, DEFAULT_DB_FILENAME))
            self.logger.warning(
                "Ignoring custom database file '%s'; using '%s' instead", normalized, corrected_path
            )
            return corrected_path

        return normalized
    
    def _initialize_service(self):
        """Initialize database and perform necessary migrations."""
        try:
            self.migrations.initialize_database()
            self.migrations.migrate_database()
            self.logger.info(f"DatabaseService initialized successfully: {self.db_file}")
        except Exception as e:
            self.logger.error(f"Failed to initialize DatabaseService: {e}")
            raise
    
    # Connection methods
    def connect_db(self):
        """Connect to the database (delegates to connection manager)."""
        return self.connection_manager.connect_db()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        return self.connection_manager.test_connection()
    
    def get_database_info(self) -> dict:
        """Get database file information."""
        return self.connection_manager.get_database_info()
    
    # Book operation methods (delegate to books module)
    def check_book_exists(self, asin: str) -> bool:
        """Check if a book with the given ASIN exists."""
        return self.books.check_book_exists(asin)
    
    def add_book(self, book_data: Dict, status: str = "Wanted") -> bool:
        """Add a book to the database."""
        return self.books.add_book(book_data, status)
    
    def get_all_books(self) -> List[Dict]:
        """Get all books from the database."""
        return self.books.get_all_books()
    
    def get_book_by_id(self, book_id: int) -> Optional[Dict]:
        """Get a specific book by ID."""
        return self.books.get_book_by_id(book_id)
    
    def get_book_by_asin(self, asin: str) -> Optional[Dict]:
        """Get a specific book by ASIN."""
        return self.books.get_book_by_asin(asin)

    def get_recent_books(self, limit: int = 6) -> List[Dict]:
        """Get the most recently updated or added books."""
        return self.books.get_recent_books(limit)
    
    def update_book_status(self, book_id: int, new_status: str) -> bool:
        """Update a book's status."""
        return self.books.update_book_status(book_id, new_status)
    
    def delete_book(self, book_id: int) -> bool:
        """Delete a book from the database."""
        return self.books.delete_book(book_id)
    
    def search_books(self, query: str) -> List[Dict]:
        """Search books by title, author, or series."""
        return self.books.search_books(query)
    
    def get_books_by_status(self, status: str) -> List[Dict]:
        """Get all books with a specific status."""
        return self.books.get_books_by_status(status)
    
    # Author operation methods (delegate to authors module)
    def get_all_authors(self) -> List[str]:
        """Get all unique authors."""
        return self.authors.get_all_authors()
    
    def get_books_by_author(self, author: str) -> List[Dict]:
        """Get all books by a specific author."""
        return self.authors.get_books_by_author(author)
    
    def get_author_stats(self, author: str) -> Dict:
        """Get comprehensive statistics for a specific author."""
        return self.authors.get_author_stats(author)
    
    def search_authors(self, query: str) -> List[str]:
        """Search authors by name."""
        return self.authors.search_authors(query)
    
    def get_top_authors_by_book_count(self, limit: int = 10) -> List[Dict]:
        """Get top authors by number of books."""
        return self.authors.get_top_authors_by_book_count(limit)
    
    def get_authors_with_series(self) -> List[Dict]:
        """Get authors who have books in series."""
        return self.authors.get_authors_with_series()
    
    # Statistics methods (delegate to stats module)
    def get_library_stats(self) -> Dict:
        """Get comprehensive library statistics."""
        return self.stats.get_library_stats()
    
    def get_status_distribution(self) -> Dict[str, int]:
        """Get book count by status."""
        return self.stats.get_status_distribution()
    
    def get_language_distribution(self) -> Dict[str, int]:
        """Get book count by language."""
        return self.stats.get_language_distribution()
    
    def get_recent_activity_stats(self, days: int = 30) -> Dict:
        """Get recent activity statistics."""
        return self.stats.get_recent_activity_stats(days)
    
    def get_series_completion_stats(self) -> Dict:
        """Get statistics about series completion."""
        return self.stats.get_series_completion_stats()
    
    # Migration and maintenance methods
    def initialize_database(self):
        """Initialize the database (delegates to migrations)."""
        return self.migrations.initialize_database()
    
    def migrate_database(self):
        """Perform database migrations (delegates to migrations)."""
        return self.migrations.migrate_database()
    
    def get_schema_version(self) -> dict:
        """Get current database schema information."""
        return self.migrations.get_schema_version()
    
    def verify_schema_integrity(self) -> bool:
        """Verify database schema integrity."""
        return self.migrations.verify_schema_integrity()
    
    # Utility methods
    def get_service_status(self) -> Dict:
        """Get comprehensive service status."""
        try:
            db_info = self.get_database_info()
            connection_test = self.test_connection()
            schema_info = self.get_schema_version()
            recent_stats = self.get_recent_activity_stats(7)  # Last 7 days
            
            status = {
                'service_name': 'DatabaseService',
                'initialized': self._initialized,
                'database_file': self.db_file,
                'connection_test': connection_test,
                'database_info': db_info,
                'schema_info': schema_info,
                'recent_activity': recent_stats,
                'components': {
                    'connection_manager': bool(self.connection_manager),
                    'migrations': bool(self.migrations),
                    'books': bool(self.books),
                    'authors': bool(self.authors),
                    'stats': bool(self.stats)
                }
            }
            
            return status
        
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {'error': str(e)}
    
    def reset_service(self):
        """Reset the service (for testing or troubleshooting)."""
        with self._lock:
            self.__class__._initialized = False
            self.__class__._instance = None
            self.logger.info("DatabaseService reset")
