"""
Module Name: imports.py
Author: TheDragonShaman
Created: July 21, 2025
Last Modified: December 23, 2025
Description:
    Manual import dashboard routes leveraging AudiobookShelf and import settings.
Location:
    /routes/imports.py

"""

from flask import Blueprint, render_template  # type: ignore
from flask_login import login_required

from services.service_manager import get_config_service
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Import")

import_bp = Blueprint('import_page', __name__)


@import_bp.route('')
@import_bp.route('/')
@login_required
def import_dashboard():
    """Render the manual import UI."""
    default_library_path = '/mnt/audiobooks'
    default_template = 'standard'
    import_directory = '/downloads/import'

    try:
        config_service = get_config_service()
        if config_service:
            abs_config = config_service.get_section('audiobookshelf') or {}
            default_library_path = abs_config.get('library_path', default_library_path)
            default_template = abs_config.get('naming_template', default_template)
            import_config = config_service.get_section('import') or {}
            import_directory = import_config.get('import_directory', import_directory)
    except Exception as exc:
        logger.warning("Unable to load config for import page: %s", exc)

    return render_template(
        'import.html',
        title='Import',
        default_library_path=default_library_path,
        default_template=default_template,
        import_directory=import_directory
    )
