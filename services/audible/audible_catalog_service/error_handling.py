"""
Module Name: error_handling.py
Author: TheDragonShaman
Created: August 18, 2025
Last Modified: December 23, 2025
Description:
    Retry, rate-limit, and response validation helpers for Audible catalog requests.
Location:
    /services/audible/audible_catalog_service/error_handling.py

"""

import time
from functools import wraps
from typing import Any, Callable, Optional

import requests

from utils.logger import get_module_logger

class AudibleErrorHandler:
    """Handles API errors, retries, and rate limiting for Audible service"""
    
    def __init__(self):
        self.logger = get_module_logger("Service.Audible.CatalogErrorHandling")
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
                                self.logger.warning("Rate limited; retrying", extra={"delay": delay, "attempt": attempt + 1})
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error("Rate limit exceeded after retries")
                                raise
                        elif e.response.status_code >= 500:  # Server error
                            if attempt < max_retries - 1:
                                delay = retry_delay * (attempt + 1)
                                self.logger.warning(
                                    "Server error; retrying",
                                    extra={"status_code": e.response.status_code, "delay": delay, "attempt": attempt + 1}
                                )
                                time.sleep(delay)
                                continue
                            else:
                                self.logger.error("Server error persisted after retries", extra={"status_code": e.response.status_code, "attempts": max_retries})
                                raise
                        else:
                            self.logger.error("HTTP error", extra={"status_code": e.response.status_code, "error": str(e)})
                            raise
                    
                    except requests.exceptions.ConnectionError as e:
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning("Connection error; retrying", extra={"delay": delay, "attempt": attempt + 1})
                            time.sleep(delay)
                            continue
                        else:
                            self.logger.error("Connection error persisted after retries", extra={"attempts": max_retries, "error": str(e)})
                            raise
                    
                    except requests.exceptions.Timeout as e:
                        if attempt < max_retries - 1:
                            delay = retry_delay * (attempt + 1)
                            self.logger.warning("Request timeout; retrying", extra={"delay": delay, "attempt": attempt + 1})
                            time.sleep(delay)
                            continue
                        else:
                            self.logger.error("Request timeout persisted after retries", extra={"attempts": max_retries, "error": str(e)})
                            raise
                    
                    except requests.exceptions.RequestException as e:
                        self.logger.error("Request error", extra={"error": str(e)})
                        raise
                    
                    except Exception as e:
                        self.logger.exception("Unexpected error during API request", extra={"error": str(e)})
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
            self.logger.debug("Rate limiting applied", extra={"sleep_seconds": round(sleep_time, 2)})
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
                        self.logger.debug("Operation successful", extra={"operation": operation, "product_count": product_count})
                        return True
                    else:
                        self.logger.warning("Unexpected data format", extra={"operation": operation})
                        return False
                except ValueError as e:
                    self.logger.error("Invalid JSON response", extra={"operation": operation, "error": str(e)})
                    return False
            else:
                self.logger.error("Operation failed", extra={"operation": operation, "status_code": response.status_code, "reason": response.reason})
                response.raise_for_status()
                return False
        
        except Exception as e:
            self.logger.exception("Error validating response", extra={"operation": operation, "error": str(e)})
            return False
    
    def log_request_info(self, url: str, params: dict, operation: str):
        """Log request information for debugging"""
        # Sanitize sensitive information
        safe_params = {k: v for k, v in params.items() if k not in ['api_key', 'token']}
        self.logger.debug("Request info", extra={"operation": operation, "url": url, "params": safe_params})
    
    def handle_api_quota(self, response: requests.Response) -> Optional[int]:
        """Handle API quota information from response headers"""
        try:
            # Check for common rate limit headers
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining is not None:
                remaining_requests = int(remaining)
                if remaining_requests < 10:
                    self.logger.warning("API quota low", extra={"remaining": remaining_requests})
                
                if reset_time:
                    self.logger.debug("Rate limit reset time", extra={"reset_time": reset_time})
                
                return remaining_requests
            
            return None
        
        except Exception as e:
            self.logger.debug("Could not parse rate limit headers", extra={"error": str(e)})
            return None

# Global instance for easy access
error_handler = AudibleErrorHandler()
