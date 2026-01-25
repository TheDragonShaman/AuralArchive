"""
Module Name: restart_services.py
Author: TheDragonShaman
Created: August 7, 2025
Last Modified: December 23, 2025
Description:
    Settings helper to reset all registered services via the service manager.
Location:
    /routes/settings_tools/restart_services.py

"""

from datetime import datetime

from flask import jsonify

from services.service_manager import service_manager
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.RestartAllServices")

def handle_restart_services():
    """Restart all services by resetting the service manager."""
    try:
        # Reset all services through the service manager
        service_manager.reset_all_services()
        
        logger.info("All services restarted successfully")
        return jsonify({
            'success': True,
            'message': 'All services restarted successfully',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error restarting services: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to restart services: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500