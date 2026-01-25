"""
Module Name: validate_config.py
Author: TheDragonShaman
Created: August 10, 2025
Last Modified: December 23, 2025
Description:
    Settings helper to validate configuration and return detailed results.
Location:
    /routes/settings_tools/validate_config.py

"""

from datetime import datetime

from flask import jsonify

from services.service_manager import get_config_service
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.ValidateConfig")

def handle_validate_configuration():
    """Validate all configuration settings with detailed results - FIXED."""
    try:
        config_service = get_config_service()
        
        # Use the actual method that exists
        try:
            validation_results = config_service.validate_config()
        except AttributeError:
            # If validate_config doesn't exist, create basic validation
            config_data = config_service.list_config()
            validation_results = {}
            
            # Basic validation checks
            for section_name, section_data in config_data.items():
                if isinstance(section_data, dict):
                    validation_results[section_name] = len(section_data) > 0
                else:
                    validation_results[section_name] = bool(section_data)
        
        overall_valid = all(validation_results.values()) if validation_results else False
        
        return jsonify({
            'success': True,
            'valid': overall_valid,
            'results': validation_results,
            'valid_sections': sum(validation_results.values()) if validation_results else 0,
            'total_sections': len(validation_results) if validation_results else 0,
            'summary': f"{sum(validation_results.values())} of {len(validation_results)} sections valid" if validation_results else "No validation results",
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to validate configuration: {str(e)}'
        }), 500