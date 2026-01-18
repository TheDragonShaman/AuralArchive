"""
Module Name: get_services_status.py
Author: TheDragonShaman
Created: July 31, 2025
Last Modified: December 23, 2025
Description:
    Settings helper summarizing metadata, download, ABS, and database service health.
Location:
    /routes/settings_tools/get_services_status.py

"""

from datetime import datetime

from flask import jsonify

from services.service_manager import (
    get_audiobookshelf_service,
    get_database_service,
    get_download_management_service,
    get_metadata_update_service,
)
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.ServicesStatus")

def handle_get_services_status():
    """Get detailed status of all services - FIXED."""
    try:
        services_status = {}
        download_service = get_download_management_service()
        
        # Get status from metadata update service
        try:
            metadata_service = get_metadata_update_service()
            services_status['metadata_update'] = metadata_service.get_service_status()
        except Exception as e:
            services_status['metadata_update'] = {'error': str(e), 'initialized': False}
        
        # Get status from download service
        try:
            services_status['download'] = download_service.get_system_status()
        except Exception as e:
            services_status['download'] = {'error': str(e), 'download_service': 'error'}
        
        # Get status from AudioBookShelf service
        try:
            abs_service = get_audiobookshelf_service()
            success, message = abs_service.test_connection()
            
            abs_status = {
                'connected': success,
                'message': message
            }
            
            # Try to get server info if connected
            if success:
                try:
                    server_success, server_info, server_message = abs_service.get_server_info()
                    if server_success:
                        abs_status['server_info'] = server_info
                except Exception as e:
                    abs_status['server_info_error'] = str(e)
            
            services_status['audiobookshelf'] = abs_status
            
        except Exception as e:
            services_status['audiobookshelf'] = {'error': str(e), 'connected': False}
        
        # Get status from database service
        try:
            db_service = get_database_service()
            books = db_service.get_all_books()
            
            db_status = {
                'connected': True,
                'books_count': len(books)
            }
            
            # Try to get additional database info if method exists
            if hasattr(db_service, 'get_database_info'):
                try:
                    db_status['info'] = db_service.get_database_info()
                except Exception as e:
                    db_status['info_error'] = str(e)
            
            services_status['database'] = db_status
            
        except Exception as e:
            services_status['database'] = {'error': str(e), 'connected': False}
        
        return jsonify({
            'success': True,
            'services': services_status,
            'check_time': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting services status: {e}")
        return jsonify({
            'success': False, 
            'error': f'Failed to get services status: {str(e)}'
        }), 500