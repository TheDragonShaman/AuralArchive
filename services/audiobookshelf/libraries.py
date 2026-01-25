"""
Module Name: libraries.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Handle AudioBookShelf library browsing, item retrieval, caching, and ASIN extraction helpers.
Location:
    /services/audiobookshelf/libraries.py

"""
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from utils.logger import get_module_logger

ASIN_PATTERN = re.compile(r"(B[0-9A-Z]{9})", re.IGNORECASE)


class AudioBookShelfLibraries:
    """Manages AudioBookShelf library operations and caching."""

    def __init__(self, connection, logger=None):
        self.connection = connection
        self.logger = logger or get_module_logger("Service.AudioBookShelf.Libraries")
        self._libraries_cache = None
        self._last_library_fetch = 0
    
    def get_libraries(self, host: str = None, api_key: str = None) -> List[Dict]:
        """Get list of libraries from AudioBookShelf with optional custom credentials."""
        try:
            # If host and api_key provided, use them directly
            if host and api_key:
                return self._get_libraries_with_credentials(host, api_key)
            
            # Otherwise use cached approach with stored config
            # Check if we have cached libraries (refresh every 5 minutes)
            if (self._libraries_cache is not None and 
                time.time() - self._last_library_fetch < 300):
                return self._libraries_cache
            
            # Refresh cache
            self._refresh_libraries_cache()
            
            return self._libraries_cache or []
        
        except Exception as exc:
            self.logger.error(
                "Error getting libraries",
                extra={"error": str(exc)},
            )
            return []
    
    def _get_libraries_with_credentials(self, host: str, api_key: str) -> List[Dict]:
        """Get libraries using provided credentials."""
        try:
            base_url = host.rstrip('/')
            if not base_url.startswith(('http://', 'https://')):
                base_url = f"http://{base_url}"
            
            url = f"{base_url}/api/libraries"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'User-Agent': 'AuralArchive/1.0.0',
                'Content-Type': 'application/json'
            }
            
            import requests
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and 'libraries' in data:
                    libraries = data['libraries']
                elif isinstance(data, list):
                    libraries = data
                else:
                    libraries = []
                
                # Format library data
                formatted_libraries = []
                for lib in libraries:
                    formatted_libraries.append({
                        'id': lib.get('id', ''),
                        'name': lib.get('name', ''),
                        'mediaType': lib.get('mediaType', ''),
                        'provider': lib.get('provider', '')
                    })
                
                return formatted_libraries
            else:
                self.logger.error(f"Failed to get libraries: HTTP {response.status_code}")
                return []
        
        except Exception as exc:
            self.logger.error(
                "Error getting libraries with credentials",
                extra={"error": str(exc)},
            )
            return []
    
    def _refresh_libraries_cache(self):
        """Refresh the libraries cache."""
        try:
            if not self.connection.ensure_authenticated():
                return
            
            base_url = self.connection.get_base_url()
            url = f"{base_url}/libraries"
            
            response = self.connection.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                libraries = []
                
                # Handle both single library and array response
                library_data = data.get('libraries', data if isinstance(data, list) else [data])
                
                for lib in library_data:
                    library_info = {
                        'id': lib.get('id', ''),
                        'name': lib.get('name', ''),
                        'mediaType': lib.get('mediaType', 'book'),
                        'provider': lib.get('provider', 'audible'),
                        'bookCount': lib.get('stats', {}).get('totalItems', 0),
                        'size': lib.get('stats', {}).get('totalSize', 0),
                        'duration': lib.get('stats', {}).get('totalDuration', 0)
                    }
                    
                    # If no stats in main response, try to get them separately
                    if library_info['bookCount'] == 0:
                        self._fetch_library_stats(lib.get('id'), library_info, base_url)
                    
                    libraries.append(library_info)
                
                self._libraries_cache = libraries
                self._last_library_fetch = time.time()
                
        except Exception as exc:
            self.logger.error(
                "Error refreshing libraries cache",
                extra={"error": str(exc)},
            )
    
    def _fetch_library_stats(self, library_id, library_info, base_url):
        """Fetch stats for a specific library."""
        try:
            stats_url = f"{base_url}/libraries/{library_id}/stats"
            stats_response = self.connection.session.get(stats_url, timeout=10)
            if stats_response.status_code == 200:
                stats_data = stats_response.json()
                library_info['bookCount'] = stats_data.get('totalItems', 0)
                library_info['size'] = stats_data.get('totalSize', 0)
                library_info['duration'] = stats_data.get('totalDuration', 0)
        except:
            # If stats call fails, try getting first page of items to count
            try:
                items_url = f"{base_url}/libraries/{library_id}/items"
                items_response = self.connection.session.get(items_url, params={'limit': 1}, timeout=10)
                if items_response.status_code == 200:
                    items_data = items_response.json()
                    library_info['bookCount'] = items_data.get('total', 0)
            except:
                pass
    
    def get_library_items(self, library_id: str, limit: int = 100, page: int = 0) -> Tuple[bool, List[Dict], str]:
        """Get items from a specific library with pagination."""
        try:
            if not self.connection.ensure_authenticated():
                return False, [], "Authentication failed"
            
            base_url = self.connection.get_base_url()
            url = f"{base_url}/libraries/{library_id}/items"
            
            params = {
                'limit': limit,
                'page': page,
                'sort': 'addedAt',
                'desc': 1
            }
            
            response = self.connection.session.get(url, params=params, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                items = []
                
                for item in data.get('results', []):
                    book = self._format_library_item(item)
                    items.append(book)
                
                total = data.get('total', len(items))
                return True, items, f"Retrieved {len(items)} of {total} items"
            else:
                return False, [], f"Failed to get library items: HTTP {response.status_code}"
        
        except Exception as exc:
            self.logger.error(
                "Error getting library items",
                extra={"error": str(exc)},
            )
            return False, [], f"Error: {str(exc)}"
    
    def search_library_items(self, library_id: str, query: str) -> Tuple[bool, List[Dict], str]:
        """Search for items in a specific library."""
        try:
            if not self.connection.ensure_authenticated():
                return False, [], "Authentication failed"
            
            base_url = self.connection.get_base_url()
            url = f"{base_url}/libraries/{library_id}/search"
            
            params = {
                'q': query,
                'limit': 25
            }
            
            response = self.connection.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('book', [])  # AudioBookShelf returns results under 'book' key
                
                processed_items = []
                for item in items:
                    processed_items.append({
                        'id': item.get('id', ''),
                        'title': item.get('title', ''),
                        'author': item.get('author', ''),
                        'series': item.get('series', ''),
                        'matchKey': item.get('matchKey', ''),
                        'matchText': item.get('matchText', '')
                    })
                
                return True, processed_items, f"Found {len(processed_items)} search results"
            else:
                return False, [], f"Search failed: HTTP {response.status_code}"
        
        except Exception as exc:
            self.logger.error(
                "Error searching library",
                extra={"error": str(exc)},
            )
            return False, [], f"Error: {str(exc)}"
    
    def _format_library_item(self, item):
        """Format a library item for consistent output."""
        media = item.get('media', {})
        metadata = media.get('metadata', {})
        
        # Handle authors array
        authors = metadata.get('authors', [])
        author_names = [auth.get('name', '') for auth in authors if auth.get('name')]
        
        # Handle narrators array  
        narrators = metadata.get('narrators', [])
        narrator_names = [narr if isinstance(narr, str) else narr.get('name', '') for narr in narrators]
        
        # Handle series array
        series_list = metadata.get('series', [])
        series_info = []
        for series in series_list:
            if isinstance(series, dict):
                series_info.append(series.get('name', ''))
            else:
                series_info.append(str(series))
        # File path can appear at item or media level depending on ABS version
        path_value = (
            item.get('path')
            or media.get('path')
            or media.get('filePath')
            or ''
        )

        asin_value = self._extract_asin_value(item, media, metadata, path_value)
        
        return {
            'id': item.get('id', ''),
            'ino': item.get('ino', ''),
            'title': metadata.get('title', ''),
            'subtitle': metadata.get('subtitle', ''),
            'author': ', '.join(author_names),
            'narrator': ', '.join(narrator_names),
            'series': ', '.join(series_info),
            'isbn': metadata.get('isbn', ''),
            'asin': asin_value or '',
            'description': metadata.get('description', ''),
            'publisher': metadata.get('publisher', ''),
            'publishedYear': metadata.get('publishedYear', ''),
            'publishedDate': metadata.get('publishedDate', ''),
            'language': metadata.get('language', ''),
            'duration': media.get('duration', 0),
            'size': media.get('size', 0),
            'path': path_value,
            'addedAt': item.get('addedAt', 0),
            'updatedAt': item.get('updatedAt', 0),
            'libraryId': item.get('libraryId', ''),
            'coverPath': media.get('coverPath', ''),
            'tags': media.get('tags', []),
            'explicit': metadata.get('explicit', False)
        }

    def _extract_asin_value(self, item: Dict, media: Dict, metadata: Dict, path_value: str) -> Optional[str]:
        """Find the most reliable ASIN available for an AudioBookShelf item."""
        direct_fields = [
            metadata.get('asin'),
            metadata.get('audible_asin'),
            metadata.get('audibleAsin'),
            metadata.get('asin_local'),
            metadata.get('asinLocal'),
            media.get('asin'),
            media.get('audibleAsin'),
            media.get('asin_local'),
            item.get('asin'),
            item.get('audibleAsin')
        ]

        for value in direct_fields:
            normalized = self._normalize_asin_candidate(value, allow_numeric=True)
            if normalized:
                return normalized

        structured_sources = [metadata, media, item]
        for source in structured_sources:
            asin = self._extract_asin_from_dict(source)
            if asin:
                return asin

        identifier_sources = [
            metadata.get('identifiers'),
            media.get('identifiers'),
            metadata.get('providerIds'),
            media.get('providerIds')
        ]
        for source in identifier_sources:
            asin = self._extract_asin_from_identifiers(source)
            if asin:
                return asin

        tag_sources = [metadata.get('tags'), media.get('tags'), item.get('tags')]
        for tags in tag_sources:
            asin = self._extract_asin_from_iterable(tags)
            if asin:
                return asin

        link_sources = [metadata.get('links'), media.get('links'), item.get('links')]
        for links in link_sources:
            asin = self._extract_asin_from_links(links)
            if asin:
                return asin

        file_path_match = self._normalize_asin_candidate(path_value)
        if file_path_match:
            return file_path_match

        return None

    def _extract_asin_from_dict(self, data: Optional[Dict]) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        for key, value in data.items():
            key_lower = str(key).lower()
            if 'asin' in key_lower:
                normalized = self._normalize_asin_candidate(value, allow_numeric=True)
                if normalized:
                    return normalized
            if isinstance(value, dict):
                nested = self._extract_asin_from_dict(value)
                if nested:
                    return nested
            elif isinstance(value, list):
                nested = self._extract_asin_from_iterable(value)
                if nested:
                    return nested
        return None

    def _extract_asin_from_iterable(self, values: Optional[List[Any]]) -> Optional[str]:
        if not isinstance(values, list):
            return None
        for entry in values:
            if isinstance(entry, dict):
                nested = self._extract_asin_from_dict(entry)
                if nested:
                    return nested
            elif isinstance(entry, list):
                nested = self._extract_asin_from_iterable(entry)
                if nested:
                    return nested
            else:
                normalized = self._normalize_asin_candidate(entry)
                if normalized:
                    return normalized
        return None

    def _extract_asin_from_identifiers(self, identifiers: Any) -> Optional[str]:
        if isinstance(identifiers, dict):
            for value in identifiers.values():
                normalized = self._normalize_asin_candidate(value)
                if normalized:
                    return normalized
        elif isinstance(identifiers, list):
            for entry in identifiers:
                if isinstance(entry, dict):
                    normalized = self._normalize_asin_candidate(
                        entry.get('value') or entry.get('id') or entry.get('code')
                    )
                    if normalized:
                        return normalized
                else:
                    normalized = self._normalize_asin_candidate(entry)
                    if normalized:
                        return normalized
        return None

    def _extract_asin_from_links(self, links: Any) -> Optional[str]:
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict):
                    normalized = self._normalize_asin_candidate(link.get('url') or link.get('href'))
                    if normalized:
                        return normalized
                else:
                    normalized = self._normalize_asin_candidate(link)
                    if normalized:
                        return normalized
        return None

    @staticmethod
    def _normalize_asin_candidate(value: Any, allow_numeric: bool = False) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            value = str(value)
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate:
            return None
        match = ASIN_PATTERN.search(candidate.upper())
        if match:
            return match.group(1).upper()
        if allow_numeric:
            alnum = candidate.replace('-', '').strip()
            if len(alnum) == 10 and alnum.isalnum():
                return alnum.upper()
        return None