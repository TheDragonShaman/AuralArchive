import logging
import time
from functools import wraps
from typing import Callable, Any, Tuple

class MetadataErrorHandler:
    """Handles errors and retry logic for metadata update operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("MetadataUpdateService.ErrorHandling")
    
    def with_retry(self, max_retries: int = 2, retry_delay: float = 1.0):
        """Decorator for metadata operations with retry logic"""
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
                            self.logger.error(f"Permanent error in {func.__name__}: {e}")
                            return False, f"Permanent error: {str(e)}"
                        
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning(f"Retrying {func.__name__} in {delay}s due to: {e}")
                            time.sleep(delay)
                        else:
                            self.logger.error(f"Final retry failed for {func.__name__}: {e}")
                
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
            self.logger.error(f"Error validating book data: {e}")
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
            self.logger.error(f"Error validating search results: {e}")
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
                    value = value[:max_length-3] + "..."
                    self.logger.warning(f"Truncated {field} field (was {len(metadata.get(field, ''))} chars)")
                
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
            self.logger.error(f"Error sanitizing metadata: {e}")
            # Return original metadata if sanitization fails
            return metadata
    
    def log_update_attempt(self, book_id: int, operation: str, details: str = ""):
        """Log metadata update attempts for debugging"""
        if details:
            self.logger.info(f"Book {book_id} - {operation}: {details}")
        else:
            self.logger.info(f"Book {book_id} - {operation}")
    
    def log_update_result(self, book_id: int, success: bool, message: str):
        """Log the result of metadata update operations"""
        if success:
            self.logger.info(f"Book {book_id} update successful: {message}")
        else:
            self.logger.warning(f"Book {book_id} update failed: {message}")

# Global instance for easy access
error_handler = MetadataErrorHandler()
