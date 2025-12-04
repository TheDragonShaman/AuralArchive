"""
Audible Manager Service
======================

Shared service for managing Audible authentication, API connections, and common utilities.
Coordinates all Audible services including library, recommendations, wishlist, and catalog services.

Services managed:
- audible_library_service: Direct library access via Python audible package
- audible_recommendations_service: Book recommendations
- audible_wishlist_service: Wishlist management
- audible_catalog_service: Catalog browsing
"""

import audible
import logging
import os
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
import time

from utils.logger import get_module_logger

# Import the new library service
from .audible_library_service.audible_library_service import AudibleLibraryService
from .audible_series_service.audible_series_service import AudibleSeriesService

logger = get_module_logger("AudibleServiceManager")

class AudibleServiceManager:
    """Shared manager for Audible authentication, API utilities, and service coordination."""
    
    def __init__(self, auth_file: str = None, config_service=None):
        """
        Initialize the Audible manager with all sub-services.
        
        Args:
            auth_file: Path to authentication file (optional)
            config_service: Configuration service instance
        """
        self.config_service = config_service
        self.auth_file = auth_file or "auth/audible_auth.json"
        self.auth = None
        self._lock = threading.Lock()
        
        # Initialize sub-services
        self.library_service = AudibleLibraryService(config_service, logger)
        self.series_service = AudibleSeriesService()
        
        # Try to load existing auth on initialization
        self._load_existing_auth()
        
    logger.debug("AudibleServiceManager initialized with library and series services")
        
    def _load_existing_auth(self) -> bool:
        """Try to load existing authentication from file."""
        try:
            if os.path.exists(self.auth_file):
                logger.debug(f"Loading existing Audible authentication from {self.auth_file}")
                self.auth = audible.Authenticator.from_file(self.auth_file)
                return True
        except Exception as e:
            logger.warning(f"Failed to load existing auth: {e}")
        return False
    
    def is_configured(self) -> bool:
        """Check if Audible is properly configured (has auth token)."""
        try:
            # Only check if auth token file exists
            return os.path.exists(self.auth_file)
        except Exception as e:
            logger.error(f"Error checking Audible configuration: {e}")
            return False
    
    def authenticate(self) -> Tuple[bool, str]:
        """
        DEPRECATED: This method no longer performs authentication.
        Use the modal-based authentication in the web UI instead.
        
        This method now only checks if an auth token exists.
        
        Returns:
            Tuple of (success, message)
        """
        with self._lock:
            try:
                # Try to load existing authentication token only
                if self.auth is None and os.path.exists(self.auth_file):
                    try:
                        logger.debug("Loading existing Audible authentication token")
                        self.auth = audible.Authenticator.from_file(self.auth_file)
                        return True, "Successfully loaded existing authentication"
                    except Exception as e:
                        logger.warning(f"Failed to load existing auth token: {e}")
                        return False, "Failed to load authentication token"
                
                # If we already have valid auth, return success
                if self.auth:
                    return True, "Authentication already loaded"
                
                # No auth available - user needs to authenticate via web UI
                logger.info("No authentication token found - user must authenticate via web UI")
                return False, "No authentication token found. Please authenticate using the Settings > Audible page."
                
            except Exception as e:
                error_msg = f"Error checking authentication: {e}"
                logger.error(error_msg)
                return False, error_msg
    
    def submit_otp(self, otp_code: str) -> Tuple[bool, str]:
        """
        DEPRECATED: OTP submission now handled by the web UI authentication API.
        
        Args:
            otp_code: The OTP code from user's authenticator app/SMS
            
        Returns:
            Tuple of (success, message)
        """
        return False, "OTP submission is now handled via the web UI. Please use Settings > Audible to authenticate."
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the Audible connection."""
        try:
            if not self.auth:
                success, message = self.authenticate()
                if not success:
                    return False, f"Authentication failed: {message}"
            
            # Try a simple API call
            with audible.Client(auth=self.auth) as client:
                account_info = client.get("1.0/account/information")
                
            return True, "Connection successful"
            
        except Exception as e:
            error_msg = f"Connection test failed: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_client(self) -> Optional[audible.Client]:
        """Get an authenticated Audible client."""
        try:
            if not self.auth:
                success, message = self.authenticate()
                if not success:
                    logger.error(f"Cannot create client: {message}")
                    return None
            
            return audible.Client(auth=self.auth)
            
        except Exception as e:
            logger.error(f"Error creating Audible client: {e}")
            return None
    
    def make_api_call(self, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Make an API call to Audible with error handling.
        
        Args:
            endpoint: API endpoint to call
            **kwargs: Additional parameters for the API call
            
        Returns:
            API response or None if failed
        """
        try:
            with self.get_client() as client:
                if client is None:
                    return None
                
                logger.debug(f"Making API call to: {endpoint}")
                response = client.get(endpoint, **kwargs)
                return response
                
        except Exception as e:
            logger.error(f"API call to {endpoint} failed: {e}")
            return None
    
    def try_multiple_endpoints(self, endpoints: List[str], **kwargs) -> Optional[Dict[str, Any]]:
        """
        Try multiple API endpoints until one succeeds.
        
        Args:
            endpoints: List of endpoint URLs to try
            **kwargs: Additional parameters for the API calls
            
        Returns:
            First successful response or None if all failed
        """
        for endpoint in endpoints:
            try:
                logger.debug(f"Trying endpoint: {endpoint}")
                response = self.make_api_call(endpoint, **kwargs)
                
                if response and isinstance(response, dict):
                    # Check if response has meaningful data
                    has_data = any(key in response for key in ['products', 'items', 'books', 'collections', 'lists'])
                    if has_data:
                        logger.debug(f"Successful response from endpoint: {endpoint}")
                        return response
                    
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} failed: {e}")
                continue
        
        logger.warning(f"All endpoints failed: {endpoints}")
        return None
    
    def format_book_data(self, book: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format book data for consistent use across the application.
        Centralized formatting logic used by both recommendations and wishlist services.
        """
        # Extract authors
        authors = []
        
        # Try 'authors' field first
        authors_data = book.get("authors") or []
        if authors_data and isinstance(authors_data, list):
            authors = [author.get("name", "Unknown") for author in authors_data 
                      if author and isinstance(author, dict)]
        
        # Try 'contributors' field if no authors
        if not authors:
            contributors_data = book.get("contributors") or []
            if contributors_data and isinstance(contributors_data, list):
                author_contributors = [c for c in contributors_data 
                                     if c and isinstance(c, dict) and c.get("role") == "Author"]
                if author_contributors:
                    authors = [contrib.get("name", "Unknown") for contrib in author_contributors]
                else:
                    authors = [contrib.get("name", "Unknown") for contrib in contributors_data
                             if contrib and isinstance(contrib, dict)]
        
        if not authors:
            authors = ["Unknown Author"]
        
        # Extract narrators
        narrators = []
        contributors_data = book.get("contributors") or []
        if contributors_data and isinstance(contributors_data, list):
            narrator_contributors = [c for c in contributors_data 
                                   if c and isinstance(c, dict) and c.get("role") == "Narrator"]
            narrators = [contrib.get("name", "Unknown") for contrib in narrator_contributors]
        
        if not narrators:
            narrators_data = book.get("narrators") or []
            if narrators_data and isinstance(narrators_data, list):
                narrators = [narrator.get("name", "Unknown") for narrator in narrators_data 
                           if narrator and isinstance(narrator, dict)]
        
        if not narrators:
            narrators = ["Unknown Narrator"]
        
        # Extract other fields
        rating_info = book.get("rating") or {}  # Changed from "overall_rating" to "rating"
        runtime_min = book.get("runtime_length_min")
        
        # Handle None runtime_length_min safely
        runtime_display = "Unknown"
        if runtime_min is not None and runtime_min > 0:
            hours = runtime_min // 60
            minutes = runtime_min % 60
            if hours > 0:
                runtime_display = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            else:
                runtime_display = f"{minutes}m"
        
        # Extract series information
        series_info = book.get("series", [])
        series_name = "N/A"
        series_sequence = ""
        
        if series_info and isinstance(series_info, list) and len(series_info) > 0:
            first_series = series_info[0]
            if isinstance(first_series, dict):
                series_name = first_series.get("title", "N/A")
                series_sequence = str(first_series.get("sequence", ""))
        
        # Map language code to full name
        language_map = {
            "en": "English",
            "es": "Spanish", 
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ja": "Japanese",
            "zh": "Chinese"
        }
        language_code = book.get("language", "en")
        language_full = language_map.get(language_code, "English")
        
        # Use only publisher_summary
        full_summary = book.get("publisher_summary", "") or "No summary available"
        
        return {
            # Keep lowercase for backwards compatibility
            'asin': book.get("asin", ""),
            'title': book.get("title", "Unknown Title"),
            'authors': authors,
            'author': ", ".join(authors),  # For compatibility
            'narrators': narrators,
            'narrator': ", ".join(narrators),  # For compatibility
            'rating': rating_info.get("displayed_average_rating", "") or rating_info.get("overall_distribution", {}).get("display_average_rating", ""),
            'num_ratings': rating_info.get("overall_distribution", {}).get("num_ratings", 0),
            'runtime_minutes': runtime_min,
            'runtime': runtime_display,
            'release_date': book.get("release_date", ""),
            'publisher': book.get("publisher_name", ""),
            'summary': full_summary,
            'cover_image': self._extract_cover_image(book),
            'price_display': self._extract_price(book),
            'categories': book.get("category_ladders", []),
            'language': language_full,
            'series': series_name,
            'sequence': series_sequence,
            
            # ALSO include uppercase versions for database compatibility
            'ASIN': book.get("asin", ""),
            'Title': book.get("title", "Unknown Title"),
            'Author': ", ".join(authors),
            'Narrator': ", ".join(narrators),
            'Overall Rating': rating_info.get("displayed_average_rating", "") or rating_info.get("overall_distribution", {}).get("display_average_rating", ""),
            'Runtime': runtime_display,
            'Release Date': book.get("release_date", ""),
            'Publisher': book.get("publisher_name", ""),
            'Summary': full_summary,
            'Cover Image': self._extract_cover_image(book),
            'Language': language_full,
            'Series': series_name,
            'Sequence': series_sequence,
            'Num_Ratings': rating_info.get("overall_distribution", {}).get("num_ratings", 0)  # Add num_ratings uppercase version
        }
    
    def _extract_cover_image(self, book: Dict[str, Any]) -> str:
        """Extract cover image URL from book data."""
        try:
            product_images = book.get("product_images", {})
            
            # Try different image sizes
            for size in ["500", "300", "150", "90"]:
                if size in product_images:
                    return product_images[size]
            
            # Fallback to any available image
            if product_images:
                return next(iter(product_images.values()))
                
            return ""
            
        except Exception:
            return ""
    
    def _extract_price(self, book: Dict[str, Any]) -> str:
        """Extract price information from book data."""
        try:
            price_info = book.get("price", {})
            list_price_info = price_info.get("list_price", {})
            return list_price_info.get("display_price", "")
        except Exception:
            return ""
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current manager status information."""
        try:
            is_configured = self.is_configured()
            connection_ok = False
            
            if is_configured:
                connection_ok, _ = self.test_connection()
            
            # Get library service status
            library_status = self.library_service.get_service_status()
            
            return {
                'configured': is_configured,
                'connected': connection_ok,
                'auth_file_exists': os.path.exists(self.auth_file),
                'auth_loaded': self.auth is not None,
                'services': {
                    'library_service': library_status
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting manager status: {e}")
            return {
                'configured': False,
                'connected': False,
                'error': str(e),
                'services': {}
            }
    
    # Library Service Methods
    def export_library(self, output_format='json', force_refresh=False) -> Dict[str, Any]:
        """Export user's Audible library via library service."""
        return self.library_service.export_library(output_format, force_refresh)
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get library statistics via library service."""
        return self.library_service.get_library_stats()
    
    def search_library(self, query: str, search_fields: List[str] = None) -> Dict[str, Any]:
        """Search within library via library service."""
        return self.library_service.search_library(query, search_fields)
    
    def refresh_library_cache(self) -> Dict[str, Any]:
        """Refresh library cache via library service."""
        return self.library_service.refresh_library_cache()
    
    def test_audible_cli_availability(self) -> Dict[str, Any]:
        """Test Python audible package availability via library service."""
        return self.library_service.test_audible_cli_availability()
    
    def check_authentication_status(self) -> Dict[str, Any]:
        """Check authentication status via library service."""
        return self.library_service.check_authentication_status()
    
    # Series Service Methods
    def initialize_series_service(self, db_service):
        """Initialize series service with dependencies."""
        if self.auth:
            client = self.get_client()
            if client:
                self.series_service.initialize(client, db_service)
                logger.debug("Series service initialized with Audible client and database service")
                return True
        logger.warning("Cannot initialize series service - authentication not available")
        return False
    
    def sync_book_series(self, book_asin: str, book_metadata: Dict) -> Dict[str, Any]:
        """Sync series data for a specific book via series service."""
        return self.series_service.sync_book_series(book_asin, book_metadata)
    
    def refresh_series(self, series_asin: str) -> Dict[str, Any]:
        """Refresh data for a specific series via series service."""
        return self.series_service.refresh_series(series_asin)
    
    def sync_all_series(self, limit: int = None) -> Dict[str, Any]:
        """Sync series data for all books via series service."""
        return self.series_service.sync_all_series(limit)

# Global manager instance
_audible_manager = None

def get_audible_manager(config_service=None):
    """Get the global Audible manager instance."""
    global _audible_manager
    if _audible_manager is None:
        _audible_manager = AudibleServiceManager(config_service=config_service)
    return _audible_manager
