"""
Module Name: __init__.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
	Expose automation service entry points.
Location:
	/services/automation/__init__.py

"""

from .automatic_download_service import AutomaticDownloadService

__all__ = ["AutomaticDownloadService"]
