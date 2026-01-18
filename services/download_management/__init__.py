"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
	Orchestrates the complete download workflow from queue to library import.
	Main service coordinates all download operations while helper modules
	handle specific concerns (queue, state, monitoring, etc.). The download
	pipeline uses database-driven state tracking with ASIN as the primary
	identifier and emits real-time progress updates via SocketIO.

Location:
	/services/download_management/__init__.py

"""

from .download_management_service import DownloadManagementService

__all__ = ['DownloadManagementService']
