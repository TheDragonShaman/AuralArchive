"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Package initializer for image caching services and helper utilities.

Location:
    /services/image_cache/__init__.py

"""

from .image_cache_service import ImageCacheService, get_image_cache_service
from .helpers import (
    cache_image,
    cache_author_image,
    cache_book_cover,
    get_cached_author_image_url,
    get_cached_book_cover_url,
    preload_images_from_database,
    preload_author_images_from_database,  # Backward compatibility
)

__all__ = [
    'ImageCacheService',
    'get_image_cache_service',
    'cache_image',
    'cache_author_image',
    'cache_book_cover',
    'get_cached_author_image_url',
    'get_cached_book_cover_url',
    'preload_images_from_database',
    'preload_author_images_from_database',
]