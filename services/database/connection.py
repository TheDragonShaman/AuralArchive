"""
Module Name: connection.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Manages SQLite connections and applies performance pragmas.

Location:
    /services/database/connection.py

"""

import sqlite3
from typing import Tuple
from utils.logger import get_module_logger


class DatabaseConnection:
    """Handles database connection management and optimization."""

    def __init__(self, db_file: str, *, logger=None):
        self.db_file = db_file
        self.logger = logger or get_module_logger("Service.Database.Connection")
    
    def connect_db(self) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
        """Connect to the SQLite database with optimized settings for concurrent access."""
        try:
            conn = sqlite3.connect(self.db_file, timeout=30.0)
            conn.row_factory = sqlite3.Row  # allow dict-style access to columns
            cursor = conn.cursor()
            
            # Optimize for concurrent access
            self._apply_optimizations(cursor)
            
            self.logger.debug(
                "Database connection established",
                extra={"database_file": self.db_file},
            )
            return conn, cursor
        
        except Exception as exc:
            self.logger.exception(
                "Failed to connect to database",
                extra={"database_file": self.db_file},
            )
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
                self.logger.debug(
                    "Applied database optimization",
                    extra={"pragma": pragma, "description": description, "database_file": self.db_file},
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to apply database optimization",
                    extra={"pragma": pragma, "database_file": self.db_file, "error": str(exc)},
                )
    
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
        
        except Exception as exc:
            self.logger.exception(
                "Database connection test failed",
                extra={"database_file": self.db_file},
            )
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
        
        except Exception as exc:
            self.logger.exception(
                "Error getting database info",
                extra={"database_file": self.db_file},
            )
            return {'error': str(exc)}
