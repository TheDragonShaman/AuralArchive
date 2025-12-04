"""
Download Routes - AuralArchive

Serves the downloads dashboard, surfacing pipeline status and recent imports
from the download management service.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from flask import Blueprint, render_template

from services.service_manager import get_download_management_service
from utils.logger import get_module_logger

downloads_bp = Blueprint('downloads', __name__)

logger = get_module_logger("DownloadsRoute")


@downloads_bp.route('')
@downloads_bp.route('/')
def downloads_page():
    """Render the downloads dashboard with pipeline and streaming activity."""
    dm_service = get_download_management_service()

    # Active pipeline items (non-terminal states)
    pipeline_items = dm_service.get_queue(limit=50)
    service_status = dm_service.get_service_status()

    # Recently imported items for quick history
    completed_items = dm_service.get_queue(status_filter='IMPORTED', limit=10)

    return render_template(
        'downloads.html',
        title='Downloads',
        pipeline_items=pipeline_items,
        service_status=service_status,
        completed_items=completed_items
    )
