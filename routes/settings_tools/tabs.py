"""
Settings Tabs Routes - AuralArchive

Serves AJAX-powered tab content for the settings UI, including system status,
configuration, and integrations.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, render_template

from services.service_manager import (
    get_audible_service,
    get_audiobookshelf_service,
    get_config_service,
    get_database_service,
    get_metadata_update_service,
)
from utils.logger import get_module_logger

# Create blueprint for tab routes
tabs_bp = Blueprint('tabs', __name__)
logger = get_module_logger("Route.Settings.Tabs")

# ============================================================================
# TAB CONTENT ROUTES
# ============================================================================

@tabs_bp.route('/services')
def services_tab():
    """Serve services tab content with service status information."""
    logger.debug("Services tab route requested")
    try:
        return "<div>Test services tab - working</div>"
    except Exception as exc:
        logger.error("Error rendering services tab: %s", exc)
        return "<div>Error in services tab</div>"

@tabs_bp.route('/audiobookshelf')
def audiobookshelf_tab():
    """Serve audiobookshelf tab content with sync configuration."""
    try:
        audiobookshelf_data = get_audiobookshelf_tab_data()
        return render_template('settings/audiobookshelf.html', **audiobookshelf_data)
    
    except Exception as e:
        logger.error(f"Error loading audiobookshelf tab: {e}")
        return render_template('settings/error.html',
                             error="Failed to load audiobookshelf information",
                             tab_name="AudioBookShelf")

@tabs_bp.route('/audible')
def audible_tab():
    """Serve audible tab content with audible integration configuration."""
    try:
        audible_data = get_audible_tab_data()
        return render_template('settings/audible.html', **audible_data)
    
    except Exception as e:
        logger.error(f"Error loading audible tab: {e}")
        return render_template('settings/error.html',
                             error="Failed to load audible information",
                             tab_name="Audible")

@tabs_bp.route('/download-clients')
def download_clients_tab():
    """Serve download clients tab content with client configuration."""
    try:
        download_data = get_download_clients_tab_data()
        
        return render_template('settings/download_clients.html', **download_data)
    
    except Exception as e:
        logger.error(f"Error loading download clients tab: {e}")
        return render_template('settings/error.html',
                             error="Failed to load download clients information",
                             tab_name="Download Clients")

@tabs_bp.route('/configuration')
def configuration_tab():
    """Serve configuration tab content with application settings."""
    try:
        # Get configuration data
        config_data = get_configuration_tab_data()
        
        return render_template('settings/configuration.html', **config_data)
    
    except Exception as e:
        logger.error(f"Error loading configuration tab: {e}")
        return render_template('settings/error.html',
                             error="Failed to load configuration information",
                             tab_name="Configuration")

@tabs_bp.route('/media-management')
def media_management_tab():
    """Serve media management tab content with automated processing configuration."""
    try:
        media_data = get_media_management_tab_data()
        
        return render_template('settings/media-management.html', **media_data)
    
    except Exception as e:
        logger.error(f"Error loading media management tab: {e}")
        return render_template('settings/error.html',
                             error="Failed to load media management information",
                             tab_name="Media Management")

# ============================================================================
# TAB DATA COLLECTION FUNCTIONS
# ============================================================================





def get_services_tab_data() -> Dict[str, Any]:
    """Collect services information for the services tab."""
    logger.info("Starting services tab data collection")
    try:
        # Initialize default values first
        services_status = {}
        service_details = {}
        audiobookshelf_config = {}
        audiobookshelf_libraries = []

        logger.info("Getting services status")
        # Get services status
        try:
            services_status = {}
            logger.info(f"Services status: {services_status}")
        except Exception as e:
            logger.error(f"Error getting services status: {e}")
            
        logger.info("Getting config data")
        # Get configuration data
        try:
            config_service = get_config_service()
            config_data = config_service.list_config()
            logger.info(f"Config data keys count: {len(config_data)}")
        except Exception as e:
            logger.error(f"Error getting config data: {e}")
            config_data = {}
        
        logger.info("Getting detailed service information")
        # Get detailed service information
        
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
            test_results = None  # download_service removed.test_connections()
            service_details['download'] = {
                'overall_status': test_results.get('overall_status', 'unknown'),
                'providers': test_results.get('providers', {}),
                'clients': test_results.get('clients', {}),
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
            audiobookshelf_config = {
                'server_url': config_data.get('abs_url', '') or config_data.get('abs_host', ''),
                'api_key': config_data.get('abs_token', '') or config_data.get('abs_api_key', ''),
                'username': config_data.get('abs_username', ''),
                'password': config_data.get('abs_password', ''),
                'sync_enabled': config_data.get('abs_enabled', 'false').lower() in ['true', '1'],
                'sync_interval_hours': config_data.get('abs_sync_frequency', '30min'),
                'auto_match_books': config_data.get('abs_sync_metadata', 'true').lower() in ['true', '1'],
                'import_progress': config_data.get('abs_sync_only_owned', 'true').lower() in ['true', '1'],
                'import_ratings': config_data.get('abs_auto_sync', 'false').lower() in ['true', '1'],
                'library_id': config_data.get('abs_library_id', '')
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
        except Exception as e:
            logger.debug(f"Could not fetch AudioBookShelf libraries: {e}")
            audiobookshelf_libraries = []
        
        logger.info("Preparing services tab return data")
        return_data = {
            'services_status': services_status,
            'service_details': service_details,
            'audiobookshelf_config': audiobookshelf_config,
            'audiobookshelf_libraries': audiobookshelf_libraries,
            'last_updated': datetime.now().isoformat()
        }
        logger.debug("Services tab data keys: %s", list(return_data.keys()))
        return return_data
    
    except Exception as e:
        logger.error(f"Error collecting services tab data: {e}", exc_info=True)
        return {
            'services_status': {},
            'service_details': {},
            'audiobookshelf_config': {},
            'audiobookshelf_libraries': [],
            'last_updated': datetime.now().isoformat()
        }

def get_audiobookshelf_tab_data() -> Dict[str, Any]:
    """Collect AudioBookShelf configuration data for the audiobookshelf tab."""
    try:
        config_service = get_config_service()
        config_data = config_service.get_section('audiobookshelf')
        
        return {
            'audiobookshelf_config': {
                'server_url': config_data.get('abs_host', ''),
                'api_key': config_data.get('abs_api_key', ''),
                'library_id': config_data.get('abs_library_id', ''),
                'sync_enabled': config_data.get('abs_enabled', 'False').lower() in ['true', '1'],
                'auto_match_books': config_data.get('abs_sync_metadata', 'True').lower() in ['true', '1'],
                'import_ratings': config_data.get('abs_auto_sync', 'False').lower() in ['true', '1'],
                'sync_interval_hours': config_data.get('abs_sync_frequency', '30min')
            },
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error collecting audiobookshelf tab data: {e}")
        return {
            'audiobookshelf_config': {
                'server_url': '',
                'api_key': '',
                'library_id': '',
                'sync_enabled': False,
                'auto_match_books': True,
                'import_ratings': False,
                'sync_interval_hours': '30min'
            },
            'last_updated': datetime.now().isoformat()
        }

def get_audible_tab_data() -> Dict[str, Any]:
    """Collect Audible configuration data for the audible tab."""
    try:
        config_service = get_config_service()
        config_data = config_service.get_section('audible')
        
        # Helper to convert to bool safely
        def to_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ['true', '1', 'yes']
            return default
        
        return {
            'audible_config': {
                'username': config_data.get('username', ''),
                'password': config_data.get('password', ''),
                'country_code': config_data.get('country_code', 'us'),
                'max_results': config_data.get('max_results', '25'),
                'cache_duration': config_data.get('cache_duration', '2'),
                'auto_authenticate': to_bool(config_data.get('auto_authenticate', True)),
                'download_directory': config_data.get('download_directory', ''),
                'download_format': config_data.get('download_format', 'aaxc'),
                'download_quality': config_data.get('download_quality', 'best'),
                'include_cover': to_bool(config_data.get('include_cover', False)),
                'include_chapters': to_bool(config_data.get('include_chapters', False)),
                'include_pdf': to_bool(config_data.get('include_pdf', False)),
                'concurrent_downloads': config_data.get('concurrent_downloads', '1'),
                'temp_dir_enabled': to_bool(config_data.get('temp_dir_enabled', True)),
                'temp_directory': config_data.get('temp_directory', '/tmp/aural_archive_conversion')
            },
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error collecting audible tab data: {e}")
        return {
            'audible_config': {
                'username': '',
                'password': '',
                'country_code': 'us',
                'max_results': '25',
                'cache_duration': '2',
                'auto_authenticate': True,
                'download_directory': '',
                'download_format': 'aaxc',
                'download_quality': 'best',
                'include_cover': False,
                'include_chapters': False,
                'include_pdf': False,
                'concurrent_downloads': '1',
                'temp_dir_enabled': True,
                'temp_directory': '/tmp/aural_archive_conversion'
            },
            'last_updated': datetime.now().isoformat()
        }


def get_download_clients_tab_data() -> Dict[str, Any]:
    """Collect download client configuration for the download clients tab."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()

        qbittorrent_config = config_data.get('qbittorrent', {})
        jackett_config = config_data.get('jackett', {})

        return {
            'download_test_results': {'status': 'disabled'},
            'qbittorrent_config': {
                'qb_host': qbittorrent_config.get('qb_host', ''),
                'qb_port': qbittorrent_config.get('qb_port', ''),
                'qb_username': qbittorrent_config.get('qb_username', ''),
                'qb_configured': bool(qbittorrent_config.get('qb_host') and qbittorrent_config.get('qb_username'))
            },
            'jackett_config': {
                'jackett_url': jackett_config.get('jackett_url', ''),
                'jackett_api_key': jackett_config.get('jackett_api_key', ''),
                'jackett_configured': bool(jackett_config.get('jackett_url') and jackett_config.get('jackett_api_key'))
            },
            'available_providers': [],
            'available_clients': [],
            'last_updated': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error collecting download clients tab data: {e}")
        return {
            'download_test_results': {'error': str(e)},
            'qbittorrent_config': {},
            'jackett_config': {},
            'available_providers': [],
            'available_clients': [],
            'last_updated': datetime.now().isoformat()
        }

def get_configuration_tab_data() -> Dict[str, Any]:
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



def get_media_management_tab_data() -> Dict[str, Any]:
    """Collect media management information for the media management tab."""
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        media_section = config_data.get('media_management', {})

        media_management_config = {
            'enabled': media_section.get('enabled', 'true').lower() in ['true', '1'],
            'processing_mode': media_section.get('mode', 'automatic'),
            'log_level': media_section.get('log_level', 'INFO'),
            'monitor_directories': media_section.get('monitor_dirs', '/downloads/completed'),
            'monitor_interval_minutes': int(media_section.get('monitor_interval', 1)),
            'monitor_torrent_clients': media_section.get('monitor_clients', 'true').lower() in ['true', '1'],
            'file_operation': media_section.get('file_operation', 'move'),
            'preserve_source': media_section.get('preserve_source', 'false').lower() in ['true', '1'],
            'atomic_operations': media_section.get('atomic', 'false').lower() in ['true', '1'],
            'target_directory': media_section.get('target_dir', '/audiobooks'),
            'directory_template': media_section.get('dir_template', '{author}/{series}/{title}'),
            'file_template': media_section.get('file_template', '{title}'),
            'abs_integration': media_section.get('abs_enabled', 'true').lower() in ['true', '1'],
            'abs_library_id': media_section.get('abs_library', ''),
            'abs_auto_scan': media_section.get('abs_auto_scan', 'true').lower() in ['true', '1'],
            'abs_auto_match': media_section.get('abs_auto_match', 'true').lower() in ['true', '1'],
            'abs_match_provider': media_section.get('abs_provider', 'audible'),
            'parse_series_info': media_section.get('parse_series', 'true').lower() in ['true', '1'],
            'series_detection_patterns': media_section.get('series_patterns', 'Book ##, Part ##, Volume ##'),
            'multi_author_handling': media_section.get('multi_author', 'first'),
            'cleanup_empty_dirs': media_section.get('cleanup_empty', 'true').lower() in ['true', '1'],
        }

        abs_libraries = []
        try:
            abs_service = get_audiobookshelf_service()
            libraries = abs_service.get_libraries()
            if libraries:
                abs_libraries = [
                    {
                        'id': lib.get('id', ''),
                        'name': lib.get('name', ''),
                        'mediaType': lib.get('mediaType', ''),
                        'provider': lib.get('provider', ''),
                        'folders': [folder.get('fullPath', '') for folder in lib.get('folders', [])]
                    }
                    for lib in libraries
                    if lib.get('mediaType') == 'book'
                ]
        except Exception as e:
            logger.debug(f"Could not fetch AudioBookShelf libraries: {e}")

        directory_validation: Dict[str, Dict[str, Any]] = {}
        directories_to_check = [
            media_management_config['target_directory'],
            *media_management_config['monitor_directories'].split(',')
        ]

        for directory in directories_to_check:
            directory = directory.strip()
            if directory:
                try:
                    exists = os.path.exists(directory)
                    writable = os.access(directory, os.W_OK) if exists else False
                    readable = os.access(directory, os.R_OK) if exists else False
                    directory_validation[directory] = {
                        'exists': exists,
                        'writable': writable,
                        'readable': readable,
                        'status': 'ok' if (exists and writable and readable) else 'error'
                    }
                except Exception as e:
                    directory_validation[directory] = {
                        'exists': False,
                        'writable': False,
                        'readable': False,
                        'status': 'error',
                        'error': str(e)
                    }

        return {
            'media_management_config': media_management_config,
            'abs_libraries': abs_libraries,
            'download_clients_status': {},
            'directory_validation': directory_validation,
            'available_patterns': {
                'directory': [
                    '{author}',
                    '{author}/{series}',
                    '{author}/{series}/{title}',
                    '{series}/{title}',
                    '{genre}/{author}/{series}',
                    'Custom...'
                ],
                'file': [
                    '{title}',
                    '{title} - {author}',
                    '{author} - {title}',
                    '{series} #{sequence} - {title}',
                    '{author} - {series} #{sequence} - {title}',
                    'Custom...'
                ],
                'series_detection': [
                    'Book ##',
                    'Part ##',
                    'Volume ##',
                    'Episode ##',
                    '## -',
                    '#\\d+',
                    'Custom regex...'
                ]
            },
            'last_updated': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error collecting media management tab data: {e}")
        return {
            'media_management_config': {},
            'abs_libraries': [],
            'download_clients_status': {},
            'directory_validation': {},
            'available_patterns': {'directory': [], 'file': [], 'series_detection': []},
            'last_updated': datetime.now().isoformat()
        }



def get_all_services_status() -> Dict[str, str]:
    """Get status of all services using actual methods."""
    services = {}
    
    # Test Audible Service
    try:
        audible_service = get_audible_service()
        results = audible_service.search_books('test', num_results=1)
        services['audible'] = 'Working' if results else 'Failed'
    except Exception as e:
        logger.debug(f"Audible service test failed: {e}")
        services['audible'] = 'Failed'
    
    # Test AudioBookShelf Service
    try:
        abs_service = get_audiobookshelf_service()
        success, message = abs_service.test_connection()
        services['audiobookshelf'] = 'Connected' if success else 'Disconnected'
    except Exception as e:
        logger.debug(f"AudioBookShelf service test failed: {e}")
        services['audiobookshelf'] = 'Not Configured'
    
    # Test Download Service
    try:
        test_results = None  # download_service removed.test_connections()
        status = test_results.get('overall_status', 'unknown')
        services['download'] = status.title()
    except Exception as e:
        logger.debug(f"Download service test failed: {e}")
        services['download'] = 'Failed'
    
    # Test Metadata Service
    try:
        metadata_service = get_metadata_update_service()
        status = metadata_service.get_service_status()
        services['metadata_update'] = 'Working' if status.get('initialized') else 'Failed'
    except Exception as e:
        logger.debug(f"Metadata service test failed: {e}")
        services['metadata_update'] = 'Failed'
    
    # Test Database
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        services['database'] = 'Connected'
    except Exception as e:
        logger.debug(f"Database service test failed: {e}")
        services['database'] = 'Failed'
    
    # Test Configuration
    try:
        config_service = get_config_service()
        config_data = config_service.list_config()
        services['config'] = 'Loaded' if config_data else 'Failed'
    except Exception as e:
        logger.debug(f"Config service test failed: {e}")
        services['config'] = 'Failed'
    
    return services

# ============================================================================
# ERROR HANDLING AND UTILITIES
# ============================================================================

@tabs_bp.errorhandler(404)
def tab_not_found(error):
    """Handle 404 errors for tab routes."""
    return render_template('settings/error.html',
                         error="The requested settings tab was not found",
                         tab_name="Unknown"), 404

@tabs_bp.errorhandler(500)
def tab_internal_error(error):
    """Handle 500 errors for tab routes."""
    logger.error(f"Internal error in tab route: {error}")
    return render_template('settings/error.html',
                         error="An internal error occurred while loading the tab",
                         tab_name="Error"), 500

# ============================================================================
# TAB REFRESH ENDPOINTS
# ============================================================================

@tabs_bp.route('/refresh/<tab_name>')
def refresh_tab(tab_name):
    """Refresh a specific tab's data without full reload."""
    try:
        if tab_name == 'services':
            return services_tab()
        elif tab_name == 'download-clients':
            return download_clients_tab()
        elif tab_name == 'configuration':
            return configuration_tab()
        elif tab_name == 'media-management':
            return media_management_tab()
        else:
            return jsonify({'error': f'Unknown tab: {tab_name}'}), 404
    
    except Exception as e:
        logger.error(f"Error refreshing tab {tab_name}: {e}")
        return jsonify({'error': f'Failed to refresh tab: {str(e)}'}), 500

# ============================================================================
# TAB STATUS ENDPOINTS
# ============================================================================

@tabs_bp.route('/status')
def tabs_status():
    """Get the status of all tabs and their data freshness."""
    try:
        return jsonify({
            'success': True,
            'tabs': {
                'system': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'database': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'services': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'download-clients': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'configuration': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'search': {'status': 'available', 'last_loaded': datetime.now().isoformat()},
                'media-management': {'status': 'available', 'last_loaded': datetime.now().isoformat()}
            },
            'services_status': {},
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting tabs status: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to get tabs status: {str(e)}'
        }), 500

# Log successful module loading
logger.info("Settings tabs module loaded successfully")
__all__ = ['tabs_bp']