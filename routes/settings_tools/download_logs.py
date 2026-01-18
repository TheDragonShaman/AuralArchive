"""
Module Name: download_logs.py
Author: TheDragonShaman
Created: July 29, 2025
Last Modified: December 23, 2025
Description:
    Settings helper to download application logs through the admin interface.
Location:
    /routes/settings_tools/download_logs.py

"""

import os
from datetime import datetime

from flask import jsonify, send_file

from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.DownloadLogs")

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