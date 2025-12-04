import requests
import logging
import time
from functools import wraps
from typing import Callable, Any, Optional, Any

class AudibleErrorHandler:
    """Handles API errors, retries, and rate limiting for Audible service"""
    
    def __init__(self):
        self.logger = logging.getLogger("AudibleService.ErrorHandling")
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Minimum seconds between requests
    
    def with_retry(self, max_retries: int = 3, retry_delay: float = 1.0):
        """Decorator for API requests with retry logic"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                for attempt in range(max_retries):
                    try:
                        # Apply rate limiting
                        self._apply_rate_limit()
                        
                        return func(*args, **kwargs)
                    
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 429:  # Rate limited
                            if attempt < max_retries - 1:
                                delay = retry_delay * (2 ** attempt)  # Exponential backoff
                                self.logger.warning(f"Rate limited, retrying in {delay}s... (attempt {attempt + 1})")
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error("Rate limit exceeded after all retries")
                                raise
                        elif e.response.status_code >= 500:  # Server error
                            if attempt < max_retries - 1:
                                delay = retry_delay * (attempt + 1)
                                self.logger.warning(f"Server error {e.response.status_code}, retrying in {delay}s...")
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error(f"Server error persisted after {max_retries} attempts")
                                raise
                        else:
                            self.logger.error(f"HTTP error {e.response.status_code}: {e}")
                            raise
                    
                    except requests.exceptions.ConnectionError as e:
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning(f"Connection error, retrying in {delay}s... (attempt {attempt + 1})")
                            time.sleep(delay)
                            continue
                        else:
                            self.logger.error("Connection error persisted after all retries")
                            raise
                    
                    except requests.exceptions.Timeout as e:
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning(f"Request timeout, retrying in {delay}s... (attempt {attempt + 1})")
                            time.sleep(delay)
                            continue
                        else:
                            self.logger.error("Request timeout persisted after all retries")
                            raise
                    
                    except requests.exceptions.RequestException as e:
                        self.logger.error(f"Request error: {e}")
                        raise
                    
                    except Exception as e:
                        self.logger.error(f"Unexpected error during API request: {e}")
                        raise
                
                return None
            return wrapper
        return decorator
    
    def _apply_rate_limit(self):
        """Apply rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def validate_response(self, response: requests.Response, operation: str) -> bool:
        """Validate API response and log appropriately"""
        try:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'products' in data:
                        product_count = len(data.get('products', []))
                        self.logger.debug(f"{operation} successful: {product_count} products returned")
                        return True
                    else:
                        self.logger.warning(f"{operation} returned unexpected data format")
                        return False
                except ValueError as e:
                    self.logger.error(f"{operation} returned invalid JSON: {e}")
                    return False
            else:
                self.logger.error(f"{operation} failed: HTTP {response.status_code} - {response.reason}")
                response.raise_for_status()
                return False
        
        except Exception as e:
            self.logger.error(f"Error validating response for {operation}: {e}")
            return False
    
    def log_request_info(self, url: str, params: dict, operation: str):
        """Log request information for debugging"""
        # Sanitize sensitive information
        safe_params = {k: v for k, v in params.items() if k not in ['api_key', 'token']}
        self.logger.debug(f"{operation} request: {url} with params: {safe_params}")
    
    def handle_api_quota(self, response: requests.Response) -> Optional[int]:
        """Handle API quota information from response headers"""
        try:
            # Check for common rate limit headers
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining is not None:
                remaining_requests = int(remaining)
                if remaining_requests < 10:
                    self.logger.warning(f"API quota low: {remaining_requests} requests remaining")
                
                if reset_time:
                    self.logger.debug(f"Rate limit resets at: {reset_time}")
                
                return remaining_requests
            
            return None
        
        except Exception as e:
            self.logger.debug(f"Could not parse rate limit headers: {e}")
            return None

# Global instance for easy access
error_handler = AudibleErrorHandler()
