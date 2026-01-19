"""
Module Name: error_handling.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Error handling utilities for metadata updates, including retry helpers
    and validation/sanitization routines.

Location:
    /services/metadata/error_handling.py

"""

import time
from functools import wraps
from typing import Callable, Any, Tuple

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Metadata.ErrorHandling")

class MetadataErrorHandler:
    """Handles errors and retry logic for metadata update operations"""
    
    def __init__(self, *, logger=None):
        self.logger = logger or _LOGGER
    
    def with_retry(self, max_retries: int = 2, retry_delay: float = 1.0):
        """Decorator for metadata operations with retry logic."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Tuple[bool, str]:
                last_error = None
                
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    
                    except Exception as e:
                        last_error = e
                        
                        # Don't retry certain types of errors
                        if self._is_permanent_error(e):
                            self.logger.error(
                                "Permanent error in operation",
                                extra={"operation": func.__name__, "error": str(e)},
                                exc_info=True,
                            )
                            return False, f"Permanent error: {str(e)}"
                        
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning(
                                "Retrying operation",
                                extra={
                                    "operation": func.__name__,
                                    "delay_seconds": delay,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "error": str(e),
                                },
                            )
                            time.sleep(delay)
                        else:
                            self.logger.error(
                                "Final retry failed",
                                extra={"operation": func.__name__, "error": str(e), "attempt": attempt + 1},
                                exc_info=True,
                            )
                
                return False, f"Failed after {max_retries} attempts: {str(last_error)}"
            
            return wrapper
        return decorator
    
    def _is_permanent_error(self, error: Exception) -> bool:
        """Determine if an error is permanent and shouldn't be retried"""
        error_str = str(error).lower()
        
        # Permanent error conditions
        permanent_indicators = [
            "book not found",
            "invalid asin",
            "no book found with id",
            "required fields missing",
            "invalid book data"
        ]
        
        return any(indicator in error_str for indicator in permanent_indicators)
    
    def validate_book_data(self, book_data: dict) -> Tuple[bool, str]:
        """Validate book data before processing"""
        try:
            # Check required fields
            required_fields = ['Title']
            missing_fields = [field for field in required_fields if not book_data.get(field)]
            
            if missing_fields:
                return False, f"Missing required fields: {missing_fields}"
            
            # Validate ASIN if present
            asin = book_data.get('ASIN', '')
            if asin and asin != 'N/A':
                if not self._is_valid_asin(asin):
                    return False, f"Invalid ASIN format: {asin}"
            
            # Validate title length
            title = book_data.get('Title', '')
            if len(title) > 500:
                return False, "Title too long (max 500 characters)"
            
            return True, "Validation passed"
        
        except Exception as e:
            self.logger.error(
                "Error validating book data",
                extra={"error": str(e)},
                exc_info=True,
            )
            return False, f"Validation error: {str(e)}"
    
    def _is_valid_asin(self, asin: str) -> bool:
        """Basic ASIN format validation"""
        if not asin or len(asin) != 10:
            return False
        
        # ASIN should be alphanumeric
        return asin.isalnum()
    
    def validate_search_results(self, results: list) -> Tuple[bool, str]:
        """Validate search results before processing"""
        try:
            if not isinstance(results, list):
                return False, "Search results must be a list"
            
            if len(results) == 0:
                return True, "No results found (valid empty response)"
            
            # Check if results have required structure
            for i, result in enumerate(results):
                if not isinstance(result, dict):
                    return False, f"Result {i} is not a dictionary"
                
                # Check for essential fields
                if not result.get('Title') and not result.get('title'):
                    return False, f"Result {i} missing title field"
            
            return True, f"Validated {len(results)} search results"
        
        except Exception as e:
            self.logger.error(
                "Error validating search results",
                extra={"error": str(e)},
                exc_info=True,
            )
            return False, f"Search results validation error: {str(e)}"
    
    def sanitize_metadata(self, metadata: dict) -> dict:
        """Sanitize metadata to prevent issues during database updates"""
        try:
            sanitized = {}
            
            # Field mappings and sanitization rules
            field_rules = {
                'Title': {'max_length': 500, 'required': True},
                'Author': {'max_length': 300, 'default': 'Unknown Author'},
                'Series': {'max_length': 200, 'default': 'N/A'},
                'Sequence': {'max_length': 50, 'default': 'N/A'},
                'Narrator': {'max_length': 300, 'default': 'Unknown Narrator'},
                'Runtime': {'max_length': 50, 'default': 'Unknown Runtime'},
                'Release Date': {'max_length': 50, 'default': 'Unknown'},
                'Language': {'max_length': 50, 'default': 'Unknown'},
                'Publisher': {'max_length': 200, 'default': 'Unknown Publisher'},
                'Overall Rating': {'max_length': 10, 'default': 'N/A'},
                'ASIN': {'max_length': 15, 'default': ''},
                'Summary': {'max_length': 5000, 'default': 'No summary available'},
                'Cover Image': {'max_length': 500, 'default': ''},
                'num_ratings': {'max_length': 10, 'default': 0},  # Add num_ratings field
                'series_asin': {'max_length': 20, 'default': ''}  # Preserve series_asin for DB update
            }
            
            for field, rules in field_rules.items():
                value = metadata.get(field, rules.get('default', ''))
                
                # Convert to string
                if value is None:
                    value = rules.get('default', '')
                else:
                    value = str(value)
                
                # Truncate if too long
                max_length = rules.get('max_length', 1000)
                if len(value) > max_length:
                    original_length = len(metadata.get(field, ''))
                    value = value[:max_length-3] + "..."
                    self.logger.warning(
                        "Truncated field during sanitization",
                        extra={"field": field, "original_length": original_length, "max_length": max_length},
                    )
                
                # Strip whitespace
                value = value.strip()
                
                # Apply default for empty required fields
                if rules.get('required') and not value:
                    value = rules.get('default', 'Unknown')
                
                sanitized[field] = value

            # Ensure we don't accidentally drop series_asin even if rules change above
            if 'series_asin' in metadata and 'series_asin' not in sanitized:
                try:
                    series_asin_val = str(metadata.get('series_asin', '')).strip()
                    sanitized['series_asin'] = series_asin_val
                except Exception:
                    pass
            
            return sanitized
        
        except Exception as e:
            self.logger.error(
                "Error sanitizing metadata",
                extra={"error": str(e)},
                exc_info=True,
            )
            # Return original metadata if sanitization fails
            return metadata
    
    def log_update_attempt(self, book_id: int, operation: str, details: str = ""):
        """Log metadata update attempts for debugging"""
        payload = {"book_id": book_id, "operation": operation}
        if details:
            payload["details"] = details
        self.logger.info("Metadata update attempt", extra=payload)
    
    def log_update_result(self, book_id: int, success: bool, message: str):
        """Log the result of metadata update operations"""
        if success:
            self.logger.info(
                "Metadata update successful",
                extra={"book_id": book_id, "result_message": message},
            )
        else:
            self.logger.warning(
                "Metadata update failed",
                extra={"book_id": book_id, "result_message": message},
            )

# Global instance for easy access
error_handler = MetadataErrorHandler()
