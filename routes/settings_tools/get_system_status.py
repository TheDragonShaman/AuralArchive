"""
System Status Route - AuralArchive

Aggregates service health, configuration checks, and uptime information for the
settings dashboard.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
from datetime import datetime

from flask import jsonify

from services.service_manager import (
    get_audible_service,
    get_audiobookshelf_service,
    get_config_service,
    get_database_service,
    get_download_management_service,
    get_metadata_update_service,
)
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.SystemStatus")
_download_service = None


def _get_download_service():
    """Lazily fetch the download management service if available."""
    global _download_service
    if _download_service is None:
        try:
            _download_service = get_download_management_service()
        except Exception as exc:
            logger.warning(f"Download management service unavailable: {exc}")
            _download_service = False  # Cache failure to avoid repeated heavy init attempts
    return _download_service if _download_service not in (None, False) else None

def get_database_size():
    """Get database file size in human readable format."""
    try:
        db_service = get_database_service()
        if hasattr(db_service, 'db_file') and os.path.exists(db_service.db_file):
            size_bytes = os.path.getsize(db_service.db_file)
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{round(size_bytes / 1024, 2)} KB"
            else:
                return f"{round(size_bytes / (1024 * 1024), 2)} MB"
        else:
            return "Unknown"
    except Exception as e:
        logger.error(f"Error getting database size: {e}")
        return "Unknown"

def get_all_services_status():
    """Get status of all services using actual methods - FIXED."""
    services = {}
    
    # Test Audible Service
    try:
        audible_service = get_audible_service()
        results = audible_service.search_books('test', num_results=1)
        services['audible'] = 'Working' if results else 'Failed'
    except Exception as e:
        logger.warning(f"Audible service test failed: {e}")
        services['audible'] = 'Failed'
    
    # Test AudioBookShelf Service
    try:
        abs_service = get_audiobookshelf_service()
        success, message = abs_service.test_connection()
        services['audiobookshelf'] = 'Connected' if success else 'Disconnected'
    except Exception as e:
        logger.warning(f"AudioBookShelf service test failed: {e}")
        services['audiobookshelf'] = 'Not Configured'
    
    # Test Download Service
    download_service = _get_download_service()
    if download_service:
        try:
            test_results = download_service.test_connections()
            status = test_results.get('overall_status', 'unknown')
            services['download'] = status.title()
        except Exception as e:
            logger.warning(f"Download service test failed: {e}")
            services['download'] = 'Failed'
    else:
        services['download'] = 'Not Available'
    
    # Test Metadata Service
    try:
        metadata_service = get_metadata_update_service()
        status = metadata_service.get_service_status()
        services['metadata_update'] = 'Working' if status.get('initialized') else 'Failed'
    except Exception as e:
        logger.warning(f"Metadata service test failed: {e}")
        services['metadata_update'] = 'Failed'
    
    # Test Database
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        services['database'] = 'Connected'
    except Exception as e:
        logger.warning(f"Database service test failed: {e}")
        services['database'] = 'Failed'
    
    return services

def _check_directories_config(config_data):
    """Check if directory configuration is valid."""
    try:
        directories = config_data.get('directories', {})
        required_dirs = ['source_dir', 'import_dir', 'library_dir']
        
        for dir_key in required_dirs:
            dir_path = directories.get(dir_key)
            if not dir_path or not os.path.exists(dir_path):
                return False
        
        return True
    except Exception as e:
        logger.error(f"Error checking directories config: {e}")
        return False

def _check_qbittorrent_config(config_data):
    """Check if qBittorrent configuration is valid."""
    try:
        qb_config = config_data.get('qbittorrent', {})
        return bool(qb_config.get('qb_host') and qb_config.get('qb_username'))
    except Exception as e:
        logger.error(f"Error checking qBittorrent config: {e}")
        return False

def _check_jackett_config(config_data):
    """Check if Jackett configuration is valid."""
    try:
        jackett_config = config_data.get('jackett', {})
        return bool(jackett_config.get('jackett_url') and jackett_config.get('jackett_api_key'))
    except Exception as e:
        logger.error(f"Error checking Jackett config: {e}")
        return False

def _check_audiobookshelf_config(config_data):
    """Check if AudioBookShelf configuration is valid."""
    try:
        abs_config = config_data.get('audiobookshelf', {})
        return bool(abs_config.get('abs_host') and abs_config.get('abs_api_key'))
    except Exception as e:
        logger.error(f"Error checking AudioBookShelf config: {e}")
        return False

def _check_download_service_config():
    """Check if download service configuration is valid."""
    try:
        download_service = _get_download_service()
        if not download_service:
            return False
        providers = download_service.get_available_providers()
        clients = download_service.get_available_clients()
        return len(providers) > 0 or len(clients) > 0
    except Exception as e:
        logger.error(f"Error checking download service config: {e}")
        return False

def handle_get_system_status():
    """Get comprehensive system status for AuralArchive dashboard - FIXED."""
    try:
        db_service = get_database_service()
        config_service = get_config_service()
        
        # Get basic system info
        books = db_service.get_all_books()
        config_data = config_service.list_config()
        
        # Get system uptime (if available)
        try:
            import psutil
            boot_time = psutil.boot_time()
            uptime_seconds = datetime.now().timestamp() - boot_time
            uptime_hours = int(uptime_seconds // 3600)
            uptime_minutes = int((uptime_seconds % 3600) // 60)
            uptime_str = f"{uptime_hours}h {uptime_minutes}m"
        except ImportError:
            uptime_str = "Unknown"
        
        system_status = {
            'application': {
                'status': 'Running',
                'version': '1.0.0',
                'database_books': len(books),
                'database_size': get_database_size(),
                'config_sections': len(config_data),
                'uptime': uptime_str
            },
            'services': get_all_services_status(),
            'configuration': {
                'directories_configured': _check_directories_config(config_data),
                'audible_configured': True,  # Always available
                'qbittorrent_configured': _check_qbittorrent_config(config_data),
                'jackett_configured': _check_jackett_config(config_data),
                'audiobookshelf_configured': _check_audiobookshelf_config(config_data),
                'download_service_configured': _check_download_service_config()
            },
            'health': {
                'overall': 'healthy',  # Will be calculated
                'database_healthy': True,
                'services_healthy': True,
                'config_valid': True
            }
        }
        
        # Calculate overall health
        try:
            # Check service health
            healthy_services = [
                status in ['Working', 'Connected'] 
                for status in system_status['services'].values()
            ]
            services_healthy = sum(healthy_services) > 0
            
            # Check configuration health
            config_healthy = sum(system_status['configuration'].values()) > 0
            
            # Update health status
            system_status['health']['services_healthy'] = services_healthy
            system_status['health']['config_valid'] = config_healthy
            
            # Calculate overall health
            if services_healthy and config_healthy and system_status['health']['database_healthy']:
                system_status['health']['overall'] = 'healthy'
            elif services_healthy or config_healthy:
                system_status['health']['overall'] = 'warning'
            else:
                system_status['health']['overall'] = 'error'
                
        except Exception as e:
            logger.warning(f"Error calculating system health: {e}")
            system_status['health']['overall'] = 'warning'
        
        return jsonify({
            'success': True, 
            'status': system_status,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to get system status: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500