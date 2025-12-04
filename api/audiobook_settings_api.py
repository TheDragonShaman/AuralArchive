"""
Audiobook Settings API - AuralArchive

Centralizes config CRUD for indexers, download clients, coordination, and file
processing modules so the UI can manage automation settings through Flask.

Author: AuralArchive Development Team
Updated: December 4, 2025
"""

from functools import wraps

from flask import Blueprint, jsonify, request

from utils.logger import get_module_logger

# Create blueprint
audiobook_settings_bp = Blueprint('audiobook_settings', __name__)
logger = get_module_logger("API.AudiobookSettings")

def handle_errors(f):
    """Decorator to handle API errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error("API error in %s: %s", f.__name__, e)
            return jsonify({'error': str(e), 'success': False}), 500
    return decorated_function

@audiobook_settings_bp.route('/api/audiobook-services/config', methods=['GET'])
@handle_errors
def get_audiobook_config():
    """Get complete audiobook services configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        config = config_manager.get_full_config()
        validation = config_manager.validate_config()
        enabled_services = config_manager.get_enabled_services()
        
        return jsonify({
            'success': True,
            'config': config,
            'validation': validation,
            'enabled_services': enabled_services
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/indexers/<indexer_name>', methods=['GET'])
@handle_errors
def get_indexer_config(indexer_name):
    """Get configuration for specific indexer"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        config = config_manager.get_indexer_config(indexer_name)
        
        
        return jsonify({
            'success': True,
            'indexer': indexer_name,
            'config': config
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get indexer configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/indexers/<indexer_name>', methods=['PUT'])
@handle_errors
def update_indexer_config(indexer_name):
    """Update configuration for specific indexer"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        success = config_manager.update_indexer_config(indexer_name, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Indexer {indexer_name} configuration updated'
            })
        else:
            return jsonify({'error': 'Failed to update indexer configuration'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Failed to update indexer configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/clients/<client_name>', methods=['GET'])
@handle_errors
def get_client_config(client_name):
    """Get configuration for specific client"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        config = config_manager.get_client_config(client_name)
        
        return jsonify({
            'success': True,
            'client': client_name,
            'config': config
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get client configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/clients/<client_name>', methods=['PUT'])
@handle_errors
def update_client_config(client_name):
    """Update configuration for specific client"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        success = config_manager.update_client_config(client_name, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Client {client_name} configuration updated'
            })
        else:
            return jsonify({'error': 'Failed to update client configuration'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Failed to update client configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/download-coordination', methods=['GET'])
@handle_errors
def get_download_coordination_config():
    """Get download coordination configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        config = config_manager.get_download_coordination_config()
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get download coordination configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/download-coordination', methods=['PUT'])
@handle_errors
def update_download_coordination_config():
    """Update download coordination configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        success = config_manager.update_download_coordination_config(data)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Download coordination configuration updated'
            })
        else:
            return jsonify({'error': 'Failed to update download coordination configuration'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Failed to update download coordination configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/file-processing', methods=['GET'])
@handle_errors
def get_file_processing_config():
    """Get file processing configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        config = config_manager.get_file_processing_config()
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get file processing configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/config/file-processing', methods=['PUT'])
@handle_errors
def update_file_processing_config():
    """Update file processing configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        success = config_manager.update_file_processing_config(data)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'File processing configuration updated'
            })
        else:
            return jsonify({'error': 'Failed to update file processing configuration'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Failed to update file processing configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/validate', methods=['POST'])
@handle_errors
def validate_audiobook_config():
    """Validate audiobook services configuration"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        validation = config_manager.validate_config()
        
        return jsonify({
            'success': True,
            'validation': validation
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to validate configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/reload', methods=['POST'])
@handle_errors
def reload_audiobook_config():
    """Reload audiobook services configuration from file"""
    try:
        from services.service_manager import get_config_service
        config_manager = get_config_service()
        
        if not config_manager:
            return jsonify({'error': 'Configuration manager not available'}), 500
        
        success = config_manager.reload_config()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Configuration reloaded from file'
            })
        else:
            return jsonify({'error': 'Failed to reload configuration'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Failed to reload configuration: {str(e)}'}), 500

@audiobook_settings_bp.route('/api/audiobook-services/status', methods=['GET'])
@handle_errors
def get_audiobook_services_status():
    """Get status of all audiobook services"""
    try:
        from services.service_manager import service_manager
        status = service_manager.get_service_status()
        
        # Filter to audiobook-related services
        audiobook_services = {
            'indexers': {
                'indexer_manager': status.get('indexer_manager', False),
                'jackett': status.get('jackett', False),
            },
            'clients': {
                'client_manager': status.get('client_manager', False),
                'qbittorrent': status.get('qbittorrent', False),
            },
            'coordination': {
                'download_coordinator': status.get('download_coordinator', False),
                'download_selector': status.get('download_selector', False),
                'download_queue_manager': status.get('download_queue_manager', False)
            },
            'processing': {
                'file_processor': status.get('file_processor', False),
                'file_organizer': status.get('file_organizer', False),
                'file_validator': status.get('file_validator', False)
            }
        }
        
        return jsonify({
            'success': True,
            'services': audiobook_services,
            'all_services': status
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get services status: {str(e)}'}), 500
