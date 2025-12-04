"""
Audible API Helper - Python API-based library access
Replaces the broken CLI-based helper with direct Python API calls
"""

import audible
import logging
import math
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("AuralArchiveLogger")


class AudibleApiHelper:
    """
    Helper class for Audible Python API operations.
    Uses the audible package directly instead of CLI subprocess calls.
    """
    
    def __init__(self, auth_file: str = 'auth/audible_auth.json'):
        """
        Initialize the API helper.
        
        Args:
            auth_file: Path to the Audible authentication file
        """
        self.auth_file = auth_file
        self.auth = None
        self._load_auth()
    
    def _load_auth(self) -> bool:
        """
        Load authentication from file.
        
        Returns:
            True if auth loaded successfully, False otherwise
        """
        try:
            auth_path = Path(self.auth_file)
            if not auth_path.exists():
                logger.warning(f"Auth file not found: {self.auth_file}")
                return False
            
            self.auth = audible.Authenticator.from_file(str(auth_path))
            logger.info(f"Loaded Audible authentication from {self.auth_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load authentication: {e}")
            return False
    
    def is_available(self) -> bool:
        """
        Check if the API helper is available and authenticated.
        
        Returns:
            True if authenticated, False otherwise
        """
        return self.auth is not None
    
    def get_library_list(self, purchased_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get the user's Audible library using the Python API.
        
        This replaces the CLI 'audible library export' command with direct API calls.
        Uses pagination to fetch all library items with full metadata.
        
        Args:
            purchased_after: Optional date filter (YYYY-MM-DD format)
            
        Returns:
            List of library items with full metadata
            
        Raises:
            Exception: If not authenticated or API call fails
        """
        if not self.auth:
            raise Exception("Not authenticated. Please authenticate via the web UI.")
        
        try:
            logger.info("Fetching library from Audible API...")
            
            # Response groups for full metadata (from audible-cli source)
            response_groups = (
                "contributors, customer_rights, media, price, product_attrs, "
                "product_desc, product_extended_attrs, product_plan_details, "
                "product_plans, rating, sample, sku, series, reviews, ws4v, "
                "relationships, review_attrs, categories, category_ladders, "
                "claim_code_url, in_wishlist, listening_status, periodicals, "
                "provided_review, product_details"
            )
            
            # Build request parameters
            params = {
                'num_results': 1000,  # Max items per page
                'page': 1,
                'response_groups': response_groups
            }
            
            # Add date filter if provided
            if purchased_after:
                params['purchased_after'] = purchased_after
                logger.info(f"Filtering library items purchased after: {purchased_after}")
            
            all_items = []
            
            with audible.Client(auth=self.auth) as client:
                # Fetch first page to get total count
                logger.info("Fetching page 1...")
                response = client.get("library", **params)
                
                items = response.get('items', [])
                total_results = response.get('total_results', 0)
                
                all_items.extend(items)
                logger.info(f"Page 1: Got {len(items)} items, total in library: {total_results}")
                
                # Calculate total pages needed
                total_pages = math.ceil(total_results / 1000)
                
                # Fetch remaining pages
                if total_pages > 1:
                    logger.info(f"Fetching remaining {total_pages - 1} pages...")
                    
                    for page in range(2, total_pages + 1):
                        params['page'] = page
                        logger.info(f"Fetching page {page}/{total_pages}...")
                        
                        page_response = client.get("library", **params)
                        page_items = page_response.get('items', [])
                        
                        all_items.extend(page_items)
                        logger.info(f"Page {page}: Got {len(page_items)} items")
            
            logger.info(f"Library fetch complete: {len(all_items)} total items")
            return all_items
            
        except Exception as e:
            logger.error(f"Error fetching library from API: {e}", exc_info=True)
            raise
    
    def get_version(self) -> Dict[str, Any]:
        """
        Get version information about the audible package.
        
        Returns:
            Dict with version info
        """
        return {
            'version': audible.__version__,
            'package': 'audible (Python API)',
            'available': True
        }
    
    def check_status(self) -> Dict[str, Any]:
        """
        Check the status of the API helper.
        
        Returns:
            Dict with status information
        """
        try:
            if not self.auth:
                return {
                    'available': False,
                    'authenticated': False,
                    'error': 'Not authenticated'
                }
            
            # Try a simple API call to verify auth works
            with audible.Client(auth=self.auth) as client:
                account_info = client.get("1.0/account/information")
            
            return {
                'available': True,
                'authenticated': True,
                'version': audible.__version__,
                'marketplace': account_info.get('marketplace'),
                'account': account_info.get('name')
            }
            
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {
                'available': True,
                'authenticated': False,
                'error': str(e)
            }

    def get_activation_bytes(self, reload: bool = False) -> Dict[str, Any]:
        """Retrieve activation bytes using the audible Python API."""
        try:
            if not self.auth and not self._load_auth():
                return {
                    'success': False,
                    'error': 'Not authenticated'
                }

            if reload:
                try:
                    self.auth.refresh_access_token()
                except Exception as exc:
                    logger.debug("Failed to refresh access token before reloading activation bytes: %s", exc)

            activation_bytes = self.auth.get_activation_bytes()

            if not activation_bytes:
                return {
                    'success': False,
                    'error': 'Activation bytes unavailable'
                }

            normalized = self._normalize_activation_bytes(activation_bytes)

            try:
                # Persist the updated auth blob so the bytes are cached for future calls
                self.auth.to_file(self.auth_file)
            except Exception as exc:
                logger.debug("Unable to persist activation bytes to auth file %s: %s", self.auth_file, exc)

            return {
                'success': True,
                'activation_bytes': normalized
            }

        except Exception as exc:
            logger.error("Error retrieving activation bytes via API: %s", exc)
            return {
                'success': False,
                'error': str(exc)
            }

    @staticmethod
    def _normalize_activation_bytes(raw: Any) -> str:
        """Normalize activation bytes into a consistent uppercase hex string."""
        if isinstance(raw, (bytes, bytearray)):
            return raw.hex().upper()
        if isinstance(raw, str):
            return raw.strip().upper()
        if isinstance(raw, dict):
            for key in ('activation_bytes', 'bytes', 'value'):
                if key in raw and raw[key]:
                    return AudibleApiHelper._normalize_activation_bytes(raw[key])
        # Fallback: convert to string representation
        return str(raw).strip()
