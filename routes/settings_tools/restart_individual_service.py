"""
Module Name: restart_individual_service.py
Author: TheDragonShaman
Created: August 6, 2025
Last Modified: December 23, 2025
Description:
    Settings helper to restart specific backend services from the UI.
Location:
    /routes/settings_tools/restart_individual_service.py

"""

from datetime import datetime

from flask import jsonify

from services.service_manager import (
    get_audiobookshelf_service,
    get_audible_service,
    get_config_service,
    get_database_service,
    get_metadata_update_service,
    service_manager,
)
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.RestartService")

def handle_restart_individual_service(service_name):
    """Restart a specific service."""
    try:
        service_mapping = {
            'database': get_database_service,
            'audible': get_audible_service,
            'audiobookshelf': get_audiobookshelf_service,
            'metadata_update': get_metadata_update_service,
            'config': get_config_service
        }
        
        if service_name not in service_mapping:
            return jsonify({
                'success': False,
                'error': f'Unknown service: {service_name}',
                'available_services': list(service_mapping.keys())
            }), 400
        
        # Get the service and attempt to restart it
        service_function = service_mapping[service_name]
        
        # Reset the specific service through service manager
        if hasattr(service_manager, 'reset_service'):
            service_manager.reset_service(service_name)
        else:
            # Fallback: reinitialize the service
            service_function()
        
        logger.info(f"Service '{service_name}' restarted successfully")
        return jsonify({
            'success': True,
            'message': f'Service {service_name} restarted successfully',
            'service': service_name,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error restarting service {service_name}: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to restart service {service_name}: {str(e)}',
            'service': service_name,
            'timestamp': datetime.now().isoformat()
        }), 500