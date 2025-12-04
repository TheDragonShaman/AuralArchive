"""
Download Management Module
==========================

Orchestrates the complete download workflow from queue to library import.

Architecture:
- Main service coordinates all download operations
- Helper modules handle specific concerns (queue, state, monitoring, etc.)
- Database-driven state tracking with ASIN as primary identifier
- Real-time progress updates via SocketIO
"""

from .download_management_service import DownloadManagementService

__all__ = ['DownloadManagementService']
