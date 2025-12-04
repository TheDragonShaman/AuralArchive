import sqlite3
import logging
import time
from functools import wraps
from typing import Callable, Any

class DatabaseErrorHandler:
    """Shared error handling and retry logic for database operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("DatabaseService.ErrorHandling")
    
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
                                self.logger.warning(f"Database locked, retrying in {delay}s... (attempt {attempt + 1})")
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error(f"Database remained locked after {max_retries} attempts")
                                raise
                        else:
                            self.logger.error(f"Database operational error: {e}")
                            raise
                    
                    except sqlite3.IntegrityError as e:
                        if "UNIQUE constraint failed" in str(e):
                            self.logger.warning(f"Duplicate entry detected: {e}")
                            return False  # Return False for duplicate entries
                        else:
                            self.logger.error(f"Database integrity error: {e}")
                            raise
                    
                    except Exception as e:
                        self.logger.error(f"Unexpected database error: {e}")
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
                self.logger.warning(f"Error closing database connection: {e}")
    
    def log_operation(self, operation: str, details: str = ""):
        """Log database operations consistently"""
        if details:
            self.logger.info(f"{operation}: {details}")
        else:
            self.logger.info(operation)
    
    def validate_required_fields(self, data: dict, required_fields: list) -> bool:
        """Validate that required fields are present in data"""
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            self.logger.error(f"Missing required fields: {missing_fields}")
            return False
        return True

# Global instance for easy access
error_handler = DatabaseErrorHandler()
