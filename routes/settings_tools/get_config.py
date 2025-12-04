"""
Get Configuration Route - AuralArchive

Serializes the current configuration into sectioned JSON for the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from datetime import datetime

from flask import jsonify

from services.service_manager import get_config_service
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.GetConfig")

def handle_get_config():
    """Get current configuration for AuralArchive settings UI."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Organize configuration into sections
        organized_config = {}
        
        # Process each configuration section
        for section_name, section_data in config_data.items():
            organized_config[section_name] = {}
            
            if isinstance(section_data, dict):
                organized_config[section_name] = section_data
            else:
                # Handle non-dict configuration values
                organized_config[section_name] = {'value': section_data}
        
        # Add metadata about configuration
        config_metadata = {
            'sections_count': len(config_data),
            'last_loaded': datetime.now().isoformat(),
            'configuration_valid': bool(config_data)
        }
        
        return jsonify({
            'success': True,
            'config': organized_config,
            'metadata': config_metadata,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting configuration: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to get configuration: {str(e)}'
        }), 500