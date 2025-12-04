"""
Settings Routes - AuralArchive

Powers the settings dashboard, tabbed AJAX views, and helper endpoints for
download clients, caching, indexing, and diagnostics.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import json
import os
import platform
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from flask import Blueprint, jsonify, render_template, request, send_file

from services.service_manager import (
    get_audiobookshelf_service,
    get_audible_service,
    get_automatic_download_service,
    get_config_service,
    get_database_service,
    get_download_management_service,
    get_file_naming_service,
    get_metadata_update_service,
)
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings")


def test_client_connection(client_key: str, client_config: dict) -> dict:
    """Test connection to a download client using backup's exact working method."""
    try:
        import requests
        
        if client_key == 'qbittorrent':
            # Get qBittorrent settings with same field names as backup
            host = client_config.get('qb_host', '172.19.0.1')
            port = client_config.get('qb_port', '8080')
            username = client_config.get('qb_username', 'peronabg')
            # Ensure password is treated as string and strip any quotes
            password = str(client_config.get('qb_password', '01181236')).strip('"\'')
            
            # Debug logging
            logger.info(f"qBittorrent config received: {client_config}")
            logger.info(f"Using host={host}, port={port}, username={username}, password={password}")
            
            base_url = f"http://{host}:{port}"

            # LazyLibrarian's exact method: Simple session with minimal configuration
            test_session = requests.Session()
            test_session.verify = False

            # Include headers to satisfy qBittorrent CSRF protection when enabled
            default_headers = {
                'Referer': f"{base_url}/",
                'Origin': base_url,
                'User-Agent': 'AuralArchive/SettingsTest'
            }
            test_session.headers.update(default_headers)

            # LazyLibrarian's login method - just the URL, data, no extra headers
            login_url = f"{base_url}/api/v2/auth/login"

            login_response = test_session.post(
                login_url,
                data={"username": username, "password": password},
                timeout=10,
                allow_redirects=False
            )
            
            if login_response.status_code in (301, 302, 303, 307, 308):
                # Some setups redirect after login; follow manually to capture cookies
                redirect_url = login_response.headers.get('Location')
                if redirect_url:
                    login_response = test_session.get(urljoin(base_url + '/', redirect_url), timeout=10)

            if login_response.status_code != 200:
                return {
                    'success': False,
                    'connected': False,
                    'message': f"Login failed with HTTP {login_response.status_code}",
                    'type': client_key
                }
            
            if login_response.text.strip() != "Ok.":
                return {
                    'success': False,
                    'connected': False,
                    'message': f"Login failed: {login_response.text.strip()}",
                    'type': client_key
                }
            
            # Now test getting version with authenticated session
            version_response = test_session.get(f"{base_url}/api/v2/app/version", timeout=10)
            
            if version_response.status_code == 200:
                version = version_response.text.strip('"')
                return {
                    'success': True,
                    'connected': True,
                    'message': f"qBittorrent connection successful (v{version})",
                    'type': client_key
                }
            else:
                return {
                    'success': False,
                    'connected': False,
                    'message': f"Failed to get version: HTTP {version_response.status_code}",
                    'type': client_key
                }
        
        else:
            return {
                'success': False,
                'connected': False,
                'message': f"Unsupported client type: {client_key}",
                'type': client_key
            }
            
    except requests.exceptions.ConnectionError as e:
        return {
            'success': False,
            'connected': False,
            'message': f"Cannot connect to qBittorrent server: {str(e)}",
            'type': client_key
        }
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'connected': False,
            'message': "Connection timeout",
            'type': client_key
        }
    except Exception as e:
        return {
            'success': False,
            'connected': False,
            'message': f"Connection error: {str(e)}",
            'type': client_key
        }


def _build_client_config_from_payload(client_key: str, payload: dict) -> dict:
    """Normalize client payload from UI into config-style dictionary."""
    normalized = {
        'enabled': payload.get('enabled', True),
        'auto_download': payload.get('auto_download', False)
    }

    if client_key == 'qbittorrent':
        raw_mappings = payload.get('path_mappings')
        mappings = []

        if isinstance(raw_mappings, list):
            for entry in raw_mappings:
                if not isinstance(entry, dict):
                    continue
                remote = str(entry.get('remote', '')).strip()
                local = str(entry.get('local', '')).strip()
                if remote or local:
                    mappings.append({'remote': remote, 'local': local})
        elif isinstance(raw_mappings, str) and raw_mappings.strip():
            # Legacy semicolon-delimited format
            for chunk in raw_mappings.split(';'):
                if '|' not in chunk:
                    continue
                remote, local = chunk.split('|', 1)
                remote = remote.strip()
                local = local.strip()
                if remote or local:
                    mappings.append({'remote': remote, 'local': local})

        normalized.update({
            'qb_host': payload.get('host') or payload.get('qb_host') or '127.0.0.1',
            'qb_port': int(payload.get('port', payload.get('qb_port', 8080)) or 8080),
            'qb_username': payload.get('username') or payload.get('qb_username') or '',
            'qb_password': payload.get('password') or payload.get('qb_password') or '',
            'category': payload.get('category') or payload.get('qb_category') or 'auralarchive'
        })

        for index, mapping in enumerate(mappings, start=1):
            normalized[f'path_mapping_{index}_qb_path'] = mapping.get('remote', '')
            normalized[f'path_mapping_{index}_host_path'] = mapping.get('local', '')
    elif client_key == 'deluge':
        normalized.update({
            'host': payload.get('host') or '127.0.0.1',
            'port': int(payload.get('port', 8112) or 8112),
            'password': payload.get('password') or ''
        })
    elif client_key == 'transmission':
        normalized.update({
            'transmission_host': payload.get('host') or '127.0.0.1',
            'transmission_port': int(payload.get('port', 9091) or 9091),
            'transmission_username': payload.get('username') or payload.get('transmission_username') or '',
            'transmission_password': payload.get('password') or payload.get('transmission_password') or ''
        })
    elif client_key == 'sabnzbd':
        normalized.update({
            'host': payload.get('host') or '127.0.0.1',
            'port': int(payload.get('port', 8080) or 8080),
            'username': payload.get('username') or '',
            'password': payload.get('password') or '',
            'api_key': payload.get('api_key') or ''
        })
    elif client_key == 'nzbget':
        normalized.update({
            'host': payload.get('host') or '127.0.0.1',
            'port': int(payload.get('port', 6789) or 6789),
            'username': payload.get('username') or '',
            'password': payload.get('password') or ''
        })

    return normalized


def _ensure_asin_in_path(preview_path: str, asin_value: str) -> str:
    """Append ASIN to the filename portion of a preview path if not already present."""
    if not preview_path or not asin_value:
        return preview_path

    if asin_value in preview_path:
        return preview_path

    root, ext = os.path.splitext(preview_path)
    ext = ext or ''
    return f"{root} [{asin_value}]{ext}"


# Import all individual route handlers
from routes.settings_tools.get_system_status import handle_get_system_status
from routes.settings_tools.get_system_resources import handle_get_system_resources
from routes.settings_tools.clear_cache import handle_clear_cache
from routes.settings_tools.restart_services import handle_restart_services
from routes.settings_tools.restart_individual_service import handle_restart_individual_service
# from routes.settings_tools.test_individual_service import handle_test_individual_service  # Missing module
from routes.settings_tools.get_services_status import handle_get_services_status
from routes.settings_tools.backup_database import handle_backup_database
from routes.settings_tools.optimize_database import handle_optimize_database
from routes.settings_tools.repair_database import handle_repair_database
from routes.settings_tools.get_config import handle_get_config
from routes.settings_tools.validate_config import handle_validate_configuration
# from routes.settings_tools.test_connection import handle_test_connection  # Missing module
# from routes.settings_tools.test_directories import handle_test_directories  # Missing module
from routes.settings_tools.download_logs import handle_download_logs

# Create the blueprint
settings_bp = Blueprint('settings', __name__)

# ============================================================================
# MAIN SETTINGS PAGE
# ============================================================================

@settings_bp.route('/')
def settings_page():
    """Display the modern professional settings page."""
    try:
        return render_template('settings.html',
                             title='Settings - AuralArchive')
    
    except Exception as e:
        logger.error(f"Error loading settings page: {e}")
        return render_template('settings.html',
                             title='Settings - AuralArchive')

# ============================================================================
# AJAX TAB CONTENT ROUTES
# ============================================================================

@settings_bp.route('/tabs/<tab_name>')
def get_tab_content(tab_name):
    """Serve individual tab content for AJAX loading."""
    try:
        # Validate tab name
        valid_tabs = ['system', 'database', 'audiobookshelf', 'download-clients', 'indexers', 'configuration', 'audible', 'search', 'media-management', 'download-management']
        if tab_name not in valid_tabs:
            logger.warning(f"Invalid tab requested: {tab_name}")
            return jsonify({'error': f'Invalid tab: {tab_name}'}), 404
        
        # Convert tab name for template (download-clients -> download_clients)
        template_name = tab_name.replace('-', '_')
        template_path = f'settings/{template_name}.html'
        
        logger.info(f"Loading tab content: {tab_name}")
        
        # Get tab data and pass it to the template
        tab_data = get_tab_data(tab_name)
        logger.debug(f"Tab data for {tab_name}: {tab_data}")
        logger.debug(f"Template path: {template_path}")
        return render_template(template_path, **tab_data)
        
    except Exception as e:
        logger.error(f"Error loading tab {tab_name}: {e}")
        logger.error(f"Detailed error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return render_tab_error(tab_name, str(e)), 500

def get_tab_data(tab_name):
    """Get data specific to each tab."""
    try:
        if tab_name == 'system':
            return get_system_tab_data()
        elif tab_name == 'database':
            return get_database_tab_data()
        elif tab_name == 'audiobookshelf':
            return get_audiobookshelf_tab_data()
        elif tab_name == 'download-clients':
            return {}  # Download clients removed
        elif tab_name == 'indexers':
            return {}  # Indexers tab - no server-side data needed
        elif tab_name == 'configuration':
            return get_configuration_tab_data()
        elif tab_name == 'media-management':
            return get_media_management_tab_data()
        elif tab_name == 'download-management':
            return get_download_management_tab_data()
        else:
            return {}
    except Exception as e:
        logger.error(f"Error getting data for tab {tab_name}: {e}")
        import traceback
        logger.error(f"Tab data error traceback: {traceback.format_exc()}")
        return {'error': str(e)}

def get_system_tab_data():
    """Collect system information for the system tab."""
    try:
        db_service = get_database_service()
        config_service = get_config_service()
        
        # Initialize defaults
        books = []
        authors = []
        config_data = {}
        
        # Get basic system info with fallbacks
        try:
            if db_service:
                books = db_service.get_all_books() or []
                authors = db_service.get_all_authors() or []
        except Exception as e:
            logger.warning(f"Could not get database info: {e}")
        
        try:
            if config_service:
                config_data = config_service.list_config() or {}
        except Exception as e:
            logger.warning(f"Could not get config info: {e}")
        
        # Calculate series count from books
        series_set = set()
        total_duration_seconds = 0
        duration_examples = []
        books_with_duration = 0
        
        # Process books for statistics
        for book in books:
            try:
                if book.get('Series'):
                    series_set.add(book['Series'])
                
                # Calculate total duration - handle various formats
                # Check Runtime field first (primary field), then Duration as fallback
                duration_str = book.get('Runtime', '') or book.get('Duration', '')
                
                # If still no value, try alternative field names
                if not duration_str:
                    for field_name in ['runtime', 'length', 'Length', 'time', 'Time']:
                        if book.get(field_name):
                            duration_str = str(book.get(field_name))
                            break
                
                if duration_str:
                    books_with_duration += 1
                    
                    # Collect examples for debugging (first 5 unique formats)
                    if duration_str not in [ex[0] for ex in duration_examples] and len(duration_examples) < 5:
                        duration_examples.append((duration_str, book.get('Title', 'Unknown')))
                    
                    # Try different duration formats
                    duration_seconds = 0
                    
                    if ':' in duration_str:
                        # Handle H:MM:SS or MM:SS formats
                        parts = duration_str.split(':')
                        try:
                            if len(parts) == 3:  # H:MM:SS format
                                hours, minutes, seconds = map(int, parts)
                                duration_seconds = hours * 3600 + minutes * 60 + seconds
                            elif len(parts) == 2:  # MM:SS format
                                minutes, seconds = map(int, parts)
                                duration_seconds = minutes * 60 + seconds
                        except ValueError:
                            logger.debug(f"Could not parse time format: {duration_str}")
                    elif 'h' in duration_str.lower() and 'm' in duration_str.lower():
                        # Handle "Xh Ym" format
                        import re
                        try:
                            hours_match = re.search(r'(\d+)h', duration_str.lower())
                            minutes_match = re.search(r'(\d+)m', duration_str.lower())
                            hours = int(hours_match.group(1)) if hours_match else 0
                            minutes = int(minutes_match.group(1)) if minutes_match else 0
                            duration_seconds = hours * 3600 + minutes * 60
                        except (ValueError, AttributeError):
                            logger.debug(f"Could not parse hour/minute format: {duration_str}")
                    elif 'min' in duration_str.lower():
                        # Handle "X minutes" format
                        import re
                        try:
                            minutes_match = re.search(r'(\d+(?:\.\d+)?)\s*min', duration_str.lower())
                            if minutes_match:
                                minutes = float(minutes_match.group(1))
                                duration_seconds = int(minutes * 60)
                        except (ValueError, AttributeError):
                            logger.debug(f"Could not parse minutes format: {duration_str}")
                    elif duration_str.replace('.', '').replace(',', '').isdigit():
                        # Handle pure number (assume seconds or minutes)
                        try:
                            duration_num = float(duration_str.replace(',', ''))
                            if duration_num > 86400:  # More than 24 hours, likely milliseconds
                                duration_seconds = int(duration_num / 1000)
                            elif duration_num > 1440:  # More than 24 minutes, likely seconds
                                duration_seconds = int(duration_num)
                            elif duration_num > 24:  # More than 24, likely minutes
                                duration_seconds = int(duration_num * 60)
                            else:  # Likely hours
                                duration_seconds = int(duration_num * 3600)
                        except ValueError:
                            logger.debug(f"Could not parse numeric format: {duration_str}")
                    
                    total_duration_seconds += duration_seconds
                    
            except Exception as e:
                logger.debug(f"Error processing book duration: {e}")
                pass  # Skip invalid duration formats
        
        # Log summary statistics only
        logger.debug(f"Duration processing complete: {books_with_duration}/{len(books)} books with duration data")
        
        # Convert total duration to human readable format
        total_hours = total_duration_seconds // 3600
        total_minutes = (total_duration_seconds % 3600) // 60
        
        if total_hours > 0:
            total_duration_str = f"{total_hours}h {total_minutes}m"
        elif total_minutes > 0:
            total_duration_str = f"{total_minutes}m"
        else:
            total_duration_str = "0h"
        
        logger.debug(f"System stats: {len(books)} books, {len(authors)} authors, {len(series_set)} series, {total_duration_str} total duration")
        
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
        
        # Get system resources (if available)
        try:
            import psutil
            system_resources = {
                'cpu_percent': psutil.cpu_percent(interval=0.1),  # Shorter interval for faster response
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': round((psutil.disk_usage('/').used / psutil.disk_usage('/').total) * 100, 2),
                'cpu_cores': psutil.cpu_count(),
                'memory_total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
                'disk_total_gb': round(psutil.disk_usage('/').total / (1024**3), 2)
            }
        except (ImportError, Exception) as e:
            logger.warning(f"Could not get system resources: {e}")
            system_resources = {
                'cpu_percent': 0,
                'memory_percent': 0,
                'disk_percent': 0,
                'cpu_cores': 1,
                'memory_total_gb': 0,
                'disk_total_gb': 0
            }
        
        # Get database size with fallback
        try:
            db_size = get_database_size()
        except Exception as e:
            logger.warning(f"Could not get database size: {e}")
            db_size = "Unknown"
        
        # Get services status with fallback
        try:
            services_status = get_all_services_status()
        except Exception as e:
            logger.warning(f"Could not get services status: {e}")
            services_status = {}
        
        return {
            'system_info': {
                'app_version': '1.0.0',
                'uptime': uptime_str,
                'database_books': len(books),
                'database_authors': len(authors),
                'database_series': len(series_set),
                'total_duration': total_duration_str,
                'database_size': db_size,
                'config_sections': len(config_data),
                'timestamp': datetime.now().isoformat()
            },
            'system_resources': system_resources,
            'services_status': services_status
        }
    
    except Exception as e:
        logger.error(f"Error collecting system tab data: {e}")
        return {
            'system_info': {'error': str(e)},
            'system_resources': {},
            'services_status': {}
        }

def get_database_tab_data():
    """Collect database information for the database tab."""
    try:
        db_service = get_database_service()
        
        # Get database statistics
        books = db_service.get_all_books()
        authors = db_service.get_all_authors()
        
        # Calculate additional statistics
        status_counts = {}
        for book in books:
            status = book.get('Status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'database_stats': {
                'total_books': len(books),
                'total_authors': len(authors),
                'database_size': get_database_size(),
                'status_counts': status_counts,
                'last_updated': datetime.now().isoformat()
            },
            'recent_books': sorted(books, key=lambda x: x.get('Created At', ''), reverse=True)[:10]
        }
    
    except Exception as e:
        logger.error(f"Error collecting database tab data: {e}")
        return {
            'database_stats': {'error': str(e)},
            'recent_books': []
        }

def get_audiobookshelf_tab_data():
    """Collect services information for the services tab."""
    try:
        services_status = get_all_services_status()
        
        # Get configuration data
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        # Get detailed service information
        service_details = {}
        
        # Database service details
        try:
            db_service = get_database_service()
            books = db_service.get_all_books()
            service_details['database'] = {
                'books_count': len(books),
                'connection_status': 'Connected',
                'last_check': datetime.now().isoformat()
            }
        except Exception as e:
            service_details['database'] = {'error': str(e)}
        
        # Audible service details
        try:
            audible_service = get_audible_service()
            test_results = audible_service.search_books('test', num_results=1)
            service_details['audible'] = {
                'test_results': len(test_results) if test_results else 0,
                'api_status': 'Working' if test_results else 'Failed',
                'last_check': datetime.now().isoformat()
            }
        except Exception as e:
            service_details['audible'] = {'error': str(e)}
        
        # AudioBookShelf service details
        try:
            abs_service = get_audiobookshelf_service()
            success, message = abs_service.test_connection()
            service_details['audiobookshelf'] = {
                'connection_status': 'Connected' if success else 'Disconnected',
                'message': message,
                'last_check': datetime.now().isoformat()
            }
        except Exception as e:
            service_details['audiobookshelf'] = {'error': str(e)}
        
        # Download service details
        try:
            # Simplified test results since test_connections() doesn't exist
            service_details['download'] = {
                'overall_status': 'disabled',  # download_service removed
                'providers': {},
                'clients': {},
                'last_check': datetime.now().isoformat()
            }
        except Exception as e:
            service_details['download'] = {'error': str(e)}
        
        # Metadata service details
        try:
            metadata_service = get_metadata_update_service()
            status = metadata_service.get_service_status()
            service_details['metadata_update'] = {
                'initialized': status.get('initialized', False),
                'status_info': status,
                'last_check': datetime.now().isoformat()
            }
        except Exception as e:
            service_details['metadata_update'] = {'error': str(e)}

        # Get AudioBookShelf configuration data
        try:
            abs_config = config_data.get('audiobookshelf', {})
            audiobookshelf_config = {
                'server_url': abs_config.get('abs_host', ''),
                'api_key': abs_config.get('abs_api_key', ''),
                'username': abs_config.get('abs_username', ''),
                'password': abs_config.get('abs_password', ''),
                'sync_enabled': abs_config.get('abs_enabled', 'false').lower() in ['true', '1'],
                'sync_interval_hours': abs_config.get('abs_sync_frequency', '30min'),
                'auto_match_books': abs_config.get('abs_sync_metadata', 'true').lower() in ['true', '1'],
                'import_progress': abs_config.get('abs_sync_only_owned', 'true').lower() in ['true', '1'],
                'import_ratings': abs_config.get('abs_auto_sync', 'false').lower() in ['true', '1'],
                'library_id': abs_config.get('abs_library_id', '')
            }
        except Exception as e:
            logger.error(f"Error processing AudioBookShelf config: {e}")
            audiobookshelf_config = {
                'server_url': '',
                'api_key': '',
                'username': '',
                'password': '',
                'sync_enabled': False,
                'sync_interval_hours': '30min',
                'auto_match_books': True,
                'import_progress': True,
                'import_ratings': False,
                'library_id': ''
            }
        
        # Get available libraries if connected
        try:
            abs_service = get_audiobookshelf_service()
            libraries = abs_service.get_libraries()
            if libraries:
                audiobookshelf_libraries = [
                    {
                        'id': lib.get('id', ''),
                        'name': lib.get('name', ''),
                        'mediaType': lib.get('mediaType', ''),
                        'provider': lib.get('provider', '')
                    }
                    for lib in libraries
                ]
            else:
                audiobookshelf_libraries = []
        except Exception as e:
            logger.debug(f"Could not fetch AudioBookShelf libraries: {e}")
            audiobookshelf_libraries = []
        
        return {
            'services_status': services_status,
            'service_details': service_details,
            'audiobookshelf_config': audiobookshelf_config,
            'audiobookshelf_libraries': audiobookshelf_libraries,
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error collecting services tab data: {e}")
        return {
            'services_status': {},
            'service_details': {},
            'audiobookshelf_config': {},
            'audiobookshelf_libraries': [],
            'last_updated': datetime.now().isoformat()
        }

    """Collect download clients information for the download clients tab."""
    try:
        config_service = get_config_service()
        
        # Get configuration from config.txt only
        config_data = config_service.list_config()
        
        # Extract download-related configuration from config.txt
        qbittorrent_config = config_data.get('qbittorrent', {})
        jackett_config = config_data.get('jackett', {})
        
        # Simple test results based on configuration in config.txt
        test_results = {
            'qbittorrent': 'configured' if qbittorrent_config.get('qb_host') and qbittorrent_config.get('enabled') else 'not_configured',
            'jackett': 'configured' if jackett_config.get('jackett_url') and jackett_config.get('enabled') else 'not_configured'
        }
        
        return {
            'download_test_results': test_results,
            'qbittorrent_config': {
                'qb_host': qbittorrent_config.get('qb_host', ''),
                'qb_port': qbittorrent_config.get('qb_port', '8080'),
                'qb_username': qbittorrent_config.get('qb_username', ''),
                'qb_configured': bool(qbittorrent_config.get('qb_host') and qbittorrent_config.get('qb_username')),
                'enabled': qbittorrent_config.get('enabled', False)
            },
            'jackett_config': {
                'jackett_url': jackett_config.get('jackett_url', ''),
                'jackett_api_key': jackett_config.get('jackett_api_key', ''),
                'jackett_configured': bool(jackett_config.get('jackett_url') and jackett_config.get('jackett_api_key')),
                'enabled': jackett_config.get('enabled', False)
            },
            'available_providers': ['qbittorrent', 'transmission', 'deluge', 'sabnzbd', 'nzbget'],
            'available_clients': ['qbittorrent', 'transmission', 'deluge', 'sabnzbd', 'nzbget'],
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error collecting download clients tab data: {e}")
        import traceback
        logger.error(f"Download clients error traceback: {traceback.format_exc()}")
        return {
            'download_test_results': {'error': str(e)},
            'qbittorrent_config': {},
            'jackett_config': {},
            'available_providers': [],
            'available_clients': [],
            'last_updated': datetime.now().isoformat()
        }

def get_configuration_tab_data():
    """Collect configuration information for the configuration tab."""
    try:
        config_service = get_config_service()
        
        # Get all configuration
        config_data = config_service.list_config()
        
        # Validate configuration
        try:
            validation_results = config_service.validate_config()
        except AttributeError:
            # If validate_config doesn't exist, create basic validation
            validation_results = {}
            for section_name, section_data in config_data.items():
                if isinstance(section_data, dict):
                    validation_results[section_name] = len(section_data) > 0
                else:
                    validation_results[section_name] = bool(section_data)
        
        # Calculate validation statistics
        total_sections = len(validation_results)
        valid_sections = sum(validation_results.values()) if validation_results else 0
        overall_valid = valid_sections == total_sections if total_sections > 0 else False
        
        # Organize configuration by category
        organized_config = {
            'directories': config_data.get('directories', {}),
            'audible': config_data.get('audible', {}),
            'qbittorrent': config_data.get('qbittorrent', {}),
            'jackett': config_data.get('jackett', {}),
            'audiobookshelf': config_data.get('audiobookshelf', {}),
            'application': {
                'theme': config_data.get('theme', 'dark'),
                'default_view': config_data.get('default_view', 'grid'),
                'items_per_page': config_data.get('items_per_page', 25)
            }
        }
        
        return {
            'config_data': organized_config,
            'validation_results': validation_results,
            'config_stats': {
                'total_sections': total_sections,
                'valid_sections': valid_sections,
                'overall_valid': overall_valid,
                'validation_percentage': round((valid_sections / total_sections) * 100, 1) if total_sections > 0 else 0
            },
            'raw_config': config_data,
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error collecting configuration tab data: {e}")
        return {
            'config_data': {},
            'validation_results': {},
            'config_stats': {'error': str(e)},
            'raw_config': {},
            'last_updated': datetime.now().isoformat()
        }

def get_media_management_tab_data():
    """Collect media management configuration for the media management tab."""
    try:
        config_service = get_config_service()
        
        # Use get_section() to read from config.txt
        abs_config = config_service.get_section('audiobookshelf')
        import_config = config_service.get_section('import')
        
        # Extract relevant settings with defaults
        return {
            'library_path': abs_config.get('library_path', '/mnt/audiobooks'),
            'naming_template': abs_config.get('naming_template', 'standard'),
            'verify_after_import': import_config.get('verify_after_import', True),
            'create_backup_on_error': import_config.get('create_backup_on_error', True),
            'delete_source_after_import': import_config.get('delete_source_after_import', False)
        }
    
    except Exception as e:
        logger.error(f"Error collecting media management tab data: {e}")
        return {
            'library_path': '/mnt/audiobooks',
            'naming_template': 'standard',
            'verify_after_import': True,
            'create_backup_on_error': True,
            'delete_source_after_import': False
        }

def get_download_management_tab_data():
    """Collect download management configuration for the download management tab."""
    
    def to_bool(val, default='false'):
        """Safely convert config value to boolean."""
        if isinstance(val, bool):
            return val
        if val is None:
            val = default
        return str(val).lower() == 'true'
    
    try:
        config_service = get_config_service()
        
        # Read from [download_management] section
        dm_config = config_service.get_section('download_management')
        
        # Extract relevant settings with defaults
        return {
            # Seeding
            'seeding_enabled': to_bool(dm_config.get('seeding_enabled'), 'true'),
            'keep_torrent_active': to_bool(dm_config.get('seeding_keep_torrent_after_import'), 'true'),
            'wait_for_seeding_completion': to_bool(dm_config.get('seeding_wait_for_client_completion'), 'true'),
            
            # Cleanup
            'delete_source_after_import': to_bool(dm_config.get('delete_source_after_import'), 'false'),
            'delete_temp_files': to_bool(dm_config.get('delete_temp_files_after_conversion'), 'true'),
            'retention_days': int(dm_config.get('failed_download_retention_days', '7')),
            
            # Paths
            'temp_download_path': dm_config.get('temp_download_path', '/tmp/auralarchive/downloads'),
            'temp_conversion_path': dm_config.get('temp_conversion_path', '/tmp/auralarchive/converting'),
            'temp_failed_path': dm_config.get('temp_failed_path', '/tmp/auralarchive/failed'),
            
            # Retry
            'retry_search_max': int(dm_config.get('retry_search_max', '3')),
            'retry_download_max': int(dm_config.get('retry_download_max', '2')),
            'retry_conversion_max': int(dm_config.get('retry_conversion_max', '1')),
            'retry_import_max': int(dm_config.get('retry_import_max', '2')),
            'retry_backoff_minutes': int(dm_config.get('retry_backoff_minutes', '30')),
            
            # Monitoring
            'monitoring_interval': int(dm_config.get('polling_interval_seconds', '2')),
            'auto_start_monitoring': to_bool(dm_config.get('monitor_auto_start'), 'true'),
            'monitor_seeding': to_bool(dm_config.get('monitor_seeding_downloads'), 'true'),
            
            # Queue
            'max_concurrent_downloads': int(dm_config.get('max_concurrent_downloads', '3')),
            'queue_priority_default': int(dm_config.get('default_priority', '5')),
            'auto_process_queue': to_bool(dm_config.get('auto_process_queue'), 'true')
        }
    
    except Exception as e:
        logger.error(f"Error collecting download management tab data: {e}")
        # Return defaults on error
        return {
            'seeding_enabled': True,
            'keep_torrent_active': True,
            'wait_for_seeding_completion': True,
            'delete_source_after_import': False,
            'delete_temp_files': True,
            'retention_days': 7,
            'temp_download_path': '/tmp/auralarchive/downloads',
            'temp_conversion_path': '/tmp/auralarchive/converting',
            'temp_failed_path': '/tmp/auralarchive/failed',
            'retry_search_max': 3,
            'retry_download_max': 2,
            'retry_conversion_max': 1,
            'retry_import_max': 2,
            'retry_backoff_minutes': 30,
            'monitoring_interval': 2,
            'auto_start_monitoring': True,
            'monitor_seeding': True,
            'max_concurrent_downloads': 3,
            'queue_priority_default': 5,
            'auto_process_queue': True
        }


def _get_sample_books_for_preview(limit: int = 3):
    """Return sample book metadata for naming template previews."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
    except Exception as exc:
        logger.debug(f"Unable to fetch books for preview: {exc}")
        books = []

    if not books:
        return [
            {
                'title': 'The Name of the Wind',
                'author': 'Patrick Rothfuss',
                'series': 'The Kingkiller Chronicle',
                'series_number': '1',
                'year': 2007,
                'narrator': 'Nick Podehl',
                'asin': 'B002UZMLXM',
                'ASIN': 'B002UZMLXM',
                'publisher': 'DAW Books',
                'RuntimeLengthMin': 27610
            },
            {
                'title': 'Project Hail Mary',
                'author': 'Andy Weir',
                'series': None,
                'series_number': None,
                'year': 2021,
                'narrator': 'Ray Porter',
                'asin': 'B08G9PRS1K',
                'ASIN': 'B08G9PRS1K',
                'publisher': 'Audible Studios',
                'RuntimeLengthMin': 16420
            },
            {
                'title': 'Rhythm of War',
                'author': 'Brandon Sanderson',
                'series': 'The Stormlight Archive',
                'series_number': '4',
                'year': 2020,
                'narrator': 'Michael Kramer, Kate Reading',
                'asin': 'B086WP794Z',
                'ASIN': 'B086WP794Z',
                'publisher': 'Tor Books',
                'RuntimeLengthMin': 57910
            }
        ][:limit]

    sample_books = []
    for book in books[:limit]:
        asin_value = book.get('asin') or book.get('ASIN')

        authors = (
            book.get('AuthorName')
            or book.get('author')
            or book.get('Author')
            or book.get('authors')
        )

        if isinstance(authors, list):
            author_name = authors[0] if authors else 'Unknown Author'
        else:
            author_name = authors or 'Unknown Author'

        sample_books.append({
            'title': book.get('Title', book.get('title', 'Unknown Title')),
            'author': author_name,
            'series': book.get('SeriesName', book.get('series')),
            'series_number': book.get('book_number'),
            'year': book.get('release_date'),
            'narrator': book.get('narrator_name'),
            'asin': asin_value,
            'ASIN': asin_value,
            'publisher': book.get('publisher_name', book.get('publisher')),
            'RuntimeLengthMin': book.get('runtime_length_min') or book.get('RuntimeLengthMin')
        })

    return sample_books

def render_tab_error(tab_name, error_message):
    """Render an error template for failed tab loads."""
    return f"""
    <div class="tab-error">
        <div class="error-icon">
            <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h3>Failed to Load {tab_name.replace('-', ' ').title()} Settings</h3>
        <p>Error: {error_message}</p>
        <button onclick="settingsManager.loadTab('{tab_name}')" class="btn btn-primary">
            <i class="fas fa-redo"></i> Retry
        </button>
    </div>
    """

# ============================================================================
# API ENDPOINTS FOR JAVASCRIPT TO FETCH DATA
# ============================================================================

@settings_bp.route('/api/system-data')
def get_system_data_api():
    """API endpoint for system tab to fetch data via JavaScript."""
    try:
        data = get_system_tab_data()
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error getting system data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/database-data')
def get_database_data_api():
    """API endpoint for database tab to fetch data via JavaScript."""
    try:
        data = get_database_tab_data()
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error getting database data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/audiobookshelf-data')
def get_audiobookshelf_data_api():
    """API endpoint for audiobookshelf tab to fetch data via JavaScript."""
    try:
        data = get_audiobookshelf_tab_data()
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error getting services data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/download-clients-data')
def get_download_clients_data():
    """API endpoint for download clients tab to fetch data via JavaScript."""
    try:
        return jsonify({
            'success': True,
            'data': {}  # Download clients removed
        })
    except Exception as e:
        logger.error(f"Error getting download clients data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# DOWNLOAD CLIENT MANAGEMENT API ROUTES
# ============================================================================

@settings_bp.route('/api/clients', methods=['GET'])
def get_clients():
    """Get all configured download clients"""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        clients = {}
        
                # Check qBittorrent
        qbittorrent_config = config_data.get('qbittorrent', {})
        if qbittorrent_config.get('qb_host') and qbittorrent_config.get('qb_username'):
            clients['qbittorrent'] = {
                'name': 'qBittorrent',
                'type': 'qbittorrent',
                'configured': True,
                'host': qbittorrent_config.get('qb_host', ''),
                'port': qbittorrent_config.get('qb_port', '8082'),
                'username': qbittorrent_config.get('qb_username', ''),
                'auto_download': config_service.get_config_bool('qbittorrent', 'auto_download', False)
            }
        
        # Check Deluge
        deluge_config = config_data.get('deluge', {})
        if deluge_config.get('host') and deluge_config.get('password'):
            clients['deluge'] = {
                'name': 'Deluge',
                'type': 'deluge',
                'configured': True,
                'host': deluge_config.get('host', ''),
                'port': deluge_config.get('port', '8112'),
                'username': '',  # Deluge doesn't use username
                'auto_download': config_service.get_config_bool('deluge', 'auto_download', False)
            }
        
        # Check Transmission
        transmission_config = config_data.get('transmission', {})
        if transmission_config.get('transmission_host') and transmission_config.get('transmission_username'):
            clients['transmission'] = {
                'name': 'Transmission',
                'type': 'transmission',
                'configured': True,
                'host': transmission_config.get('transmission_host', ''),
                'port': transmission_config.get('transmission_port', '9091'),
                'username': transmission_config.get('transmission_username', ''),
                'auto_download': config_service.get_config_bool('transmission', 'auto_download', False)
            }
        
        # Check rTorrent
        rtorrent_config = config_data.get('rtorrent', {})
        if rtorrent_config.get('rtorrent_host') and rtorrent_config.get('rtorrent_username'):
            clients['rtorrent'] = {
                'name': 'rTorrent',
                'type': 'rtorrent',
                'configured': True,
                'host': rtorrent_config.get('rtorrent_host', ''),
                'port': rtorrent_config.get('rtorrent_port', '5000'),
                'username': rtorrent_config.get('rtorrent_username', ''),
                'auto_download': config_service.get_config_bool('rtorrent', 'auto_download', False)
            }
        
        # Check SABnzbd
        sabnzbd_config = config_data.get('sabnzbd', {})
        if sabnzbd_config.get('host') and sabnzbd_config.get('username'):
            clients['sabnzbd'] = {
                'name': 'SABnzbd',
                'type': 'sabnzbd',
                'configured': True,
                'host': sabnzbd_config.get('host', ''),
                'port': sabnzbd_config.get('port', '8080'),
                'username': sabnzbd_config.get('username', ''),
                'auto_download': config_service.get_config_bool('sabnzbd', 'auto_download', False)
            }
        
        # Check NZBGet
        nzbget_config = config_data.get('nzbget', {})
        if nzbget_config.get('host') and nzbget_config.get('username'):
            clients['nzbget'] = {
                'name': 'NZBGet',
                'type': 'nzbget',
                'configured': True,
                'host': nzbget_config.get('host', ''),
                'port': nzbget_config.get('port', '6789'),
                'username': nzbget_config.get('username', ''),
                'auto_download': config_service.get_config_bool('nzbget', 'auto_download', False)
            }
        
        return jsonify({
            'success': True,
            'clients': clients
        })
        
    except Exception as e:
        logger.error(f"Error getting clients: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/clients/<client_key>/test', methods=['POST'])
def test_client(client_key):
    """Test a download client connection"""
    try:
        payload = request.get_json(silent=True) or {}
        config_service = get_config_service()

        if payload:
            client_config = _build_client_config_from_payload(client_key, payload)
        else:
            if not config_service:
                return jsonify({
                    'success': False,
                    'error': 'Config service not available'
                }), 500
            client_config = config_service.get_section(client_key)

        if not client_config or not client_config.get('enabled', True):
            return jsonify({
                'success': False,
                'test_result': {
                    'message': f'Client {client_key} not found or not enabled',
                    'status': 'not_configured'
                },
                'error': f'Client {client_key} not configured'
            }), 404

        test_result = test_client_connection(client_key, client_config)
        
        return jsonify({
            'success': True,
            'test_result': test_result,
            'message': f'{client_key.title()} connection test completed'
        })
        
    except Exception as e:
        logger.error(f"Error testing client {client_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/clients/test-all', methods=['POST'])
def test_all_clients():
    """Test all download clients"""
    try:
        config_service = get_config_service()
        
        if not config_service:
            return jsonify({
                'success': False,
                'error': 'Config service not available'
            }), 500
        
        # Test all enabled clients from config
        client_types = ['qbittorrent', 'transmission', 'deluge', 'sabnzbd', 'nzbget']
        test_results = {
            'overall_status': 'unknown',
            'providers': {},
            'clients': {}
        }
        
        working_count = 0
        total_count = 0
        
        for client_key in client_types:
            client_config = config_service.get_section(client_key)
            if client_config and client_config.get('enabled', False):
                total_count += 1
                test_result = test_client_connection(client_key, client_config)
                test_results['clients'][client_key] = test_result
                
                if test_result.get('success', False):
                    working_count += 1
        
        # Set overall status
        if total_count == 0:
            test_results['overall_status'] = 'no_clients'
        elif working_count == total_count:
            test_results['overall_status'] = 'all_working'
        elif working_count > 0:
            test_results['overall_status'] = 'partial'
        else:
            test_results['overall_status'] = 'none_working'
        
        return jsonify({
            'success': True,
            'test_results': test_results,
            'message': f"Client connection testing completed - {working_count}/{total_count} clients working"
        })
        
    except Exception as e:
        logger.error(f"Error testing all clients: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/clients/<client_key>', methods=['PUT'])
def update_client(client_key):
    """Update a download client configuration"""
    try:
        data = request.get_json() or {}

        # Valid client types
        valid_clients = ['qbittorrent', 'deluge', 'transmission', 'sabnzbd', 'nzbget']
        if client_key not in valid_clients:
            return jsonify({
                'success': False,
                'error': f'Invalid client: {client_key}'
            }), 400

        config_service = get_config_service()

        client_config = _build_client_config_from_payload(client_key, data)

        if not client_config:
            return jsonify({
                'success': False,
                'error': 'No configuration values supplied'
            }), 400

        if client_key == 'qbittorrent':
            config_parser = config_service.load_config()
            section_name = client_key.lower()

            preserved_values = {}
            if config_parser.has_section(section_name):
                for option, value in config_parser.items(section_name):
                    option_lower = option.lower()
                    if option_lower in {'download_path', 'download_path_remote', 'path_mappings'}:
                        continue
                    if option_lower.startswith('path_mapping_'):
                        continue
                    preserved_values[option_lower] = value

            config_parser.remove_section(section_name)
            config_parser.add_section(section_name)

            merged_values = {**preserved_values}
            for key, value in client_config.items():
                if isinstance(value, (list, dict)):
                    continue
                merged_values[key.lower()] = value

            for key, value in merged_values.items():
                if value is None:
                    continue
                config_parser.set(section_name, key, config_service._coerce_value(value))

            config_service._write_config(config_parser)
        else:
            if not config_service.update_section(client_key, client_config):
                return jsonify({
                    'success': False,
                    'error': 'Failed to update client configuration'
                }), 500

        logger.info(f"Updated {client_key} client configuration")
        
        return jsonify({
            'success': True,
            'message': f'{client_key.title()} configuration updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating client {client_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/clients/<client_key>/toggle', methods=['POST'])
def toggle_client(client_key):
    """Toggle a download client's auto_download setting"""
    try:
        # Valid client types
        valid_clients = ['qbittorrent', 'deluge', 'transmission', 'sabnzbd', 'nzbget']
        if client_key not in valid_clients:
            return jsonify({
                'success': False,
                'error': f'Invalid client: {client_key}'
            }), 400

        config_service = get_config_service()

        current_auto_download = config_service.get_config_bool(client_key, 'auto_download', False)
        new_auto_download = not current_auto_download

        logger.info("Toggling %s auto_download from %s to %s", client_key, current_auto_download, new_auto_download)

        if not config_service.update_config(client_key, 'auto_download', new_auto_download):
            return jsonify({
                'success': False,
                'error': f'Failed to toggle {client_key} auto-download setting'
            }), 500

        logger.info("Successfully toggled %s auto_download = %s", client_key, new_auto_download)
        
        return jsonify({
            'success': True,
            'message': f'Client {client_key} auto-download {"enabled" if new_auto_download else "disabled"}',
            'auto_download': new_auto_download
        })
        
    except Exception as e:
        logger.error(f"Error toggling client {client_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/clients/<client_key>', methods=['DELETE'])
def delete_client(client_key):
    """Delete a download client configuration"""
    try:
        # Valid client types
        valid_clients = ['qbittorrent', 'deluge', 'transmission', 'sabnzbd', 'nzbget']
        if client_key not in valid_clients:
            return jsonify({
                'success': False,
                'error': f'Invalid client: {client_key}'
            }), 400
        
        config_service = get_config_service()

        if config_service.remove_section(client_key):
            logger.info(f"Deleted {client_key} client configuration")
            return jsonify({
                'success': True,
                'message': f'{client_key.title()} client configuration deleted successfully'
            })

        return jsonify({
            'success': False,
            'error': f'Failed to delete {client_key} client configuration'
        }), 500
            
    except Exception as e:
        logger.error(f"Error deleting client {client_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/configuration-data')
def get_configuration_data_api():
    """API endpoint for configuration tab to fetch data via JavaScript."""
    try:
        data = get_configuration_tab_data()
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error getting configuration data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/tabs/refresh/<tab_name>')
def refresh_tab(tab_name):
    """Refresh a specific tab's data without full reload."""
    try:
        return get_tab_content(tab_name)
    except Exception as e:
        logger.error(f"Error refreshing tab {tab_name}: {e}")
        return jsonify({'error': f'Failed to refresh tab: {str(e)}'}), 500

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

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
    """Get status of all services with enhanced error handling."""
    services = {}
    
    # Test Audible Service
    try:
        audible_service = get_audible_service()
        if audible_service:
            results = audible_service.search_books('test', num_results=1)
            services['audible'] = 'Working' if results else 'Failed'
        else:
            services['audible'] = 'Not Available'
    except Exception as e:
        logger.debug(f"Audible service test failed: {e}")
        services['audible'] = 'Failed'
    
    # Test AudioBookShelf Service
    try:
        abs_service = get_audiobookshelf_service()
        if abs_service:
            success, message = abs_service.test_connection()
            services['audiobookshelf'] = 'Connected' if success else 'Disconnected'
        else:
            services['audiobookshelf'] = 'Not Available'
    except Exception as e:
        logger.debug(f"AudioBookShelf service test failed: {e}")
        services['audiobookshelf'] = 'Not Configured'
    
    # Test Download Service
    try:
        if False:  # download_service removed
            # Simplified since test_connections() doesn't exist
            services['download'] = 'Available'
        else:
            services['download'] = 'Not Available'
    except Exception as e:
        logger.debug(f"Download service test failed: {e}")
        services['download'] = 'Failed'
    
    # Test Metadata Service
    try:
        metadata_service = get_metadata_update_service()
        if metadata_service:
            status = metadata_service.get_service_status()
            services['metadata_update'] = 'Working' if status.get('initialized') else 'Failed'
        else:
            services['metadata_update'] = 'Not Available'
    except Exception as e:
        logger.debug(f"Metadata service test failed: {e}")
        services['metadata_update'] = 'Failed'
    
    # Test Database
    try:
        db_service = get_database_service()
        if db_service:
            books = db_service.get_all_books()
            services['database'] = 'Connected'
        else:
            services['database'] = 'Not Available'
    except Exception as e:
        logger.debug(f"Database service test failed: {e}")
        services['database'] = 'Failed'
    
    # Test Configuration
    try:
        config_service = get_config_service()
        if config_service:
            config_data = config_service.list_config()
            services['config'] = 'Loaded' if config_data else 'Failed'
        else:
            services['config'] = 'Not Available'
    except Exception as e:
        logger.debug(f"Config service test failed: {e}")
        services['config'] = 'Failed'
    
    return services

# ============================================================================
# EXISTING API ROUTE REGISTRATION (Keep all your existing functionality)
# ============================================================================

# System routes
settings_bp.add_url_rule('/system/status', 'get_system_status', handle_get_system_status, methods=['GET'])
settings_bp.add_url_rule('/system/resources', 'get_system_resources', handle_get_system_resources, methods=['GET'])
settings_bp.add_url_rule('/cache/clear', 'clear_cache', handle_clear_cache, methods=['POST'])

# Services routes
settings_bp.add_url_rule('/services/restart', 'restart_services', handle_restart_services, methods=['POST'])
settings_bp.add_url_rule('/services/restart/<service_name>', 'restart_individual_service', handle_restart_individual_service, methods=['POST'])
# settings_bp.add_url_rule('/services/test/<service_name>', 'test_individual_service', handle_test_individual_service, methods=['POST'])  # Missing function
settings_bp.add_url_rule('/services/status', 'get_services_status', handle_get_services_status, methods=['GET'])

# Database routes
settings_bp.add_url_rule('/database/backup', 'backup_database', handle_backup_database, methods=['POST'])
settings_bp.add_url_rule('/database/optimize', 'optimize_database', handle_optimize_database, methods=['POST'])
settings_bp.add_url_rule('/database/repair', 'repair_database', handle_repair_database, methods=['POST'])

# Configuration routes
settings_bp.add_url_rule('/config', 'get_config', handle_get_config, methods=['GET'])
settings_bp.add_url_rule('/config/validate', 'validate_config', handle_validate_configuration, methods=['GET'])


@settings_bp.route('/config/update', methods=['POST'])
def update_configuration_values():
    """Persist configuration updates received from the settings UI."""
    try:
        payload = request.get_json(silent=True) or {}

        updates_map = payload.get('updates')
        if not updates_map and 'section' in payload:
            updates_map = {
                str(payload.get('section')): payload.get('values', {})
            }

        if not updates_map or not isinstance(updates_map, dict):
            return jsonify({
                'success': False,
                'error': 'No configuration changes supplied'
            }), 400

        def _normalize(value):
            if isinstance(value, bool):
                return 'true' if value else 'false'
            if value is None:
                return ''
            if isinstance(value, (int, float)):
                return str(value)
            return str(value)

        flattened_updates = {}
        touched_sections = set()

        for section, values in updates_map.items():
            if not section or not isinstance(values, dict):
                continue

            section_name = str(section).strip().lower()
            if not section_name:
                continue

            for key, value in values.items():
                if key is None:
                    continue

                option_name = str(key).strip().lower()
                if not option_name:
                    continue

                config_key = f"{section_name}.{option_name}"
                flattened_updates[config_key] = _normalize(value)
                touched_sections.add(section_name)

        if not flattened_updates:
            return jsonify({
                'success': False,
                'error': 'No valid configuration keys supplied'
            }), 400

        config_service = get_config_service()
        success = config_service.update_multiple_config(flattened_updates)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to persist configuration changes'
            }), 500

        logger.info("Updated configuration sections: %s", ', '.join(sorted(touched_sections)))

        return jsonify({
            'success': True,
            'updated': len(flattened_updates),
            'sections': sorted(touched_sections)
        })

    except Exception as exc:
        logger.error(f"Error updating configuration: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500

# Testing routes
# settings_bp.add_url_rule('/test-connection', 'test_connection', handle_test_connection, methods=['POST'])  # Missing function
# settings_bp.add_url_rule('/test-directories', 'test_directories', handle_test_directories, methods=['POST'])  # Missing function

# Logs routes
settings_bp.add_url_rule('/logs/download', 'download_logs', handle_download_logs, methods=['GET'])

# ============================================================================
# PROVIDER MANAGEMENT API ROUTES
# ============================================================================

@settings_bp.route('/api/providers', methods=['GET'])
def get_providers():
    """Get all configured indexer providers"""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        
        providers = {}
        
        # Check Jackett
        jackett_config = config_data.get('jackett', {})
        if jackett_config.get('api_url') and jackett_config.get('api_key'):
            providers['jackett'] = {
                'name': 'Jackett',
                'type': 'jackett',
                'enabled': config_service.get_config_bool('jackett', 'enabled', False),
                'status': 'configured',
                'api_url': jackett_config.get('api_url', ''),
                'api_key': jackett_config.get('api_key', ''),
                'indexers': jackett_config.get('indexers', 'all')
            }
        
        # Check Prowlarr (if configured)
        prowlarr_config = config_data.get('prowlarr', {})
        if prowlarr_config.get('base_url') and prowlarr_config.get('api_key'):
            providers['prowlarr'] = {
                'name': 'Prowlarr',
                'type': 'prowlarr',
                'enabled': config_service.get_config_bool('prowlarr', 'enabled', False),
                'status': 'configured',
                'base_url': prowlarr_config.get('base_url', ''),
                'api_key': prowlarr_config.get('api_key', ''),
                'indexer_ids': prowlarr_config.get('indexer_ids', ''),
                'min_seeders': prowlarr_config.get('min_seeders', 1)
            }
        
        # Check NZBHydra2 (if configured)
        nzbhydra2_config = config_data.get('nzbhydra2', {})
        if nzbhydra2_config.get('base_url') and nzbhydra2_config.get('api_key'):
            providers['nzbhydra2'] = {
                'name': 'NZBHydra2',
                'type': 'nzbhydra2',
                'enabled': config_service.get_config_bool('nzbhydra2', 'enabled', False),
                'status': 'configured',
                'base_url': nzbhydra2_config.get('base_url', ''),
                'api_key': nzbhydra2_config.get('api_key', '')
            }
        
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

@settings_bp.route('/api/providers/<provider_key>/toggle', methods=['POST'])
def toggle_provider(provider_key):
    """Toggle a provider on/off"""
    try:
        # Valid provider types
        valid_providers = ['jackett', 'prowlarr', 'nzbhydra2']
        if provider_key not in valid_providers:
            return jsonify({
                'success': False,
                'error': f'Invalid provider: {provider_key}'
            }), 400

        config_service = get_config_service()

        current_enabled = config_service.get_config_bool(provider_key, 'enabled', False)
        new_enabled = not current_enabled

        logger.info("Toggling %s from %s to %s", provider_key, current_enabled, new_enabled)

        if not config_service.update_config(provider_key, 'enabled', new_enabled):
            return jsonify({
                'success': False,
                'error': f'Failed to toggle {provider_key} configuration'
            }), 500
        
        # Refresh the provider manager to pick up the configuration change
        try:
            if False:  # download_service removed
                # download_service removed
                logger.info(f"Provider manager refreshed after toggling {provider_key}")
        except Exception as e:
            logger.warning(f"Failed to refresh provider manager: {e}")

        logger.info(f"Successfully toggled {provider_key} enabled = {new_enabled}")

        return jsonify({
            'success': True,
            'message': f'Provider {provider_key} {"enabled" if new_enabled else "disabled"}',
            'enabled': new_enabled
        })
        
    except Exception as e:
        logger.error(f"Error toggling provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/providers/<provider_key>/test', methods=['POST'])
def test_provider(provider_key):
    """Test a provider connection"""
    try:
        provider_key = provider_key.lower()
        config_service = get_config_service()
        provider_config = config_service.get_section(provider_key)

        if not provider_config:
            return jsonify({
                'success': False,
                'error': f'Provider {provider_key} not configured'
            }), 404

        if provider_key == 'jackett':
            api_url = provider_config.get('api_url') or provider_config.get('jackett_url')
            api_key = provider_config.get('api_key') or provider_config.get('jackett_api_key')

            if not api_url or not api_key:
                return jsonify({
                    'success': False,
                    'error': 'Jackett API URL and API key are required'
                }), 400

            parsed = urlparse(api_url)
            query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query_params.update({'apikey': api_key, 't': 'indexers'})
            test_url = urlunparse(parsed._replace(query=urlencode(query_params)))

            try:
                response = requests.get(test_url, timeout=10)
                if response.status_code == 200:
                    return jsonify({
                        'success': True,
                        'message': 'Jackett connection successful'
                    })

                return jsonify({
                    'success': False,
                    'error': f'Jackett responded with HTTP {response.status_code}'
                }), 502

            except requests.exceptions.RequestException as req_error:
                return jsonify({
                    'success': False,
                    'error': f'Jackett request failed: {req_error}'
                }), 502

        elif provider_key in {'prowlarr', 'nzbhydra2'}:
            return jsonify({
                'success': False,
                'error': f'Testing for {provider_key.title()} is not implemented yet'
            }), 501

        return jsonify({
            'success': False,
            'error': f'Unknown provider: {provider_key}'
        }), 400

    except Exception as e:
        logger.error(f"Error testing provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/providers/test-all', methods=['POST'])
def test_all_providers():
    """Test all configured providers"""
    try:
        return jsonify({
            'success': True,
            'message': 'Test All functionality coming soon',
            'results': {},
            'summary': {
                'total': 0,
                'successful': 0,
                'failed': 0
            }
        })
        
    except Exception as e:
        logger.error(f"Error testing all providers: {e}")
        return jsonify({
            'success': False,
            'error': f'Error checking providers: {str(e)}'
        }), 500

@settings_bp.route('/api/providers/<provider_key>', methods=['PUT'])
def update_provider(provider_key):
    """Update provider configuration"""
    try:
        data = request.get_json() or {}
        
        # Valid provider types
        valid_providers = ['jackett', 'prowlarr', 'nzbhydra2']
        if provider_key not in valid_providers:
            return jsonify({
                'success': False,
                'error': f'Invalid provider: {provider_key}'
            }), 400
        
        # Get values from request
        api_url = data.get('api_url', '')
        api_key = data.get('api_key', '')
        indexers = data.get('indexers', 'all')
        enabled = data.get('enabled', False)
        
        if not api_url or not api_key:
            return jsonify({
                'success': False,
                'error': 'API URL and API Key are required'
            }), 400
        
        config_service = get_config_service()

        section_updates = {
            'enabled': enabled,
            'api_url': api_url,
            'api_key': api_key,
        }

        if provider_key == 'jackett':
            section_updates.update({
                'indexers': indexers,
                'jackett_url': api_url,  # Legacy field
                'jackett_api_key': api_key,  # Legacy field
            })
        elif provider_key == 'prowlarr':
            section_updates.update({
                'base_url': api_url,
                'indexer_ids': indexers,
                'min_seeders': 1,
            })
        elif provider_key == 'nzbhydra2':
            section_updates.update({'base_url': api_url})

        if not config_service.update_section(provider_key, section_updates):
            return jsonify({
                'success': False,
                'error': f'Failed to update {provider_key} configuration'
            }), 500

        # Refresh the provider manager to pick up the configuration changes
        try:
            if False:  # download_service removed
                # download_service removed
                logger.info(f"Provider manager refreshed after updating {provider_key}")
        except Exception as e:
            logger.warning(f"Failed to refresh provider manager: {e}")
        
        logger.info(f"Updated {provider_key} provider configuration")
        
        return jsonify({
            'success': True,
            'message': f'{provider_key.title()} configuration updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/providers', methods=['POST'])
def add_provider():
    """Add a new provider"""
    try:
        data = request.get_json() or {}
        provider_type = data.get('type')
        api_url = data.get('api_url', '')
        api_key = data.get('api_key', '')
        indexers = data.get('indexers', 'all')
        enabled = data.get('enabled', False)
        
        if not provider_type:
            return jsonify({
                'success': False,
                'error': 'Provider type is required'
            }), 400
        
        if not api_url or not api_key:
            return jsonify({
                'success': False,
                'error': 'API URL and API Key are required'
            }), 400
        
        # Valid provider types
        valid_providers = ['jackett', 'prowlarr', 'nzbhydra2']
        if provider_type not in valid_providers:
            return jsonify({
                'success': False,
                'error': f'Invalid provider type: {provider_type}'
            }), 400
        
        config_service = get_config_service()

        section_updates = {
            'enabled': enabled,
            'api_url': api_url,
            'api_key': api_key,
        }

        if provider_type == 'jackett':
            section_updates.update({
                'indexers': indexers,
                'jackett_url': api_url,  # Legacy field
                'jackett_api_key': api_key,  # Legacy field
            })
        elif provider_type == 'prowlarr':
            section_updates.update({
                'base_url': api_url,
                'indexer_ids': indexers,
                'min_seeders': 1,
            })
        elif provider_type == 'nzbhydra2':
            section_updates.update({'base_url': api_url})

        if not config_service.update_section(provider_type, section_updates):
            return jsonify({
                'success': False,
                'error': f'Failed to add {provider_type} configuration'
            }), 500

        # Refresh the provider manager to pick up the new configuration
        try:
            if False:  # download_service removed
                # download_service removed
                logger.info(f"Provider manager refreshed after adding {provider_type}")
        except Exception as e:
            logger.warning(f"Failed to refresh provider manager: {e}")
        
        logger.info(f"Added {provider_type} provider with URL: {api_url}")
        
        return jsonify({
            'success': True,
            'message': f'{provider_type.title()} provider added successfully',
            'provider': {
                'name': provider_type.title(),
                'type': provider_type,
                'enabled': enabled,
                'api_url': api_url,
                'status': 'configured'
            }
        })
        
    except Exception as e:
        logger.error(f"Error adding provider: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/api/providers/<provider_key>', methods=['DELETE'])
def delete_provider(provider_key):
    """Delete a provider (clear its configuration)"""
    try:
        config_service = get_config_service()
        
        # Valid provider types
        valid_providers = ['jackett', 'prowlarr', 'nzbhydra2']
        if provider_key not in valid_providers:
            return jsonify({
                'success': False,
                'error': f'Invalid provider: {provider_key}'
            }), 400
        
        if not config_service.remove_section(provider_key):
            return jsonify({
                'success': False,
                'error': f'Failed to delete provider {provider_key}'
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'{provider_key.title()} provider deleted'
        })
        
    except Exception as e:
        logger.error(f"Error deleting provider {provider_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# AUDIOBOOKSHELF SUPPORT ROUTES
# ============================================================================

@settings_bp.route('/audiobookshelf/test', methods=['POST'])
def test_audiobookshelf_connection():
    """Test connectivity to the configured AudioBookShelf instance."""
    try:
        config_service = get_config_service()
        abs_service = get_audiobookshelf_service()

        payload = request.get_json(silent=True) or {}
        host = (payload.get('host') or '').strip()
        api_key = (payload.get('api_key') or '').strip()

        if not host or not api_key:
            abs_config = config_service.get_section('audiobookshelf')
            host = host or abs_config.get('abs_host', '')
            api_key = api_key or abs_config.get('abs_api_key', '')

        if not host or not api_key:
            return jsonify({
                'success': False,
                'error': 'AudioBookShelf host and API key are required to test the connection.'
            }), 400

        success, message = abs_service.test_connection(host=host, api_key=api_key)

        return jsonify({
            'success': success,
            'message': message,
            'host': host
        }), (200 if success else 500)

    except Exception as exc:
        logger.error(f"Error testing AudioBookShelf connection: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500


@settings_bp.route('/audiobookshelf/libraries', methods=['GET'])
def list_audiobookshelf_libraries():
    """Return available libraries from AudioBookShelf."""
    try:
        config_service = get_config_service()
        abs_service = get_audiobookshelf_service()

        host = (request.args.get('host') or '').strip()
        api_key = (request.args.get('api_key') or '').strip()

        if not host or not api_key:
            abs_config = config_service.get_section('audiobookshelf')
            host = host or abs_config.get('abs_host', '')
            api_key = api_key or abs_config.get('abs_api_key', '')

        if not host or not api_key:
            return jsonify({
                'success': False,
                'error': 'AudioBookShelf host and API key are required to load libraries.'
            }), 400

        libraries = abs_service.get_libraries(host=host, api_key=api_key) or []
        normalized = [
            {
                'id': lib.get('id') or lib.get('_id'),
                'name': lib.get('name', 'Unnamed Library'),
                'media_type': lib.get('mediaType') or lib.get('media_type'),
                'provider': lib.get('provider')
            }
            for lib in libraries
            if lib
        ]

        return jsonify({
            'success': True,
            'libraries': normalized,
            'count': len(normalized)
        })

    except Exception as exc:
        logger.error(f"Error retrieving AudioBookShelf libraries: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500


@settings_bp.route('/audiobookshelf/manual-sync', methods=['POST'])
def trigger_audiobookshelf_sync():
    """Trigger a manual sync from AudioBookShelf into AuralArchive."""
    try:
        abs_service = get_audiobookshelf_service()
        result = abs_service.sync_from_audiobookshelf()

        status_code = 200 if result.get('success') else 500
        return jsonify(result), status_code

    except Exception as exc:
        logger.error(f"Error triggering AudioBookShelf sync: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500


@settings_bp.route('/audiobookshelf/naming-templates', methods=['GET'])
def get_audiobookshelf_naming_templates():
    """Return available naming templates with preview examples."""
    try:
        file_naming_service = get_file_naming_service()
        config_service = get_config_service()
        templates = file_naming_service.get_available_templates()
        sample_books = _get_sample_books_for_preview()

        base_path = '/mnt/audiobooks'
        if config_service:
            configured_path = config_service.get_config_value('audiobookshelf', 'library_path', fallback=base_path)
            if configured_path:
                base_path = configured_path

        template_payload = []
        for template_name in templates:
            example_entries = []
            for book in sample_books:
                try:
                    asin_value = book.get('asin') or book.get('ASIN')
                    preview_path = file_naming_service.generate_file_path(book, base_path, template_name, 'm4b')
                    preview_path = _ensure_asin_in_path(preview_path, asin_value)

                    example_entries.append({
                        'title': book.get('title'),
                        'author': book.get('author'),
                        'series': book.get('series'),
                        'preview': preview_path
                    })
                except Exception as preview_error:
                    logger.debug(f"Failed to build preview for template {template_name}: {preview_error}")
                    continue

            template_payload.append({
                'name': template_name,
                'label': template_name.replace('_', ' ').title(),
                'examples': example_entries
            })

        return jsonify({
            'success': True,
            'templates': template_payload
        })

    except Exception as exc:
        logger.error(f"Error loading naming templates: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500

# ============================================================================
# AUDIBLE CONFIGURATION ROUTES
# ============================================================================

@settings_bp.route('/config/audible', methods=['POST'])
def save_audible_config():
    """Save Audible configuration."""
    try:
        from flask import request
        config_service = get_config_service()
        audible_config = request.json
        
        # Security: Filter out credentials - they should NEVER be stored in config
        # Credentials are only used during authentication to generate a token
        forbidden_keys = ['username', 'password']
        
        # Prepare updates for the config service
        updates = {}
        for key, value in audible_config.items():
            if key not in forbidden_keys:
                updates[f'audible.{key}'] = value
            else:
                logger.warning(f"Blocked attempt to save credential '{key}' to config - use authentication modal instead")
        
        # Update configuration using the multiple update method
        success = config_service.update_multiple_config(updates)
        
        if success:
            logger.info("Audible configuration saved successfully (credentials excluded)")
            return jsonify({
                'success': True,
                'message': 'Audible configuration saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            }), 500
            
    except Exception as e:
        logger.error(f"Error saving Audible config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/test-audible-connection', methods=['POST'])
def test_audible_connection():
    """Test Audible connection."""
    try:
        from services.audible.audible_recommendations_service.audible_recommendations_service import get_audible_recommendations_service
        
        config_service = get_config_service()
        recommendations_service = get_audible_recommendations_service(config_service)
        
        success, message = recommendations_service.test_connection()
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error testing Audible connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/revoke-audible-auth', methods=['POST'])
def revoke_audible_auth():
    """Revoke Audible authentication."""
    try:
        import os
        
        # Remove the auth file
        auth_file = "auth/audible_auth.json"
        if os.path.exists(auth_file):
            os.remove(auth_file)
            logger.info("Audible authentication file removed")
        
        # Clear any cached authentication in the service
        from services.audible.audible_recommendations_service.audible_recommendations_service import get_audible_recommendations_service
        config_service = get_config_service()
        recommendations_service = get_audible_recommendations_service(config_service)
        recommendations_service.auth = None
        recommendations_service.clear_cache()
        
        return jsonify({
            'success': True,
            'message': 'Audible authentication revoked successfully'
        })
        
    except Exception as e:
        logger.error(f"Error revoking Audible auth: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# SEARCH MANAGEMENT API ENDPOINTS
# ============================================================================

@settings_bp.route('/api/search/status')
def get_search_status():
    """Get current search service status."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({
                'running': False,
                'queue_size': 0,
                'total_searches': 0,
                'last_search': 'Never',
                'error': 'Automatic search service not available'
            }), 503

        download_service = get_download_management_service()
        active_searches = len(download_service.queue_manager.get_queue(status_filter='SEARCHING'))

        status = service.get_status()
        metrics = status.get('metrics', {})

        last_search = status.get('last_run') or 'Never'

        return jsonify({
            'running': status.get('running', False),
            'paused': status.get('paused', False),
            'queue_size': status.get('queue_size', 0),
            'total_searches': metrics.get('total_books_queued', 0),
            'successful_searches': metrics.get('total_books_queued', 0),
            'auto_downloads': metrics.get('total_books_queued', 0),
            'failed_searches': 0,
            'books_found': metrics.get('total_books_queued', 0),
            'last_search': last_search,
            'active_searches': active_searches
        })
        
    except Exception as e:
        logger.error(f"Error getting search status: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/automatic/<action>', methods=['POST'])
def control_automatic_search(action):
    """Control automatic search service (start/pause/stop)."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        action = action.lower()
        if action == 'start':
            service.start()
        elif action == 'pause':
            service.pause()
        elif action == 'resume':
            service.resume()
        elif action == 'stop':
            service.stop()
        else:
            return jsonify({'error': f'Invalid action: {action}'}), 400

        return jsonify({
            'success': True,
            'message': f'Service {action} action processed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error {action}ing search service: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/config', methods=['GET', 'POST'])
def search_configuration():
    """Get or update search configuration."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        if request.method == 'GET':
            config_service = get_config_service()
            config = config_service.get_section('auto_search') or {}
            return jsonify(config)

        new_config = request.get_json()
        if not new_config:
            return jsonify({'error': 'No configuration data provided'}), 400

        success = service.update_configuration(new_config)
        return jsonify({
            'success': bool(success),
            'message': 'Configuration updated successfully' if success else 'Failed to update configuration'
        }), (200 if success else 500)
            
    except Exception as e:
        logger.error(f"Error handling search configuration: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/queue', methods=['GET', 'DELETE'])
def search_queue():
    """Get or clear search queue."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        if request.method == 'GET':
            queue = service.get_search_queue()
            return jsonify({'queue': queue, 'count': len(queue)})

        result = service.clear_queue()
        return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error handling search queue: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/queue/<item_id>', methods=['DELETE'])
def remove_from_queue(item_id):
    """Remove specific item from search queue."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        result = service.remove_from_queue(int(item_id))
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error removing item from queue: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/force-all', methods=['POST'])
def force_search_all():
    """Force search all items in queue."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        result = service.force_search_all()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error forcing search all: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/search/force/<item_id>', methods=['POST'])
def force_search_item(item_id):
    """Force search specific item."""
    try:
        service = get_automatic_download_service()
        if not service:
            return jsonify({'error': 'Automatic search service not available'}), 503

        result = service.force_search_book(int(item_id))
        if result.get('success'):
            return jsonify(result)
        return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error forcing search for item: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MEDIA MANAGEMENT API ROUTES
# ============================================================================

@settings_bp.route('/api/media-management', methods=['GET'])
def get_media_management_config():
    """Get current media management configuration."""
    try:
        config_service = get_config_service()
        
        # Use get_section() to read from config.txt
        abs_config = config_service.get_section('audiobookshelf')
        import_config = config_service.get_section('import')
        audible_config = config_service.get_section('audible')

        def coerce_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {'true', '1', 'yes', 'on'}:
                    return True
                if lowered in {'false', '0', 'no', 'off'}:
                    return False
            return bool(default)

        def coerce_int(value, default=1):
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(default)
        
        return jsonify({
            'success': True,
            'config': {
                'library_path': abs_config.get('library_path', '/mnt/audiobooks'),
                'naming_template': abs_config.get('naming_template', 'standard'),
                'import_directory': import_config.get('import_directory', '/downloads/import'),
                'verify_after_import': import_config.get('verify_after_import', True),
                'create_backup_on_error': import_config.get('create_backup_on_error', True),
                'delete_source_after_import': import_config.get('delete_source_after_import', False),
                'audible_downloads': {
                    'format': (audible_config.get('download_format') or 'aaxc') if audible_config else 'aaxc',
                    'quality': (audible_config.get('download_quality') or 'best') if audible_config else 'best',
                    'aax_fallback': coerce_bool(audible_config.get('aax_fallback_enabled'), True) if audible_config else True,
                    'save_voucher': coerce_bool(audible_config.get('save_voucher'), True) if audible_config else True,
                    'include_cover': coerce_bool(audible_config.get('include_cover'), False) if audible_config else False,
                    'include_chapters': coerce_bool(audible_config.get('include_chapters'), False) if audible_config else False,
                    'include_pdf': coerce_bool(audible_config.get('include_pdf'), False) if audible_config else False,
                    'concurrent_downloads': coerce_int(audible_config.get('concurrent_downloads'), 1) if audible_config else 1
                }
            }
        })
    except Exception as e:
        logger.error(f"Error getting media management config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@settings_bp.route('/api/media-management', methods=['POST'])
def save_media_management_config():
    """Save media management configuration."""
    try:
        from services.service_manager import get_file_naming_service
        config_service = get_config_service()
        file_naming_service = get_file_naming_service()
        
        data = request.get_json()
        
        # Validate template if custom
        template = data.get('naming_template', 'standard')
        if template == 'custom':
            custom_template = data.get('custom_template', '')
            if not custom_template:
                return jsonify({
                    'success': False,
                    'message': 'Custom template cannot be empty'
                }), 400
            
            # Validate custom template
            is_valid, errors = file_naming_service.validate_template(custom_template)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': 'Invalid custom template',
                    'errors': errors
                }), 400
            
            template = custom_template
        
        # Build updates dictionary using ConfigService's update_multiple_config method
        audible_payload = data.get('audible_downloads', {}) or {}

        def to_bool_str(value, default=False):
            return str(value if value is not None else default).lower()

        def to_int_str(value, default=1):
            try:
                return str(int(value))
            except (TypeError, ValueError):
                return str(default)

        updates = {
            # AudiobookShelf settings
            'audiobookshelf.library_path': data.get('library_path', '/mnt/audiobooks'),
            'audiobookshelf.naming_template': template,
            # Import settings
            'import.import_directory': data.get('import_directory', '/downloads/import'),
            'import.verify_after_import': to_bool_str(data.get('verify_after_import'), True),
            'import.create_backup_on_error': to_bool_str(data.get('create_backup_on_error'), True),
            'import.delete_source_after_import': to_bool_str(data.get('delete_source_after_import'), False),
            # Audible download defaults
            'audible.download_format': (audible_payload.get('format') or 'aaxc'),
            'audible.download_quality': (audible_payload.get('quality') or 'best'),
            'audible.aax_fallback_enabled': to_bool_str(audible_payload.get('aax_fallback'), True),
            'audible.save_voucher': to_bool_str(audible_payload.get('save_voucher'), True),
            'audible.include_cover': to_bool_str(audible_payload.get('include_cover'), False),
            'audible.include_chapters': to_bool_str(audible_payload.get('include_chapters'), False),
            'audible.include_pdf': to_bool_str(audible_payload.get('include_pdf'), False),
            'audible.concurrent_downloads': to_int_str(audible_payload.get('concurrent_downloads'), 1)
        }
        
        # Update configuration using the correct ConfigService API
        success = config_service.update_multiple_config(updates)
        
        if success:
            try:
                dm_service = get_download_management_service()
                if hasattr(dm_service, 'reload_configuration'):
                    dm_service.reload_configuration()
            except Exception as reload_exc:  # pragma: no cover - defensive logging only
                logger.warning(f"Failed to reload download management configuration: {reload_exc}")
            return jsonify({
                'success': True,
                'message': 'Media management settings saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            }), 500
        
    except Exception as e:
        logger.error(f"Error saving media management config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@settings_bp.route('/api/media-management/preview', methods=['POST'])
def preview_naming_template():
    """Generate preview examples for naming template."""
    try:
        from services.service_manager import get_file_naming_service
        file_naming_service = get_file_naming_service()

        data = request.get_json()
        template = data.get('template', 'standard')

        sample_books = _get_sample_books_for_preview()

        # Generate paths for each sample book
        examples = []
        for book in sample_books:
            try:
                # Use generate_filename to get just the filename/path pattern
                path = file_naming_service.generate_filename(book, template, 'm4b')
                examples.append({
                    'title': book['title'],
                    'author': book['author'],
                    'series': book.get('series'),
                    'path': path
                })
            except Exception as e:
                logger.warning(f"Error generating preview for {book['title']}: {e}")
                continue
        
        if not examples:
            return jsonify({
                'success': False,
                'message': 'Could not generate preview examples'
            }), 400
        
        return jsonify({
            'success': True,
            'examples': examples
        })
        
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@settings_bp.route('/api/media-management/validate-path', methods=['POST'])
def validate_library_path():
    """Validate library path exists and is writable."""
    try:
        import os
        
        data = request.get_json()
        path = data.get('path', '')
        
        if not path:
            return jsonify({
                'success': False,
                'valid': False,
                'message': 'Path cannot be empty'
            })
        
        # Check if path exists
        if not os.path.exists(path):
            return jsonify({
                'success': True,
                'valid': False,
                'message': f'Path does not exist: {path}'
            })
        
        # Check if it's a directory
        if not os.path.isdir(path):
            return jsonify({
                'success': True,
                'valid': False,
                'message': f'Path is not a directory: {path}'
            })
        
        # Check if writable
        if not os.access(path, os.W_OK):
            return jsonify({
                'success': True,
                'valid': False,
                'message': f'Path is not writable: {path}'
            })
        
        return jsonify({
            'success': True,
            'valid': True,
            'message': 'Path is valid and writable'
        })
        
    except Exception as e:
        logger.error(f"Error validating path: {e}")
        return jsonify({
            'success': False,
            'valid': False,
            'message': str(e)
        }), 500

@settings_bp.route('/api/media-management/reset', methods=['POST'])
def reset_media_management():
    """Reset media management settings to defaults."""
    try:
        config_service = get_config_service()
        
        # Build updates dictionary with default values
        updates = {
            # AudiobookShelf defaults (keeping existing connection settings)
            'audiobookshelf.library_path': '/mnt/audiobooks',
            'audiobookshelf.naming_template': 'standard',
            # Import defaults
            'import.import_directory': '/downloads/import',
            'import.verify_after_import': 'true',
            'import.create_backup_on_error': 'true',
            'import.delete_source_after_import': 'false',
            # Audible defaults
            'audible.download_format': 'aaxc',
            'audible.download_quality': 'best',
            'audible.aax_fallback_enabled': 'true',
            'audible.save_voucher': 'true',
            'audible.include_cover': 'false',
            'audible.include_chapters': 'false',
            'audible.include_pdf': 'false',
            'audible.concurrent_downloads': '1'
        }
        
        # Update configuration using the correct ConfigService API
        success = config_service.update_multiple_config(updates)
        
        if success:
            try:
                dm_service = get_download_management_service()
                if hasattr(dm_service, 'reload_configuration'):
                    dm_service.reload_configuration()
            except Exception as reload_exc:  # pragma: no cover - defensive logging only
                logger.warning(f"Failed to reload download management configuration after reset: {reload_exc}")
            return jsonify({
                'success': True,
                'message': 'Media management settings reset to defaults'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to reset configuration'
            }), 500
        
    except Exception as e:
        logger.error(f"Error resetting media management: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DOWNLOAD MANAGEMENT SETTINGS ROUTES
# ============================================================================

@settings_bp.route('/api/download-management', methods=['GET'])
def get_download_management_config():
    """Get current download management configuration."""
    try:
        config_service = get_config_service()
        
        # Read from [download_management] section
        dm_config = config_service.get_section('download_management')

        def get_bool(key: str, default: bool) -> bool:
            value = dm_config.get(key, default)
            if isinstance(value, bool):
                return value
            if value is None:
                return default
            return str(value).strip().lower() == 'true'

        def get_int(key: str, default: int) -> int:
            value = dm_config.get(key, default)
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def get_str(key: str, default: str) -> str:
            value = dm_config.get(key, default)
            if value is None:
                return default
            return str(value)

        return jsonify({
            'success': True,
            'config': {
                # Seeding
                'seeding_enabled': get_bool('seeding_enabled', True),
                'keep_torrent_active': get_bool('keep_torrent_active', True),
                'wait_for_seeding_completion': get_bool('wait_for_seeding_completion', True),

                # Cleanup
                'delete_source_after_import': get_bool('delete_source_after_import', False),
                'delete_temp_files': get_bool('delete_temp_files', True),
                'retention_days': get_int('retention_days', 7),

                # Paths
                'temp_download_path': get_str('temp_download_path', '/tmp/auralarchive/downloads'),
                'temp_conversion_path': get_str('temp_conversion_path', '/tmp/auralarchive/converting'),
                'temp_failed_path': get_str('temp_failed_path', '/tmp/auralarchive/failed'),

                # Retry
                'retry_search_max': get_int('retry_search_max', 3),
                'retry_download_max': get_int('retry_download_max', 2),
                'retry_conversion_max': get_int('retry_conversion_max', 1),
                'retry_import_max': get_int('retry_import_max', 2),
                'retry_backoff_minutes': get_int('retry_backoff_minutes', 30),

                # Monitoring
                'monitoring_interval': get_int('monitoring_interval', 2),
                'auto_start_monitoring': get_bool('auto_start_monitoring', True),
                'monitor_seeding': get_bool('monitor_seeding', True),

                # Queue
                'max_concurrent_downloads': get_int('max_concurrent_downloads', 3),
                'queue_priority_default': get_int('queue_priority_default', 5),
                'auto_process_queue': get_bool('auto_process_queue', True)
            }
        })
    except Exception as e:
        logger.error(f"Error getting download management config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/download-management', methods=['POST'])
def save_download_management_config():
    """Save download management configuration."""
    try:
        config_service = get_config_service()
        data = request.get_json()
        
        # Build updates dictionary
        updates = {
            # Seeding
            'download_management.seeding_enabled': str(data.get('seeding_enabled', True)).lower(),
            'download_management.keep_torrent_active': str(data.get('keep_torrent_active', True)).lower(),
            'download_management.wait_for_seeding_completion': str(data.get('wait_for_seeding_completion', True)).lower(),
            
            # Cleanup
            'download_management.delete_source_after_import': str(data.get('delete_source_after_import', False)).lower(),
            'download_management.delete_temp_files': str(data.get('delete_temp_files', True)).lower(),
            'download_management.retention_days': str(data.get('retention_days', 7)),
            
            # Paths
            'download_management.temp_download_path': data.get('temp_download_path', '/tmp/auralarchive/downloads'),
            'download_management.temp_conversion_path': data.get('temp_conversion_path', '/tmp/auralarchive/converting'),
            'download_management.temp_failed_path': data.get('temp_failed_path', '/tmp/auralarchive/failed'),
            
            # Retry
            'download_management.retry_search_max': str(data.get('retry_search_max', 3)),
            'download_management.retry_download_max': str(data.get('retry_download_max', 2)),
            'download_management.retry_conversion_max': str(data.get('retry_conversion_max', 1)),
            'download_management.retry_import_max': str(data.get('retry_import_max', 2)),
            'download_management.retry_backoff_minutes': str(data.get('retry_backoff_minutes', 30)),
            
            # Monitoring
            'download_management.monitoring_interval': str(data.get('monitoring_interval', 2)),
            'download_management.auto_start_monitoring': str(data.get('auto_start_monitoring', True)).lower(),
            'download_management.monitor_seeding': str(data.get('monitor_seeding', True)).lower(),
            
            # Queue
            'download_management.max_concurrent_downloads': str(data.get('max_concurrent_downloads', 3)),
            'download_management.queue_priority_default': str(data.get('queue_priority_default', 5)),
            'download_management.auto_process_queue': str(data.get('auto_process_queue', True)).lower()
        }
        
        # Update configuration
        success = config_service.update_multiple_config(updates)
        
        if success:
            try:
                dm_service = get_download_management_service()
                if hasattr(dm_service, 'reload_configuration'):
                    dm_service.reload_configuration()
            except Exception as reload_exc:  # pragma: no cover - defensive logging only
                logger.warning(f"Failed to reload download management configuration: {reload_exc}")

            return jsonify({
                'success': True,
                'message': 'Download management settings saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            }), 500
        
    except Exception as e:
        logger.error(f"Error saving download management config: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/download-management/status', methods=['GET'])
def get_download_management_status():
    """Get download management service status."""
    try:
        from services.service_manager import get_download_management_service
        dm_service = get_download_management_service()
        
        # Get service statistics
        queue_stats = dm_service.get_queue_statistics()
        
        return jsonify({
            'success': True,
            'status': {
                'monitoring_active': dm_service.monitoring_active,
                'queue_statistics': {
                    'total': queue_stats.get('total', 0),
                    'queued': queue_stats.get('queued', 0),
                    'active': queue_stats.get('downloading', 0) + queue_stats.get('converting', 0),
                    'completed': queue_stats.get('imported', 0),
                    'failed': queue_stats.get('failed', 0)
                }
            }
        })
    except Exception as e:
        logger.error(f"Error getting download management status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/download-management/test-paths', methods=['POST'])
def test_download_paths():
    """Validate download management paths."""
    try:
        import os
        data = request.get_json()
        
        paths = {
            'temp_download_path': data.get('temp_download_path'),
            'temp_conversion_path': data.get('temp_conversion_path'),
            'temp_failed_path': data.get('temp_failed_path')
        }
        
        results = {}
        for key, path in paths.items():
            if not path:
                results[key] = {'valid': False, 'message': 'Path is empty'}
                continue
            
            # Check if path exists or can be created
            try:
                if not os.path.exists(path):
                    os.makedirs(path, exist_ok=True)
                
                # Check if writable
                if os.access(path, os.W_OK):
                    results[key] = {'valid': True, 'message': 'Path is valid and writable'}
                else:
                    results[key] = {'valid': False, 'message': 'Path exists but is not writable'}
            except Exception as e:
                results[key] = {'valid': False, 'message': f'Cannot create/access path: {str(e)}'}
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        logger.error(f"Error testing paths: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/download-management/reset', methods=['POST'])
def reset_download_management_config():
    """Reset download management settings to defaults."""
    try:
        config_service = get_config_service()
        
        # Default values
        defaults = {
            'download_management.seeding_enabled': 'true',
            'download_management.keep_torrent_active': 'true',
            'download_management.wait_for_seeding_completion': 'true',
            'download_management.delete_source_after_import': 'false',
            'download_management.delete_temp_files': 'true',
            'download_management.retention_days': '7',
            'download_management.temp_download_path': '/tmp/auralarchive/downloads',
            'download_management.temp_conversion_path': '/tmp/auralarchive/converting',
            'download_management.temp_failed_path': '/tmp/auralarchive/failed',
            'download_management.retry_search_max': '3',
            'download_management.retry_download_max': '2',
            'download_management.retry_conversion_max': '1',
            'download_management.retry_import_max': '2',
            'download_management.retry_backoff_minutes': '30',
            'download_management.monitoring_interval': '2',
            'download_management.auto_start_monitoring': 'true',
            'download_management.monitor_seeding': 'true',
            'download_management.max_concurrent_downloads': '3',
            'download_management.queue_priority_default': '5',
            'download_management.auto_process_queue': 'true'
        }
        
        success = config_service.update_multiple_config(defaults)
        
        if success:
            try:
                dm_service = get_download_management_service()
                if hasattr(dm_service, 'reload_configuration'):
                    dm_service.reload_configuration()
            except Exception as reload_exc:  # pragma: no cover - defensive logging only
                logger.warning(f"Failed to reload download management configuration after reset: {reload_exc}")

            return jsonify({
                'success': True,
                'message': 'Download management settings reset to defaults'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to reset configuration'
            }), 500
        
    except Exception as e:
        logger.error(f"Error resetting download management: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


logger.info("Settings module initialized successfully with AJAX tab system")