"""
Settings API Routes - Modern Backend for Redesigned Settings Interface
======================================================================

Provides clean, organized API endpoints for the new settings UI with:
- Logical grouping of functionality
- Performance optimization
- Real-time monitoring capabilities
- Proper error handling
"""

from flask import Blueprint, jsonify, request, send_file, current_app
from collections import deque
from services.service_manager import (
    get_config_service,
    get_database_service,
    get_audiobookshelf_service,
    get_audible_service,
    get_metadata_update_service,
    service_manager
)
import os
import json
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import sqlite3

from utils.logger import get_module_logger

settings_api_bp = Blueprint('settings_api', __name__, url_prefix='/settings/api')
logger = get_module_logger("API.Settings")

# Global variables for log streaming
log_cache = []
last_log_check = datetime.now()
log_stream_state = {}

INITIAL_LOG_LINE_LIMIT = 80
MAX_LOG_RESPONSE_SIZE = 120


def _read_log_lines(log_file: str, state: dict, initial_limit: int = INITIAL_LOG_LINE_LIMIT):
    """Read new log lines, tailing on first read and streaming thereafter."""
    lines = []
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as log_handle:
        if not state.get('initialized'):
            lines = list(deque(log_handle, maxlen=initial_limit))
            state['position'] = log_handle.tell()
            state['initialized'] = True
        else:
            log_handle.seek(state.get('position', 0))
            lines = log_handle.readlines()
            state['position'] = log_handle.tell()
    return lines


def get_log_file_path() -> str:
    """Resolve the active log file path used by the application logger."""
    log_file_name = current_app.config.get('LOG_FILE', 'auralarchive_web.log')
    project_root = current_app.root_path

    # Primary location: project /logs directory (where setup_logger writes files)
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    preferred_path = os.path.join(logs_dir, log_file_name)
    if os.path.exists(preferred_path):
        return preferred_path

    # Fallback to project root for legacy setups
    fallback_path = os.path.join(project_root, log_file_name)
    if os.path.exists(fallback_path):
        return fallback_path

    # As a last resort, return preferred path so errors surface clearly
    return preferred_path

# ============================================================================
# OVERVIEW & DASHBOARD ENDPOINTS
# ============================================================================

@settings_api_bp.route('/overview')
def get_overview():
    """Get comprehensive system overview data."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        authors = db_service.get_all_authors()
        
        # Calculate total hours
        total_hours = 0
        for book in books:
            runtime = book.get('Runtime', '0 hrs 0 mins')
            try:
                if 'hrs' in runtime:
                    hours = int(runtime.split(' hrs')[0])
                    minutes = int(runtime.split(' hrs ')[1].split(' mins')[0]) if ' mins' in runtime else 0
                    total_hours += hours + (minutes / 60)
            except:
                pass
        
        # Get database size
        db_size = get_database_size()
        
        # Get system status
        system_status = get_quick_system_status()
        
        return jsonify({
            'success': True,
            'total_books': len(books),
            'total_authors': len(authors),
            'total_hours': int(total_hours),
            'database_size': f"{db_size:.1f} MB",
            'system_status': system_status
        })
    
    except Exception as e:
        logger.error(f"Error getting overview: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'total_books': 0,
            'total_authors': 0,
            'total_hours': 0,
            'database_size': '0 MB',
            'system_status': []
        })

def get_quick_system_status():
    """Get quick system status indicators."""
    status_items = []
    
    # Database status
    try:
        db_service = get_database_service()
        db_service.get_all_books()
        status_items.append({
            'name': 'Database',
            'description': 'SQLite database connection',
            'status': 'healthy'
        })
    except Exception:
        status_items.append({
            'name': 'Database',
            'description': 'SQLite database connection',
            'status': 'error'
        })
    
    # Service Manager status
    try:
        if service_manager.is_running():
            status_items.append({
                'name': 'Service Manager',
                'description': 'Core service coordination',
                'status': 'healthy'
            })
        else:
            status_items.append({
                'name': 'Service Manager',
                'description': 'Core service coordination',
                'status': 'warning'
            })
    except Exception:
        status_items.append({
            'name': 'Service Manager',
            'description': 'Core service coordination',
            'status': 'error'
        })
    
    # Disk space check
    try:
        disk_usage = psutil.disk_usage('/')
        free_percent = (disk_usage.free / disk_usage.total) * 100
        if free_percent > 20:
            disk_status = 'healthy'
        elif free_percent > 10:
            disk_status = 'warning'
        else:
            disk_status = 'error'
        
        status_items.append({
            'name': 'Disk Space',
            'description': f'{free_percent:.1f}% free',
            'status': disk_status
        })
    except Exception:
        status_items.append({
            'name': 'Disk Space',
            'description': 'Unable to check',
            'status': 'error'
        })
    
    return status_items

def get_database_size():
    """Get database file size in MB."""
    try:
        db_path = os.path.join(os.getcwd(), 'database', 'auralarchive_database.db')
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
            return size_bytes / (1024 * 1024)  # Convert to MB
    except Exception:
        pass
    return 0

# ============================================================================
# SYSTEM HEALTH & MONITORING ENDPOINTS
# ============================================================================

@settings_api_bp.route('/system-health')
def get_system_health():
    """Get detailed system health metrics."""
    try:
        # CPU and Memory metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Process information
        current_process = psutil.Process()
        process_memory = current_process.memory_info()
        
        health_data = {
            'cpu': {
                'usage_percent': cpu_percent,
                'status': 'healthy' if cpu_percent < 80 else 'warning' if cpu_percent < 95 else 'error'
            },
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'usage_percent': memory.percent,
                'status': 'healthy' if memory.percent < 80 else 'warning' if memory.percent < 90 else 'error'
            },
            'disk': {
                'total_gb': round(disk.total / (1024**3), 2),
                'used_gb': round(disk.used / (1024**3), 2),
                'usage_percent': round((disk.used / disk.total) * 100, 1),
                'status': 'healthy' if disk.used / disk.total < 0.8 else 'warning' if disk.used / disk.total < 0.9 else 'error'
            },
            'process': {
                'memory_mb': round(process_memory.rss / (1024**2), 2),
                'pid': current_process.pid,
                'threads': current_process.num_threads()
            }
        }
        
        return jsonify({
            'success': True,
            'health_data': health_data
        })
    
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# LIVE LOGS ENDPOINTS
# ============================================================================

@settings_api_bp.route('/logs/latest')
def get_latest_logs():
    """Get latest log entries for live streaming."""
    global last_log_check, log_cache
    
    try:
        # Read recent log entries from file
        log_file = get_log_file_path()
        new_logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Get last 50 lines for performance
                recent_lines = lines[-50:] if len(lines) > 50 else lines
                
                for line in recent_lines:
                    if line.strip():
                        # Parse log line
                        log_entry = parse_log_line(line.strip())
                        if log_entry:
                            new_logs.append(log_entry)
        
        # Update cache and return new logs
        log_cache.extend(new_logs)
        if len(log_cache) > 1000:  # Limit cache size
            log_cache = log_cache[-1000:]
        
        last_log_check = datetime.now()
        
        return jsonify({
            'success': True,
            'logs': new_logs[-20:] if len(new_logs) > 20 else new_logs  # Return last 20 for performance
        })
    
    except Exception as e:
        logger.error(f"Error getting latest logs: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'logs': []
        })

def parse_log_line(line):
    """Parse a log line into structured data."""
    try:
        # Basic log line parsing - adjust based on your log format
        if ' - ' in line:
            parts = line.split(' - ')
            if len(parts) >= 4:
                timestamp = parts[0].strip()
                logger_name = parts[1].strip()
                level = parts[2].strip()
                message = ' - '.join(parts[3:]).strip()

                return {
                    'timestamp': timestamp,
                    'source': logger_name,
                    'level': level.lower(),
                    'message': message
                }
            elif len(parts) >= 3:
                timestamp = parts[0].strip()
                level = parts[1].strip()
                message = ' - '.join(parts[2:]).strip()

                return {
                    'timestamp': timestamp,
                    'level': level.lower(),
                    'message': message
                }
    except Exception:
        pass
    
    # Return raw line if parsing fails
    return {
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'level': 'info',
        'message': line
    }

@settings_api_bp.route('/logs/download')
def download_logs():
    """Download log file."""
    try:
        log_file = get_log_file_path()
        if os.path.exists(log_file):
            return send_file(log_file, as_attachment=True, 
                           download_name=f'auralarchive_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        else:
            return jsonify({'error': 'Log file not found'}), 404
    
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# SERVICES MANAGEMENT ENDPOINTS
# ============================================================================

@settings_api_bp.route('/services-status')
def get_services_status():
    """Get status of all application services."""
    try:
        services = []
        
        # Database Service
        try:
            db_service = get_database_service()
            db_service.get_all_books()
            services.append({
                'id': 'database',
                'name': 'Database Service',
                'description': 'SQLite database operations',
                'status': 'healthy'
            })
        except Exception as e:
            services.append({
                'id': 'database',
                'name': 'Database Service',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })
        
        # Audible Service
        try:
            audible_service = get_audible_service()
            # Just check if service is available - Audible service doesn't require config
            if audible_service:
                services.append({
                    'id': 'audible',
                    'name': 'Audible Service',
                    'description': 'Audible API integration',
                    'status': 'healthy'
                })
            else:
                services.append({
                    'id': 'audible',
                    'name': 'Audible Service',
                    'description': 'Service not available',
                    'status': 'error'
                })
        except Exception as e:
            logger.error(f"Error getting audible service status: {e}")
            services.append({
                'id': 'audible',
                'name': 'Audible Service',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })
        
        # Download Service
        try:
            providers = None  # download_service removed.get_available_providers()
            clients = []
            
            if providers or clients:
                services.append({
                    'id': 'download',
                    'name': 'Download Service',
                    'description': f'{len(providers)} providers, {len(clients)} clients',
                    'status': 'healthy'
                })
            else:
                services.append({
                    'id': 'download',
                    'name': 'Download Service',
                    'description': 'No providers or clients configured',
                    'status': 'warning'
                })
        except Exception as e:
            services.append({
                'id': 'download',
                'name': 'Download Service',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })
        
        # AudioBookShelf Service
        try:
            abs_service = get_audiobookshelf_service()
            connection_success, message = abs_service.test_connection()
            services.append({
                'id': 'audiobookshelf',
                'name': 'AudioBookShelf',
                'description': message,
                'status': 'healthy' if connection_success else 'warning'
            })
        except Exception as e:
            services.append({
                'id': 'audiobookshelf',
                'name': 'AudioBookShelf',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })
        
        # Metadata Update Service
        try:
            metadata_service = get_metadata_update_service()
            # Safely check if service is initialized
            if metadata_service and hasattr(metadata_service, '_initialized'):
                services.append({
                    'id': 'metadata',
                    'name': 'Metadata Service',
                    'description': 'Book metadata updates',
                    'status': 'healthy' if metadata_service._initialized else 'warning'
                })
            else:
                services.append({
                    'id': 'metadata',
                    'name': 'Metadata Service',
                    'description': 'Service not fully initialized',
                    'status': 'warning'
                })
        except Exception as e:
            logger.error(f"Error getting metadata service status: {e}")
            services.append({
                'id': 'metadata',
                'name': 'Metadata Service',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })

        # Media Management Service
        try:
            if False:  # media_service removed
                # Check if service is running and configured
                if False:  # media_service removed
                    status_desc = f"Processing queue: {len([])} items"  # media_service removed
                    status = 'healthy'
                elif False:  # media_service removed
                    status_desc = "Service enabled but not running"
                    status = 'warning'
                else:
                    status_desc = "Service disabled in configuration"
                    status = 'warning'
                
                services.append({
                    'id': 'media_management',
                    'name': 'Media Management',
                    'description': status_desc,
                    'status': status
                })
            else:
                services.append({
                    'id': 'media_management',
                    'name': 'Media Management',
                    'description': 'Service not available',
                    'status': 'error'
                })
        except Exception as e:
            logger.error(f"Error getting media management service status: {e}")
            services.append({
                'id': 'media_management',
                'name': 'Media Management',
                'description': f'Error: {str(e)}',
                'status': 'error'
            })
        
        return jsonify({
            'success': True,
            'services': services
        })
    
    except Exception as e:
        logger.error(f"Error getting services status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'services': []
        })

@settings_api_bp.route('/media-management/scan-directories', methods=['POST'])
def scan_media_directories():
    """Manually scan directories for new files to process."""
    try:
        logger.warning("Media management service has been removed; scan request cannot be processed")
        return jsonify({
            'success': False,
            'error': 'Media management service not available',
            'message': 'Directory scanning is currently disabled because the media management service has been removed.'
        }), 503
        
    except Exception as e:
        logger.error(f"Error scanning directories: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/services/<service_id>/test', methods=['POST'])
def test_service(service_id):
    """Test a specific service."""
    try:
        if service_id == 'database':
            db_service = get_database_service()
            books = db_service.get_all_books()
            return jsonify({
                'success': True,
                'message': f'Database test successful. Found {len(books)} books.'
            })
        
        elif service_id == 'audible':
            audible_service = get_audible_service()
            if audible_service.is_configured():
                # Simple test - check if we can search
                results = audible_service.search_books('test', num_results=1)
                return jsonify({
                    'success': True,
                    'message': 'Audible service test successful.'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Audible service not configured.'
                })
        
        elif service_id == 'audiobookshelf':
            abs_service = get_audiobookshelf_service()
            success, message = abs_service.test_connection()
            return jsonify({
                'success': success,
                'message': message
            })
        
        else:
            return jsonify({
                'success': False,
                'message': f'Unknown service: {service_id}'
            }), 400
    
    except Exception as e:
        logger.error(f"Error testing service {service_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Service test failed: {str(e)}'
        })

@settings_api_bp.route('/services/<service_id>/restart', methods=['POST'])
def restart_service(service_id):
    """Restart a specific service."""
    try:
        # Implementation depends on your service architecture
        # For now, return a success message
        return jsonify({
            'success': True,
            'message': f'Service {service_id} restart requested. This feature is not yet fully implemented.'
        })
    
    except Exception as e:
        logger.error(f"Error restarting service {service_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Service restart failed: {str(e)}'
        })

# ============================================================================
# DATABASE MANAGEMENT ENDPOINTS
# ============================================================================

@settings_api_bp.route('/database/backup', methods=['POST'])
def backup_database():
    """Create database backup."""
    try:
        from routes.settings_tools.backup_database import handle_backup_database
        result = handle_backup_database()
        return result
    
    except Exception as e:
        logger.error(f"Error backing up database: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/database/optimize', methods=['POST'])
def optimize_database():
    """Optimize database."""
    try:
        from routes.settings_tools.optimize_database import handle_optimize_database
        result = handle_optimize_database()
        return result
    
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/database/repair', methods=['POST'])
def repair_database():
    """Repair database."""
    try:
        from routes.settings_tools.repair_database import handle_repair_database
        result = handle_repair_database()
        return result
    
    except Exception as e:
        logger.error(f"Error repairing database: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# CONFIGURATION ENDPOINTS
# ============================================================================

@settings_api_bp.route('/config/general')
def get_general_config():
    """Get general configuration settings."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Filter for general settings (non-sensitive)
        general_config = {}
        for key, value in config_data.items():
            if not any(sensitive in key.lower() for sensitive in ['password', 'token', 'secret', 'key']):
                general_config[key] = value
        
        return jsonify({
            'success': True,
            'config': general_config
        })
    
    except Exception as e:
        logger.error(f"Error getting general config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/config/media')
def get_media_config():
    """Get media management configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Extract media-related configuration
        media_config = {
            'rename_books': config_data.get('rename_books', True),
            'replace_illegal_chars': config_data.get('replace_illegal_chars', False),
            'book_format': config_data.get('book_format', '{Author Name} - {Book Title}'),
            'author_format': config_data.get('author_format', '{Author Name}'),
            'create_empty_folders': config_data.get('create_empty_folders', True),
            'delete_empty_folders': config_data.get('delete_empty_folders', False),
            'minimum_free_space': config_data.get('minimum_free_space', '100'),
            'free_space_unit': config_data.get('free_space_unit', 'MB'),
            'skip_free_space_check': config_data.get('skip_free_space_check', False),
            'use_hardlinks': config_data.get('use_hardlinks', False),
            'file_date': config_data.get('file_date', 'None')
        }
        
        return jsonify({
            'success': True,
            'config': media_config
        })
    
    except Exception as e:
        logger.error(f"Error getting media config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/config/metadata')
def get_metadata_config():
    """Get metadata configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Extract metadata-related configuration
        metadata_config = {
            'primary_source': config_data.get('primary_metadata_source', 'Audible'),
            'write_metadata': config_data.get('write_metadata', True),
            'scrape_additional': config_data.get('scrape_additional_metadata', True),
            'download_cover_art': config_data.get('download_cover_art', True),
            'cover_art_size': config_data.get('cover_art_size', '500x500'),
            'cover_art_format': config_data.get('cover_art_format', 'JPG')
        }
        
        return jsonify({
            'success': True,
            'config': metadata_config
        })
    
    except Exception as e:
        logger.error(f"Error getting metadata config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/config/system')
def get_system_config():
    """Get system configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Extract system-related configuration
        system_config = {
            'log_level': config_data.get('log_level', 'Info'),
            'enable_analytics': config_data.get('enable_analytics', False),
            'backup_folder': config_data.get('backup_folder', './backups'),
            'backup_interval': config_data.get('backup_interval', 'Daily'),
            'backup_retention': config_data.get('backup_retention', '7'),
            'update_branch': config_data.get('update_branch', 'Master'),
            'automatic_updates': config_data.get('automatic_updates', True)
        }
        
        return jsonify({
            'success': True,
            'config': system_config
        })
    
    except Exception as e:
        logger.error(f"Error getting system config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/download-clients')
def get_download_clients():
    """Get download clients configuration."""
    try:
        
        # Get available clients
        clients = []
        try:
            available_clients = []
            for client_id, client_info in available_clients.items():
                clients.append({
                    'id': client_id,
                    'name': client_info.get('name', client_id),
                    'type': client_info.get('type', 'Unknown'),
                    'status': client_info.get('status', 'unknown'),
                    'description': client_info.get('description', ''),
                    'host': client_info.get('host', '')
                })
        except Exception as e:
            logger.debug(f"Error getting download clients: {e}")
        
        # Get download handling configuration
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        download_config = {
            'enable_completed_handling': config_data.get('enable_completed_handling', True),
            'remove_completed': config_data.get('remove_completed_downloads', False),
            'check_interval': config_data.get('download_check_interval', '1')
        }
        
        return jsonify({
            'success': True,
            'clients': clients,
            'config': download_config
        })
    
    except Exception as e:
        logger.error(f"Error getting download clients: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'clients': [],
            'config': {}
        })

@settings_api_bp.route('/indexers')
def get_indexers():
    """Get indexers configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Extract indexer-related configuration
        indexer_config = {
            'minimum_seeders': config_data.get('minimum_seeders', '1'),
            'retention_days': config_data.get('retention_days', '0')
        }
        
        return jsonify({
            'success': True,
            'config': indexer_config
        })
    
    except Exception as e:
        logger.error(f"Error getting indexers config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/config/save', methods=['POST'])
def save_all_config():
    """Save all configuration settings."""
    try:
        from flask import request
        settings_data = request.json
        
        if not settings_data:
            return jsonify({
                'success': False,
                'error': 'No settings data provided'
            }), 400
        
        config_service = get_config_service()
        
        # Prepare updates for the config service
        updates = {}
        
        # Process each section
        for section_name, section_data in settings_data.items():
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    # Create config key
                    config_key = f'{section_name}.{key}' if section_name != 'general' else key
                    updates[config_key] = value
        
        # Update configuration using the multiple update method
        success = config_service.update_multiple_config(updates)
        
        if success:
            logger.info("All configuration saved successfully")
            return jsonify({
                'success': True,
                'message': 'Configuration saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            }), 500
            
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/system/check-updates', methods=['POST'])
def check_for_updates():
    """Check for application updates."""
    try:
        # This would implement actual update checking
        # For now, return a placeholder response
        return jsonify({
            'success': True,
            'updates_available': False,
            'current_version': '1.0.0',
            'latest_version': '1.0.0',
            'message': 'No updates available'
        })
    
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# PERFORMANCE MONITORING ENDPOINTS
# ============================================================================

@settings_api_bp.route('/performance/metrics')
def get_performance_metrics():
    """Get performance metrics over time."""
    try:
        # This would ideally be stored in a time-series database
        # For now, return current snapshot
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_gb': round(memory.used / (1024**3), 2),
            'memory_total_gb': round(memory.total / (1024**3), 2)
        }
        
        return jsonify({
            'success': True,
            'metrics': metrics
        })
    
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# CONNECTION TEST ENDPOINTS
# ============================================================================

@settings_api_bp.route('/test-audiobookshelf', methods=['POST'])
def test_audiobookshelf_connection():
    """Test connection to AudioBookShelf server."""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        token = data.get('token', '').strip()
        
        logger.info(f"Testing AudioBookShelf connection to: {url}")
        
        if not url or not token:
            logger.warning("AudioBookShelf test failed: Missing URL or token")
            return jsonify({
                'success': False,
                'error': 'URL and API token are required'
            })
        
        import requests
        
        # Test connection to AudioBookShelf API
        test_url = f"{url.rstrip('/')}/api/me"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Connecting to AudioBookShelf at: {test_url}")
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            user_data = response.json()
            logger.info(f"AudioBookShelf connection successful! User: {user_data.get('username', 'Unknown')}")
            
            # Also get server info
            server_url = f"{url.rstrip('/')}/api/status"
            server_response = requests.get(server_url, headers=headers, timeout=10)
            server_info = server_response.json() if server_response.status_code == 200 else {}
            
            return jsonify({
                'success': True,
                'user_info': user_data,
                'server_info': server_info,
                'message': 'Connection successful'
            })
        else:
            logger.warning(f"AudioBookShelf connection failed: HTTP {response.status_code}")
            return jsonify({
                'success': False,
                'error': f'HTTP {response.status_code}: {response.text[:200]}'
            })
            
    except requests.exceptions.Timeout:
        logger.warning("AudioBookShelf connection timeout")
        return jsonify({
            'success': False,
            'error': 'Connection timeout - server may be unreachable'
        })
    except requests.exceptions.ConnectionError:
        logger.warning("AudioBookShelf connection refused")
        return jsonify({
            'success': False,
            'error': 'Connection refused - check URL and server status'
        })
    except Exception as e:
        logger.error(f"Error testing AudioBookShelf connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/test-download-client', methods=['POST'])
def test_download_client():
    """Test connection to download client."""
    try:
        data = request.get_json()
        client_type = data.get('type', '').lower()
        host = data.get('host', 'localhost')
        port = data.get('port', 8080)
        username = data.get('username', '')
        password = data.get('password', '')
        
        logger.info(f"Testing {client_type} connection to: {host}:{port}")
        
        if client_type == 'qbittorrent':
            import requests
            
            # Test qBittorrent Web API
            login_url = f"http://{host}:{port}/api/v2/auth/login"
            login_data = {
                'username': username,
                'password': password
            }
            
            logger.info(f"Attempting qBittorrent login at: {login_url}")
            session = requests.Session()
            response = session.post(login_url, data=login_data, timeout=10)
            
            if response.status_code == 200 and 'Ok.' in response.text:
                logger.info("qBittorrent authentication successful")
                # Test API access
                version_url = f"http://{host}:{port}/api/v2/app/version"
                version_response = session.get(version_url, timeout=5)
                
                logger.info(f"qBittorrent version: {version_response.text}")
                return jsonify({
                    'success': True,
                    'message': f'qBittorrent connection successful (v{version_response.text})',
                    'version': version_response.text
                })
            else:
                logger.warning(f"qBittorrent authentication failed: {response.status_code} - {response.text}")
                return jsonify({
                    'success': False,
                    'error': 'Authentication failed - check username/password'
                })
        
        else:
            logger.warning(f"Testing for {client_type} not implemented yet")
            return jsonify({
                'success': False,
                'error': f'Testing for {client_type} not implemented yet'
            })
            
    except Exception as e:
        logger.error(f"Error testing download client: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# PROVIDER MANAGEMENT ENDPOINTS
# ============================================================================

@settings_api_bp.route('/providers')
def get_providers():
    """Get all configured providers."""
    try:
        config_service = get_config_service()
        
        # Get provider configurations
        config_data = config_service.list_config()
        providers = {}
        
        # Extract Jackett configuration
        jackett_config = config_data.get('jackett', {})
        if jackett_config.get('jackett_url'):
            providers['jackett'] = {
                'type': 'jackett',
                'name': 'Jackett',
                'enabled': jackett_config.get('enabled', True),
                'api_url': jackett_config.get('jackett_url', ''),
                'api_key': jackett_config.get('jackett_api_key', ''),
                'indexers': jackett_config.get('indexers', 'all'),
                'status': 'unknown'
            }
        
        # Check for other provider types in configuration
        for provider_type in ['prowlarr', 'nzbhydra2']:
            provider_config = config_data.get(provider_type, {})
            if provider_config and provider_config.get('base_url'):
                providers[provider_type] = {
                    'type': provider_type,
                    'name': provider_type.title(),
                    'enabled': provider_config.get('enabled', True),
                    'base_url': provider_config.get('base_url', ''),
                    'api_key': provider_config.get('api_key', ''),
                    'status': 'unknown'
                }
        
        # Test provider connections to get status
        for key, provider in providers.items():
            try:
                if False:  # download_service removed
                    success = False  # download_service removed(provider['type'], provider)
                    provider['status'] = 'connected' if success else 'error'
                else:
                    provider['status'] = 'unknown'
            except Exception as e:
                logger.debug(f"Error testing provider {key}: {e}")
                provider['status'] = 'error'
        
        return jsonify({
            'success': True,
            'providers': providers
        })
        
    except Exception as e:
        logger.error(f"Error getting providers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/providers', methods=['POST'])
def add_provider():
    """Add a new provider."""
    try:
        data = request.get_json()
        provider_type = data.get('type')
        
        if not provider_type:
            return jsonify({
                'success': False,
                'error': 'Provider type is required'
            }), 400
        
        # Generate a unique key for the provider
        provider_key = f"{provider_type}_1"
        
        # Create default configuration based on type
        if provider_type == 'jackett':
            provider_config = {
                'type': 'jackett',
                'name': 'Jackett',
                'enabled': False,
                'api_url': '',
                'api_key': '',
                'indexers': 'all'
            }
        elif provider_type == 'prowlarr':
            provider_config = {
                'type': 'prowlarr',
                'name': 'Prowlarr',
                'enabled': False,
                'base_url': '',
                'api_key': '',
                'indexer_ids': '',
                'min_seeders': 1
            }
        elif provider_type == 'nzbhydra2':
            provider_config = {
                'type': 'nzbhydra2',
                'name': 'NZBHydra2',
                'enabled': False,
                'base_url': '',
                'api_key': ''
            }
        else:
            return jsonify({
                'success': False,
                'error': f'Unknown provider type: {provider_type}'
            }), 400
        
        return jsonify({
            'success': True,
            'key': provider_key,
            'provider': provider_config
        })
        
    except Exception as e:
        logger.error(f"Error adding provider: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/providers/<provider_key>', methods=['PUT'])
def update_provider(provider_key):
    """Update a provider configuration."""
    try:
        config_service = get_config_service()
        data = request.get_json()
        
        # Determine provider type from key
        provider_type = provider_key.split('_')[0]
        
        # Update configuration
        updates = {}
        for key, value in data.items():
            updates[f'{provider_type}.{key}'] = value
        
        success = config_service.update_multiple_config(updates)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Provider configuration updated'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update configuration'
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/providers/<provider_key>/test', methods=['POST'])
def test_provider(provider_key):
    """Test a provider connection."""
    try:
        config_service = get_config_service()
        
        # Get provider configuration
        provider_type = provider_key.split('_')[0]
        config_data = config_service.list_config()
        provider_config = config_data.get(provider_type, {})
        
        if not provider_config:
            return jsonify({
                'success': False,
                'error': 'Provider not configured'
            }), 404
        
        # Test the connection based on provider type
        
        # Create a temporary config service class for provider testing
        class TempConfigService:
            def __init__(self, config_data):
                self.config_data = config_data
            
            def get_config_value(self, section, key, default=None):
                section_data = self.config_data.get(section, {})
                return section_data.get(key, default)
        
        if provider_type == 'jackett':
            # Jackett provider not available
            logger.warning("Jackett provider not available")
            return jsonify({
                'success': False,
                'error': 'Jackett provider not available'
            })
        elif provider_type == 'prowlarr':
            # Prowlarr provider not available
            logger.warning("Prowlarr provider not available")
            return jsonify({
                'success': False,
                'error': 'Prowlarr provider not available'
            })
        
        elif provider_type == 'nzbhydra2':
            # NZBHydra2 provider not available
            logger.warning("NZBHydra2 provider not available") 
            return jsonify({
                'success': False,
                'error': 'NZBHydra2 provider not available'
            })
        
        else:
            return jsonify({
                'success': False,
                'error': 'Connection test not implemented for this provider type'
            })
        
    except Exception as e:
        logger.error(f"Error testing provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/providers/<provider_key>/toggle', methods=['POST'])
def toggle_provider(provider_key):
    """Toggle a provider enabled/disabled."""
    try:
        config_service = get_config_service()
        data = request.get_json()
        enabled = data.get('enabled', False)
        
        # Determine provider type from key
        provider_type = provider_key.split('_')[0]
        
        # Update enabled status
        success = config_service.update_config(f'{provider_type}.enabled', enabled)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Provider {"enabled" if enabled else "disabled"}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update provider status'
            }), 500
            
    except Exception as e:
        logger.error(f"Error toggling provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_api_bp.route('/providers/<provider_key>', methods=['DELETE'])
def delete_provider(provider_key):
    """Delete a provider configuration."""
    try:
        config_service = get_config_service()
        
        # Determine provider type from key
        provider_type = provider_key.split('_')[0]
        
        # Remove all configuration for this provider type
        config_data = config_service.list_config()
        if provider_type in config_data:
            # Clear the entire section
            success = config_service.update_config(provider_type, {})
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Provider deleted'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to delete provider'
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': 'Provider not found'
            }), 404
            
    except Exception as e:
        logger.error(f"Error deleting provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

@settings_api_bp.route('/debug/jackett-test', methods=['POST'])
def debug_jackett_test():
    """Debug endpoint to test Jackett connection with detailed logging."""
    try:
        data = request.get_json()
        url = data.get('url', 'http://localhost:9117').rstrip('/')
        api_key = data.get('api_key', '')
        
        logger.info(f"DEBUG: Testing Jackett at {url} with API key {api_key[:8] if api_key else 'NONE'}...")
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key is required for testing'
            })
        
        import requests
        
        results = {
            'web_interface': None,
            'api_indexers': None,
            'api_search': None
        }
        
        # Test 1: Web interface
        try:
            logger.info(f"DEBUG: Testing web interface at {url}/UI/Dashboard")
            web_response = requests.get(f"{url}/UI/Dashboard", timeout=5)
            results['web_interface'] = {
                'status_code': web_response.status_code,
                'accessible': web_response.status_code == 200
            }
            logger.info(f"DEBUG: Web interface result: {results['web_interface']}")
        except Exception as e:
            results['web_interface'] = {
                'error': str(e),
                'accessible': False
            }
            logger.error(f"DEBUG: Web interface error: {e}")
        
        # Test 2: API indexers endpoint
        try:
            indexers_url = f"{url}/api/v2.0/indexers"
            params = {'apikey': api_key}
            logger.info(f"DEBUG: Testing API at {indexers_url} with params {params}")
            
            api_response = requests.get(indexers_url, params=params, timeout=10)
            results['api_indexers'] = {
                'status_code': api_response.status_code,
                'accessible': api_response.status_code == 200,
                'response_preview': api_response.text[:200] if api_response.text else 'No content'
            }
            
            if api_response.status_code == 200:
                try:
                    indexers = api_response.json()
                    results['api_indexers']['indexer_count'] = len(indexers) if isinstance(indexers, list) else 0
                    results['api_indexers']['indexers'] = [idx.get('id', 'unknown') for idx in indexers[:5]] if isinstance(indexers, list) else []
                except:
                    pass
            
            logger.info(f"DEBUG: API indexers result: {results['api_indexers']}")
            
        except Exception as e:
            results['api_indexers'] = {
                'error': str(e),
                'accessible': False
            }
            logger.error(f"DEBUG: API indexers error: {e}")
        
        # Test 3: API search endpoint (the one that was failing)
        try:
            search_url = f"{url}/api/v2.0/indexers/all/results"
            search_params = {'apikey': api_key, 'q': 'test', 't': 'search'}
            logger.info(f"DEBUG: Testing search at {search_url} with params {search_params}")
            
            search_response = requests.get(search_url, params=search_params, timeout=15)
            results['api_search'] = {
                'status_code': search_response.status_code,
                'accessible': search_response.status_code == 200,
                'response_preview': search_response.text[:200] if search_response.text else 'No content'
            }
            logger.info(f"DEBUG: API search result: {results['api_search']}")
            
        except Exception as e:
            results['api_search'] = {
                'error': str(e),
                'accessible': False
            }
            logger.error(f"DEBUG: API search error: {e}")
        
        # Determine overall success
        overall_success = results['web_interface'].get('accessible', False) and results['api_indexers'].get('accessible', False)
        
        return jsonify({
            'success': overall_success,
            'message': 'Debug test completed',
            'results': results,
            'recommendation': 'Use indexers endpoint for connection testing' if results['api_indexers'].get('accessible') else 'Check Jackett configuration'
        })
        
    except Exception as e:
        logger.error(f"DEBUG: Error in debug test: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================================================
# AUDIOBOOKSHELF SERVICE ENDPOINTS
# ============================================================================

@settings_api_bp.route('/audiobookshelf/config', methods=['GET'])
def get_audiobookshelf_config():
    """Get AudioBookShelf configuration."""
    try:
        config_service = get_config_service()
        abs_config = config_service.get_section('audiobookshelf') or {}
        
        return jsonify({
            'success': True,
            'config': abs_config
        })
        
    except Exception as e:
        logger.error(f"Error getting AudioBookShelf config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/audiobookshelf/config', methods=['POST'])
def save_audiobookshelf_config():
    """Save AudioBookShelf configuration."""
    try:
        config_service = get_config_service()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No configuration data provided'
            })
        
        # Update configuration using the specific AudioBookShelf method
        success = config_service.update_audiobookshelf_config(data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            })
        
        logger.info("AudioBookShelf configuration saved successfully")
        
        return jsonify({
            'success': True,
            'message': 'Configuration saved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error saving AudioBookShelf config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings_api_bp.route('/audiobookshelf/test', methods=['POST'])
def test_audiobookshelf():
    """Test AudioBookShelf connection."""
    try:
        abs_service = get_audiobookshelf_service()
        success, message = abs_service.test_connection()
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error testing AudioBookShelf connection: {e}")
        return jsonify({
            'success': False,
            'message': f'Connection test failed: {str(e)}'
        })

@settings_api_bp.route('/audiobookshelf/libraries', methods=['GET'])
def get_audiobookshelf_libraries():
    """Get AudioBookShelf libraries."""
    try:
        abs_service = get_audiobookshelf_service()
        libraries = abs_service.get_libraries()
        
        if libraries is not None:
            return jsonify({
                'success': True,
                'libraries': libraries
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve libraries',
                'libraries': []
            })
        
    except Exception as e:
        logger.error(f"Error getting AudioBookShelf libraries: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to get libraries: {str(e)}',
            'libraries': []
        })

@settings_api_bp.route('/audiobookshelf/sync', methods=['POST'])
def sync_from_audiobookshelf():
    """Sync books from AudioBookShelf to AuralArchive."""
    try:
        abs_service = get_audiobookshelf_service()
        
        result = abs_service.sync_from_audiobookshelf()
        
        return jsonify({
            'success': result.get('success', False),
            'synced_count': result.get('synced_count', 0),
            'message': result.get('message', 'Unknown error')
        })
        
    except Exception as e:
        logger.error(f"Error syncing from AudioBookShelf: {e}")
        return jsonify({
            'success': False,
            'synced_count': 0,
            'message': f'Sync failed: {str(e)}'
        })

# ============================================================================
# MEDIA MANAGEMENT ENDPOINTS
# ============================================================================

@settings_api_bp.route('/media-management', methods=['POST'])
def save_media_management_config():
    """Save media management configuration."""
    try:
        config_data = request.get_json()
        if not config_data:
            return jsonify({
                'success': False,
                'message': 'No configuration data provided'
            })

        config_service = get_config_service()
        
        # Save directories configuration
        if 'directories' in config_data:
            dirs = config_data['directories']
            if 'downloads_directory' in dirs:
                config_service.update_config('media_management', 'monitor_dirs', dirs['downloads_directory'])
            if 'target_directory' in dirs:
                config_service.update_config('media_management', 'target_dir', dirs['target_directory'])

        # Save organization configuration  
        if 'organization' in config_data:
            org = config_data['organization']
            if 'directory_template' in org:
                config_service.update_config('media_management', 'dir_template', org['directory_template'])
            if 'file_template' in org:
                config_service.update_config('media_management', 'file_template', org['file_template'])

        # Save processing configuration
        if 'processing' in config_data:
            proc = config_data['processing']
            if 'processing_mode' in proc:
                config_service.update_config('media_management', 'mode', proc['processing_mode'])
            if 'file_operation' in proc:
                config_service.update_config('media_management', 'file_operation', proc['file_operation'])
            if 'monitor_interval' in proc:
                config_service.update_config('media_management', 'monitor_interval', str(proc['monitor_interval']))
            if 'atomic_operations' in proc:
                config_service.update_config('media_management', 'atomic', 'true' if proc['atomic_operations'] else 'false')

        # Save AudioBookShelf configuration
        if 'audiobookshelf' in config_data:
            abs_config = config_data['audiobookshelf']
            if 'abs_integration' in abs_config:
                config_service.update_config('media_management', 'abs_enabled', 'true' if abs_config['abs_integration'] else 'false')
            if 'abs_library' in abs_config:
                config_service.update_config('media_management', 'abs_library', abs_config['abs_library'])
            if 'abs_auto_scan' in abs_config:
                config_service.update_config('media_management', 'abs_auto_scan', 'true' if abs_config['abs_auto_scan'] else 'false')
            if 'abs_auto_match' in abs_config:
                config_service.update_config('media_management', 'abs_auto_match', 'true' if abs_config['abs_auto_match'] else 'false')
            if 'abs_match_provider' in abs_config:
                config_service.update_config('media_management', 'abs_provider', abs_config['abs_match_provider'])
        
        return jsonify({
            'success': True,
            'message': 'Media management configuration saved successfully'
        })

    except Exception as e:
        logger.error(f"Error saving media management config: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to save configuration: {str(e)}'
        })

@settings_api_bp.route('/media-management/test', methods=['POST'])
def test_media_management_config():
    """Test media management configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Run various configuration tests
        tests = {}
        
        # Test downloads directory
        downloads_dir = config_data.get('media_management_monitor_dirs', '')
        if downloads_dir:
            tests['downloads_directory_exists'] = {
                'success': os.path.exists(downloads_dir),
                'message': f'Downloads directory: {downloads_dir}'
            }
            tests['downloads_directory_readable'] = {
                'success': os.access(downloads_dir, os.R_OK) if os.path.exists(downloads_dir) else False,
                'message': 'Downloads directory access permissions'
            }
        else:
            tests['downloads_directory_configured'] = {
                'success': False,
                'message': 'Downloads directory not configured'
            }
        
        # Test target directory
        target_dir = config_data.get('media_management_target_dir', '')
        if target_dir:
            tests['target_directory_exists'] = {
                'success': os.path.exists(target_dir),
                'message': f'Target directory: {target_dir}'
            }
            tests['target_directory_writable'] = {
                'success': os.access(target_dir, os.W_OK) if os.path.exists(target_dir) else False,
                'message': 'Target directory write permissions'
            }
        else:
            tests['target_directory_configured'] = {
                'success': False,
                'message': 'Target directory not configured'
            }
        
        # Test templates
        dir_template = config_data.get('media_management_dir_template', '')
        file_template = config_data.get('media_management_file_template', '')
        
        tests['templates_configured'] = {
            'success': bool(dir_template and file_template),
            'message': f'Directory: {dir_template}, File: {file_template}'
        }
        
        return jsonify({
            'success': True,
            'tests': tests
        })

    except Exception as e:
        logger.error(f"Error testing media management config: {e}")
        return jsonify({
            'success': False,
            'message': f'Configuration test failed: {str(e)}'
        })

@settings_api_bp.route('/media-management/config', methods=['GET'])
def get_media_management_config():
    """Get current media management configuration."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Extract media_management configuration from config.txt
        # config_data is structured as {'section': {'key': 'value'}}
        media_section = config_data.get('media_management', {})
        
        media_config = {
            'media_enabled': True,  # Default enabled
            'monitor_dirs': media_section.get('monitor_dirs', ''),
            'target_dir': media_section.get('target_dir', ''),
            'dir_template': media_section.get('dir_template', '{author}/{series}/{title}'),
            'file_template': media_section.get('file_template', '{title}'),
            'mode': media_section.get('mode', 'automatic'),
            'file_operation': media_section.get('file_operation', 'move'),
            'monitor_interval': media_section.get('monitor_interval', 1),
            'atomic': media_section.get('atomic', 'false').lower() == 'true',
            'abs_enabled': media_section.get('abs_enabled', 'true').lower() == 'true',
            'abs_library': media_section.get('abs_library', ''),
            'abs_auto_scan': media_section.get('abs_auto_scan', 'true').lower() == 'true',
            'abs_auto_match': media_section.get('abs_auto_match', 'true').lower() == 'true',
            'abs_provider': media_section.get('abs_provider', 'audible')
        }
        
        return jsonify({
            'success': True,
            'config': media_config
        })
        
    except Exception as e:
        logger.error(f"Error loading media management config: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to load configuration: {str(e)}'
        })

@settings_api_bp.route('/media-management/validate-directories', methods=['GET', 'POST'])
def validate_media_management_directories():
    """Validate media management directories."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Access the media_management section specifically
        media_section = config_data.get('media_management', {})
        downloads_dir = media_section.get('monitor_dirs', '')
        target_dir = media_section.get('target_dir', '')
        
        validation_results = {
            'downloads_directory': {
                'path': downloads_dir,
                'exists': os.path.exists(downloads_dir) if downloads_dir else False,
                'readable': os.access(downloads_dir, os.R_OK) if downloads_dir and os.path.exists(downloads_dir) else False,
                'writable': os.access(downloads_dir, os.W_OK) if downloads_dir and os.path.exists(downloads_dir) else False
            },
            'target_directory': {
                'path': target_dir,
                'exists': os.path.exists(target_dir) if target_dir else False,
                'readable': os.access(target_dir, os.R_OK) if target_dir and os.path.exists(target_dir) else False,
                'writable': os.access(target_dir, os.W_OK) if target_dir and os.path.exists(target_dir) else False
            }
        }
        
        # Count valid directories
        valid_count = sum(1 for result in validation_results.values() if result['exists'] and result['readable'])
        total_count = len([d for d in [downloads_dir, target_dir] if d])
        
        return jsonify({
            'success': True,
            'validation': validation_results,
            'valid_count': valid_count,
            'total_count': total_count,
            'message': f'{valid_count}/{total_count} directories are valid'
        })

    except Exception as e:
        logger.error(f"Error validating directories: {e}")
        return jsonify({
            'success': False,
            'message': f'Directory validation failed: {str(e)}'
        })

@settings_api_bp.route('/media-management/preview', methods=['POST'])
def preview_media_management_organization():
    """Preview how files would be organized with current templates."""
    try:
        data = request.get_json()
        directory_template = data.get('directory_template', '{author}/{title}')
        file_template = data.get('file_template', '{title} - {author}')
        
        # Generate example preview
        examples = [
            {
                'title': 'The Hobbit',
                'author': 'J.R.R. Tolkien',
                'series': 'Middle-earth',
                'organized_path': f"{directory_template.replace('{author}', 'J.R.R. Tolkien').replace('{title}', 'The Hobbit').replace('{series}', 'Middle-earth')}/{file_template.replace('{author}', 'J.R.R. Tolkien').replace('{title}', 'The Hobbit')}.m4b"
            },
            {
                'title': 'Dune',
                'author': 'Frank Herbert',
                'series': 'Dune Chronicles',
                'organized_path': f"{directory_template.replace('{author}', 'Frank Herbert').replace('{title}', 'Dune').replace('{series}', 'Dune Chronicles')}/{file_template.replace('{author}', 'Frank Herbert').replace('{title}', 'Dune')}.m4b"
            },
            {
                'title': 'Project Hail Mary',
                'author': 'Andy Weir',
                'series': 'Standalone',
                'organized_path': f"{directory_template.replace('{author}', 'Andy Weir').replace('{title}', 'Project Hail Mary').replace('{series}', 'Standalone')}/{file_template.replace('{author}', 'Andy Weir').replace('{title}', 'Project Hail Mary')}.m4b"
            }
        ]
        
        return jsonify({
            'success': True,
            'preview': {
                'directory_template': directory_template,
                'file_template': file_template,
                'examples': examples
            }
        })

    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return jsonify({
            'success': False,
            'message': f'Preview generation failed: {str(e)}'
        })

@settings_api_bp.route('/media-management/reset', methods=['POST'])
def reset_media_management_defaults():
    """Reset media management settings to defaults."""
    try:
        config_service = get_config_service()
        
        # Reset to default values
        defaults = {
            'enabled': 'false',
            'mode': 'manual',
            'log_level': 'INFO',
            'monitor_dirs': '/downloads/completed',
            'monitor_interval': '5',
            'monitor_clients': 'true',
            'file_operation': 'copy',
            'preserve_source': 'true',
            'atomic': 'true',
            'target_dir': '/audiobooks',
            'dir_template': '{author}/{series}/{title}',
            'file_template': '{title} - {author}',
            'abs_enabled': 'true',
            'abs_library': '',
            'abs_auto_scan': 'true',
            'abs_auto_match': 'true',
            'abs_provider': 'audible',
            'parse_series': 'true',
            'multi_author': 'first',
            'cleanup': 'true'
        }
        
        for key, value in defaults.items():
            config_service.update_config('media_management', key, value)
        
        return jsonify({
            'success': True,
            'message': 'Media management settings reset to defaults'
        })

    except Exception as e:
        logger.error(f"Error resetting media management defaults: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to reset settings: {str(e)}'
        })

@settings_api_bp.route('/media-management/queue-status', methods=['GET'])
def get_queue_status():
    """Get processing queue status."""
    try:
        # MediaManagementService not available - return empty queue
        return jsonify({
            'success': True,
            'queue': [],
            'total_items': 0,
            'pending_items': 0,
            'processing_items': 0
        })

    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to get queue status: {str(e)}'
        })

@settings_api_bp.route('/media-management/process-queue', methods=['POST'])
def process_queue():
    """Start processing the queue."""
    try:
        # MediaManagementService not available
        return jsonify({
            'success': False,
            'message': 'Media management service not available'
        })

    except Exception as e:
        logger.error(f"Error processing queue: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to start queue processing: {str(e)}'
        })

@settings_api_bp.route('/media-management/pause-queue', methods=['POST'])
def pause_queue():
    """Pause queue processing."""
    try:
        # This would integrate with the MediaManagementService
        return jsonify({
            'success': True,
            'message': 'Queue processing paused'
        })

    except Exception as e:
        logger.error(f"Error pausing queue: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to pause queue: {str(e)}'
        })

@settings_api_bp.route('/media-management/clear-queue', methods=['POST'])
def clear_queue():
    """Clear all items from the processing queue."""
    try:
        # MediaManagementService not available
        return jsonify({
            'success': True,
            'message': 'Queue cleared (service not available)',
            'cleared_count': 0
        })

    except Exception as e:
        logger.error(f"Error clearing queue: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to clear queue: {str(e)}'
        })

@settings_api_bp.route('/media-management/retry-item/<item_id>', methods=['POST'])
def retry_queue_item(item_id):
    """Retry a failed queue item."""
    try:
        # This would integrate with the MediaManagementService
        return jsonify({
            'success': True,
            'message': f'Item {item_id} queued for retry'
        })

    except Exception as e:
        logger.error(f"Error retrying queue item: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to retry item: {str(e)}'
        })

@settings_api_bp.route('/media-management/remove-item/<item_id>', methods=['DELETE'])
def remove_queue_item(item_id):
    """Remove an item from the processing queue."""
    try:
        # This would integrate with the MediaManagementService
        return jsonify({
            'success': True,
            'message': f'Item {item_id} removed from queue'
        })

    except Exception as e:
        logger.error(f"Error removing queue item: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to remove item: {str(e)}'
        })
