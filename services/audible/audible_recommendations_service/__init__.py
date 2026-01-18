"""
Module Name: __init__.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Exports recommendations service helpers.
Location:
    /services/audible/audible_recommendations_service/__init__.py

"""

from .audible_recommendations_service import (
    AudibleRecommendationsService,
    get_audible_recommendations_service,
)

__all__ = [
    "AudibleRecommendationsService",
    "get_audible_recommendations_service",
]
