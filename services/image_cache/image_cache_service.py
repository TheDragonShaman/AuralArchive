"""
Module Name: image_cache_service.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Local image caching service to reduce external requests for author images
    and book covers. Supports preload from DB and cache size management.

Location:
    /services/image_cache/image_cache_service.py

"""

import os
import hashlib
import requests
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import time

from utils.logger import get_module_logger

_LOGGER = get_module_logger("Service.ImageCache.Service")

class ImageCacheService:
    """Local image caching service to reduce external web requests for author images and book covers."""
    
    def __init__(self, cache_dir: str = None, cache_type: str = "local", max_cache_size_mb: int = 500, *, logger=None):
        """
        Initialize the image cache service.
        
        Args:
            cache_dir: Directory to store cached images (default: static/cache/{cache_type}/images)
            cache_type: Type of cache - "local" or "audible"
            max_cache_size_mb: Maximum cache size in MB before cleanup
        """
        self.logger = logger or _LOGGER
        self.cache_type = cache_type
        
        # Set up cache directory with new structure
        if cache_dir is None:
            base_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static', 'cache')
            cache_dir = os.path.join(base_cache_dir, cache_type, 'images')
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AuralArchive/1.0 (Image Cache Service)'
        })
        
        self.logger.success(
            "Image cache service started successfully",
            extra={"cache_dir": str(self.cache_dir), "cache_type": self.cache_type},
        )
        
    def _generate_cache_key(self, url: str) -> str:
        """Generate a unique cache key from URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _normalize_url(self, url: str) -> str:
        """Convert relative URLs to absolute URLs for downloading."""
        if url.startswith('http://') or url.startswith('https://'):
            return url
        elif url.startswith('/'):
            # This is a relative URL - we need to construct the full URL
            # For local metadata files, they should be served from the local server
            return f"http://localhost:5000{url}"
        else:
            # Assume it's a relative path without leading slash
            return f"http://localhost:5000/{url}"
    
    def _get_cache_path(self, cache_key: str, extension: str = None) -> Path:
        """Get the full path for a cached file."""
        if extension and not extension.startswith('.'):
            extension = f'.{extension}'
        elif not extension:
            extension = '.jpg'  # Default extension
            
        return self.cache_dir / f"{cache_key}{extension}"
    
    def _detect_extension_from_url(self, url: str) -> str:
        """Detect file extension from URL."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Common image extensions
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
            if path.endswith(ext):
                return ext
                
        return '.jpg'  # Default
    
    def _detect_extension_from_content(self, response: requests.Response) -> str:
        """Detect file extension from response content type."""
        content_type = response.headers.get('content-type', '').lower()
        
        extension_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg', 
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp'
        }
        
        return extension_map.get(content_type, '.jpg')
    
    def _download_image(self, url: str, cache_path: Path) -> bool:
        """Download an image from URL to cache path."""
        try:
            # Normalize the URL to handle relative paths
            full_url = self._normalize_url(url)
            self.logger.debug(f"Downloading image: {url} -> {full_url}")
            
            response = self.session.get(full_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Verify it's an image
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                self.logger.warning(f"URL does not return an image: {url} (content-type: {content_type})")
                return False
            
            # Write to a unique temporary file first, then move to final location
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode='wb',
                    delete=False,
                    dir=str(cache_path.parent),
                    prefix=cache_path.stem + '.',
                    suffix=cache_path.suffix + '.tmp',
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                os.replace(temp_path, cache_path)
            finally:
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
            
            self.logger.debug(f"Image cached successfully: {cache_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to download image {url}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error caching image {url}: {e}")
            return False
    
    def _cleanup_cache(self):
        """Remove old cache files if cache size exceeds limit."""
        try:
            # Get all cache files with their sizes and modification times
            cache_files = []
            total_size = 0
            
            for file_path in self.cache_dir.glob('*'):
                if file_path.is_file() and not file_path.name.endswith('.tmp'):
                    stat = file_path.stat()
                    cache_files.append({
                        'path': file_path,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime
                    })
                    total_size += stat.st_size
            
            if total_size <= self.max_cache_size_bytes:
                return
            
            self.logger.info(
                "Cache size exceeds limit; cleaning up",
                extra={
                    "cache_size_mb": round(total_size / 1024 / 1024, 1),
                    "limit_mb": round(self.max_cache_size_bytes / 1024 / 1024, 1),
                },
            )
            
            # Sort by modification time (oldest first)
            cache_files.sort(key=lambda x: x['mtime'])
            
            # Remove files until we're under the limit
            target_size = self.max_cache_size_bytes * 0.8  # Remove extra 20% for buffer
            
            for file_info in cache_files:
                if total_size <= target_size:
                    break
                    
                try:
                    file_info['path'].unlink()
                    total_size -= file_info['size']
                    self.logger.debug(f"Removed cached file: {file_info['path']}")
                except Exception as e:
                    self.logger.error(f"Error removing cache file {file_info['path']}: {e}")
            
            self.logger.info(
                "Cache cleanup completed",
                extra={"cache_size_mb": round(total_size / 1024 / 1024, 1)},
            )
            
        except Exception as e:
            self.logger.error(f"Error during cache cleanup: {e}")
    
    def get_cached_image_url(self, original_url: str) -> Optional[str]:
        """
        Get a local cached version of an image URL.
        
        Args:
            original_url: The original image URL
            
        Returns:
            Local URL path to cached image, or None if caching failed
        """
        if not original_url:
            return None
            
        try:
            # Skip caching for valid local static files - return them as-is
            if original_url.startswith('/static/'):
                self.logger.debug(f"Skipping cache for static URL: {original_url}")
                return original_url
            
            # Handle invalid /metadata/items/ URLs - these don't exist, return None
            if original_url.startswith('/metadata/items/'):
                self.logger.warning(f"Invalid metadata URL detected: {original_url} - returning None")
                return None
            
            # Generate cache key and determine file extension
            cache_key = self._generate_cache_key(original_url)
            extension = self._detect_extension_from_url(original_url)
            cache_path = self._get_cache_path(cache_key, extension)
            
            # Check if already cached
            if cache_path.exists():
                # Update access time
                cache_path.touch()
                
                # Return relative URL path from static directory
                relative_path = cache_path.relative_to(Path(__file__).parent.parent.parent / 'static')
                return f"/static/{relative_path.as_posix()}"
            
            # Only try to download external URLs (http/https)
            if original_url.startswith('http://') or original_url.startswith('https://'):
                # Try to download and cache the image
                if self._download_image(original_url, cache_path):
                    # Cleanup cache if needed
                    self._cleanup_cache()
                    
                    # Return relative URL path
                    relative_path = cache_path.relative_to(Path(__file__).parent.parent.parent / 'static')
                    return f"/static/{relative_path.as_posix()}"
            else:
                self.logger.debug(f"Skipping download for non-HTTP URL: {original_url}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error getting cached image for {original_url}: {e}")
            # Return None to allow fallback to original URL
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the image cache."""
        try:
            cache_files = list(self.cache_dir.glob('*'))
            cache_files = [f for f in cache_files if f.is_file() and not f.name.endswith('.tmp')]
            
            total_size = sum(f.stat().st_size for f in cache_files)
            
            return {
                'cache_dir': str(self.cache_dir),
                'total_files': len(cache_files),
                'total_size_mb': round(total_size / 1024 / 1024, 2),
                'max_size_mb': round(self.max_cache_size_bytes / 1024 / 1024, 2),
                'usage_percent': round((total_size / self.max_cache_size_bytes) * 100, 1) if self.max_cache_size_bytes > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}
    
    def clear_cache(self) -> bool:
        """Clear all cached images."""
        try:
            removed_count = 0
            for file_path in self.cache_dir.glob('*'):
                if file_path.is_file():
                    file_path.unlink()
                    removed_count += 1
            
            self.logger.info(f"Cache cleared: {removed_count} files removed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            return False
    
    def preload_images_from_database(self) -> Dict[str, bool]:
        """
        Preload all images (author images and book covers) from the database into the cache.
        
        Returns:
            Dict mapping URLs to success status
        """
        try:
            from services.service_manager import get_database_service
            
            db_service = get_database_service()
            conn, cursor = db_service.connect_db()
            
            try:
                # Get all image URLs from database (both author images and book covers)
                image_urls = []
                
                # Get author images
                cursor.execute('''
                    SELECT DISTINCT author_image_url 
                    FROM authors 
                    WHERE author_image_url IS NOT NULL 
                    AND author_image_url != ''
                ''')
                author_images = [row[0] for row in cursor.fetchall()]
                image_urls.extend(author_images)
                
                # Get book cover images
                cursor.execute('''
                    SELECT DISTINCT cover_image 
                    FROM books 
                    WHERE cover_image IS NOT NULL 
                    AND cover_image != ''
                    AND cover_image LIKE 'http%'
                ''')
                cover_images = [row[0] for row in cursor.fetchall()]
                image_urls.extend(cover_images)
                
                if image_urls:
                    self.logger.info(
                        f"Preloading {len(image_urls)} images into cache ({len(author_images)} author images, {len(cover_images)} book covers)..."
                    )

                    results: Dict[str, bool] = {}
                    for url in image_urls:
                        try:
                            cache_key = self._generate_cache_key(url)
                            extension = self._detect_extension_from_url(url)
                            cache_path = self._get_cache_path(cache_key, extension)

                            if cache_path.exists():
                                results[url] = True  # Already cached
                            else:
                                results[url] = self._download_image(url, cache_path)

                        except Exception as e:
                            self.logger.error(f"Error preloading image {url}: {e}")
                            results[url] = False

                    # Cleanup cache after preloading
                    self._cleanup_cache()

                    success_count = sum(1 for success in results.values() if success)
                    self.logger.info(
                        f"Preloaded {success_count}/{len(image_urls)} images successfully"
                    )

                    return results
                else:
                    self.logger.info("No images found in database to preload")
                    return {}
                    
            finally:
                conn.close()
                
        except Exception as e:
            self.logger.error(f"Error preloading images: {e}")
            return {}


# Global service instances
_local_image_cache_service = None
_audible_image_cache_service = None

def get_image_cache_service(cache_type: str = "local") -> ImageCacheService:
    """Get the image cache service instance for the specified type."""
    global _local_image_cache_service, _audible_image_cache_service
    
    if cache_type == "audible":
        if _audible_image_cache_service is None:
            _audible_image_cache_service = ImageCacheService(cache_type="audible")
        return _audible_image_cache_service
    else:  # default to local
        if _local_image_cache_service is None:
            _local_image_cache_service = ImageCacheService(cache_type="local")
        return _local_image_cache_service
