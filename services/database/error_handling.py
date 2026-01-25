"""
Module Name: error_handling.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Retry and cleanup helpers for database operations.

Location:
    /services/database/error_handling.py

"""

import sqlite3
import time
from functools import wraps
from typing import Callable, Any
from utils.logger import get_module_logger


class DatabaseErrorHandler:
    """Shared error handling and retry logic for database operations."""

    def __init__(self, *, logger=None):
        self.logger = logger or get_module_logger("Service.Database.ErrorHandling")
    
    def with_retry(self, max_retries: int = 3, retry_delay: float = 0.5):
        """Decorator for database operations with retry logic for locks"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    
                    except sqlite3.OperationalError as e:
                        if "database is locked" in str(e):
                            if attempt < max_retries - 1:
                                delay = retry_delay * (attempt + 1)  # Exponential backoff
                                self.logger.warning(
                                    "Database locked, retrying",
                                    extra={"delay_seconds": delay, "attempt": attempt + 1},
                                )
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error(
                                    "Database remained locked after retries",
                                    extra={"retries": max_retries},
                                )
                                raise
                        else:
                            self.logger.error(
                                "Database operational error",
                                extra={"error": str(e)},
                            )
                            raise
                    
                    except sqlite3.IntegrityError as e:
                        if "UNIQUE constraint failed" in str(e):
                            self.logger.warning(
                                "Duplicate entry detected",
                                extra={"error": str(e)},
                            )
                            return False  # Return False for duplicate entries
                        else:
                            self.logger.error(
                                "Database integrity error",
                                extra={"error": str(e)},
                            )
                            raise
                    
                    except Exception as e:
                        self.logger.error(
                            "Unexpected database error",
                            extra={"error": str(e)},
                        )
                        raise
                
                return None
            return wrapper
        return decorator
    
    def handle_connection_cleanup(self, conn=None):
        """Safely close database connection"""
        if conn:
            try:
                conn.close()
            except Exception as e:
                self.logger.warning(
                    "Error closing database connection",
                    extra={"error": str(e)},
                )
    
    def log_operation(self, operation: str, details: str = ""):
        """Log database operations consistently"""
        if details:
            self.logger.info(operation, extra={"details": details})
        else:
            self.logger.info(operation)
    
    def validate_required_fields(self, data: dict, required_fields: list) -> bool:
        """Validate that required fields are present in data"""
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            self.logger.error(
                "Missing required fields",
                extra={"fields": missing_fields},
            )
            return False
        return True

# Global instance for easy access
error_handler = DatabaseErrorHandler()
