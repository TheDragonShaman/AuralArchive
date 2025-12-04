from typing import Optional, List, Dict, Any
import logging
from .image_cache_service import get_image_cache_service

logger = logging.getLogger("ImageCacheHelpers")

def cache_image(image_url: str) -> Optional[str]:
    """
    Cache any image (author image or book cover) and return the local URL.
    
    Args:
        image_url: Original image URL
        
    Returns:
        Local cached image URL or None if caching fails or URL is invalid
    """
    if not image_url:
        return None
        
    try:
        image_cache = get_image_cache_service()
        cached_url = image_cache.get_cached_image_url(image_url)
        
        if cached_url:
            logger.debug(f"Image cached successfully: {image_url} -> {cached_url}")
            return cached_url
        else:
            logger.warning(f"Failed to cache image: {image_url}")
            # Don't fall back to original URL if it's invalid
            if image_url.startswith('/metadata/items/'):
                logger.warning(f"Invalid metadata URL, returning None: {image_url}")
                return None
            return image_url
            
    except Exception as e:
        logger.error(f"Error caching image {image_url}: {e}")
        # Don't fall back to original URL if it's invalid
        if image_url.startswith('/metadata/items/'):
            logger.warning(f"Invalid metadata URL, returning None: {image_url}")
            return None
        return image_url

def cache_author_image(author_image_url: str) -> Optional[str]:
    """
    Cache an author image and return the local URL.
    (Wrapper for cache_image for backward compatibility)
    """
    return cache_image(author_image_url)

def cache_book_cover(cover_image_url: str) -> Optional[str]:
    """
    Cache a book cover image and return the local URL.
    """
    return cache_image(cover_image_url)

def get_cached_author_image_url(author_data: Dict[str, Any]) -> Optional[str]:
    """
    Get cached author image URL from author data, with fallback logic.
    
    Args:
        author_data: Author data dictionary
        
    Returns:
        Cached image URL or None
    """
    # Try different possible image URL fields
    image_url = (
        author_data.get('author_image_url') or 
        author_data.get('author_image') or 
        author_data.get('image_url') or
        author_data.get('cover_image')
    )
    
    if image_url:
        return cache_image(image_url)
    
    return None

def get_cached_book_cover_url(book_data: Dict[str, Any]) -> Optional[str]:
    """
    Get cached book cover image URL from book data, with fallback logic.
    
    Args:
        book_data: Book data dictionary
        
    Returns:
        Cached image URL or None
    """
    # Try different possible cover image URL fields
    cover_url = (
        book_data.get('cover_image') or 
        book_data.get('Cover Image') or  # Legacy support
        book_data.get('cover_url') or
        book_data.get('image_url')
    )
    
    if cover_url:
        return cache_image(cover_url)
    
    return None

def preload_images_from_database():
    """
    Preload all images (author images and book covers) from the database into the cache.
    This runs automatically in the background.
    """
    try:
        image_cache = get_image_cache_service()
        results = image_cache.preload_images_from_database()
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        if total_count > 0:
            logger.info(f"Preloaded {success_count}/{total_count} images successfully")
        
        return results
        
    except Exception as e:
        logger.error(f"Error preloading images: {e}")
        return {}

# Backward compatibility
preload_author_images_from_database = preload_images_from_database
