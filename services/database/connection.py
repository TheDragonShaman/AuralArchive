import sqlite3
import logging
from typing import Tuple

class DatabaseConnection:
    """Handles database connection management and optimization"""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.logger = logging.getLogger("DatabaseService.Connection")
    
    def connect_db(self) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
        """Connect to the SQLite database with optimized settings for concurrent access."""
        try:
            conn = sqlite3.connect(self.db_file, timeout=30.0)
            conn.row_factory = sqlite3.Row  # allow dict-style access to columns
            cursor = conn.cursor()
            
            # Optimize for concurrent access
            self._apply_optimizations(cursor)
            
            self.logger.debug(f"Database connection established: {self.db_file}")
            return conn, cursor
        
        except Exception as e:
            self.logger.error(f"Failed to connect to database {self.db_file}: {e}")
            raise
    
    def _apply_optimizations(self, cursor: sqlite3.Cursor):
        """Apply SQLite optimization settings for better performance"""
        optimizations = [
            ("PRAGMA journal_mode=WAL", "Write-Ahead Logging"),
            ("PRAGMA synchronous=NORMAL", "Faster than FULL, safer than OFF"),
            ("PRAGMA cache_size=10000", "Larger cache"),
            ("PRAGMA temp_store=memory", "Store temp tables in memory"),
            ("PRAGMA busy_timeout=30000", "30 second timeout for locks")
        ]
        
        for pragma, description in optimizations:
            try:
                cursor.execute(pragma)
                self.logger.debug(f"Applied optimization: {pragma} ({description})")
            except Exception as e:
                self.logger.warning(f"Failed to apply optimization {pragma}: {e}")
    
    def test_connection(self) -> bool:
        """Test database connection and return success status"""
        try:
            conn, cursor = self.connect_db()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()
            
            success = result is not None
            if success:
                self.logger.info("Database connection test successful")
            else:
                self.logger.error("Database connection test failed - no result")
            
            return success
        
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_database_info(self) -> dict:
        """Get database file information"""
        try:
            import os
            if os.path.exists(self.db_file):
                size_bytes = os.path.getsize(self.db_file)
                size_mb = round(size_bytes / (1024 * 1024), 2)
                
                return {
                    'file_path': self.db_file,
                    'size_bytes': size_bytes,
                    'size_mb': size_mb,
                    'exists': True
                }
            else:
                return {
                    'file_path': self.db_file,
                    'exists': False
                }
        
        except Exception as e:
            self.logger.error(f"Error getting database info: {e}")
            return {'error': str(e)}
