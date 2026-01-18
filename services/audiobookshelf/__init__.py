"""
Module Name: __init__.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
	Expose the AudioBookShelf service entry point.
Location:
	/services/audiobookshelf/__init__.py

"""

from .audiobookshelf_service import AudioBookShelfService

__all__ = ["AudioBookShelfService"]