"""
Download Logs Route - AuralArchive

Lets administrators download the primary web log file directly from the
settings interface.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
from datetime import datetime

from flask import jsonify, send_file

from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.DownloadLogs")

def handle_download_logs():
    """Download system logs."""
    try:
        log_file = 'auralarchive_web.log'
        
        if os.path.exists(log_file):
            return send_file(
                log_file,
                as_attachment=True,
                download_name=f"auralarchive_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
        else:
            return jsonify({
                'success': False,
                'error': 'Log file not found'
            }), 404
    
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to download logs: {str(e)}'
        }), 500