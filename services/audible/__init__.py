"""
Module Name: __init__.py
Author: TheDragonShaman
Created: August 12, 2025
Last Modified: December 23, 2025
Description:
    Exposes Audible service entry points and managers.
Location:
    /services/audible/__init__.py

"""

from .audible_catalog_service.audible_catalog_service import AudibleService
from .audible_wishlist_service.audible_wishlist_service import get_audible_wishlist_service
from .audible_recommendations_service.audible_recommendations_service import get_audible_recommendations_service
from .audible_service_manager import get_audible_manager, AudibleServiceManager

__all__ = [
    'AudibleService',
    'get_audible_wishlist_service',
    'get_audible_recommendations_service',
    'get_audible_manager',
    'AudibleServiceManager',
]
