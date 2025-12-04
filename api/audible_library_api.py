"""
Audible Library API - AuralArchive

Coordinates library export, search, stats, auth validation, and metadata sync
operations around the Audible cache and download services.

Author: AuralArchive Development Team
Updated: December 3, 2025
"""

import threading
from typing import Any, Dict

from flask import Blueprint, jsonify, current_app, request

from utils.logger import get_module_logger

# Import service manager
from services.audible.audible_service_manager import get_audible_manager
from services.service_manager import get_config_service
from services.audible.audible_metadata_sync_service.audible_metadata_sync_service import (
    AudibleMetadataSyncService,
    SyncMode
)

# Create blueprint
audible_library_api = Blueprint('audible_library_api', __name__, url_prefix='/api/audible/library')

logger = get_module_logger("API.AudibleLibrary")


@audible_library_api.route('/status', methods=['GET'])
def get_library_service_status():
    """
    Get comprehensive status of the Audible Library Service.
    
    Returns:
        JSON response with service status, authentication, and capabilities
    """
    try:
        manager = get_audible_manager()
        status = manager.library_service.get_service_status()
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        logger.error(f"Error getting library service status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error getting library service status'
        }), 500


@audible_library_api.route('/test-cli', methods=['GET'])
def test_audible_cli():
    """
    Test Python audible package availability and functionality.
    
    Returns:
        JSON response with package availability status and version information
    """
    try:
        manager = get_audible_manager()
        cli_status = manager.test_audible_cli_availability()
        
        return jsonify({
            'success': True,
            'data': cli_status
        })
        
    except Exception as e:
        logger.error(f"Error testing Python audible package: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error testing Python audible package'
        }), 500


@audible_library_api.route('/auth-status', methods=['GET'])
def check_authentication():
    """
    Check Audible authentication status.
    
    Returns:
        JSON response with authentication status and profile information
    """
    try:
        manager = get_audible_manager()
        auth_status = manager.check_authentication_status()
        
        return jsonify({
            'success': True,
            'data': auth_status
        })
        
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error checking authentication status'
        }), 500


@audible_library_api.route('/export', methods=['GET'])
def export_library():
    """
    Export the user's Audible library.
    
    Query Parameters:
        format: Export format ('json', 'csv', 'tsv') - default: 'json'
        force_refresh: Force fresh export even if cached ('true'/'false') - default: 'false'
    
    Returns:
        JSON response with library data and metadata
    """
    try:
        # Get query parameters
        output_format = request.args.get('format', 'json').lower()
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        # Validate format
        if output_format not in ['json', 'csv', 'tsv']:
            return jsonify({
                'success': False,
                'error': 'Invalid format',
                'message': 'Format must be one of: json, csv, tsv'
            }), 400
        
        manager = get_audible_manager()
        library_result = manager.export_library(output_format, force_refresh)
        
        return jsonify({
            'success': library_result.get('success', False),
            'data': library_result
        })
        
    except Exception as e:
        logger.error(f"Error exporting library: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error exporting library'
        }), 500


@audible_library_api.route('/stats', methods=['GET'])
def get_library_statistics():
    """
    Get statistics about the user's Audible library.
    
    Returns:
        JSON response with library statistics and summary information
    """
    try:
        manager = get_audible_manager()
        stats_result = manager.get_library_stats()
        
        return jsonify({
            'success': stats_result.get('success', False),
            'data': stats_result
        })
        
    except Exception as e:
        logger.error(f"Error getting library statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error getting library statistics'
        }), 500


@audible_library_api.route('/search', methods=['GET'])
def search_library():
    """
    Search within the user's Audible library.
    
    Query Parameters:
        q: Search query string (required)
        fields: Comma-separated list of fields to search (optional)
                Available fields: title, authors, narrators, series
    
    Returns:
        JSON response with search results
    """
    try:
        # Get query parameters
        query = request.args.get('q', '').strip()
        fields_param = request.args.get('fields', '')
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'Missing query',
                'message': 'Query parameter "q" is required'
            }), 400
        
        # Parse search fields
        search_fields = None
        if fields_param:
            search_fields = [field.strip() for field in fields_param.split(',') if field.strip()]
        
        manager = get_audible_manager()
        search_result = manager.search_library(query, search_fields)
        
        return jsonify({
            'success': search_result.get('success', False),
            'data': search_result
        })
        
    except Exception as e:
        logger.error(f"Error searching library: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error searching library'
        }), 500


@audible_library_api.route('/refresh', methods=['POST'])
def refresh_library():
    """
    Force refresh of the library cache.
    
    Returns:
        JSON response with refresh status and updated library data
    """
    try:
        manager = get_audible_manager()
        refresh_result = manager.refresh_library_cache()
        
        return jsonify({
            'success': refresh_result.get('success', False),
            'data': refresh_result
        })
        
    except Exception as e:
        logger.error(f"Error refreshing library: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error refreshing library'
        }), 500


@audible_library_api.route('/download/all', methods=['POST'])
def start_bulk_download():
    """Kick off a concurrent download of the entire Audible library."""

    def _to_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {'true', '1', 'yes', 'on'}

    try:
        manager = get_audible_manager()
        payload = request.get_json(silent=True) or {}

        # Load Audible defaults from config if available
        audible_defaults = {}
        try:
            config_service = get_config_service()
            audible_defaults = config_service.get_section('audible') or {}
        except Exception as cfg_exc:
            logger.debug(f"Unable to load Audible config defaults: {cfg_exc}")

        def _normalize_string(value, fallback):
            if value is None:
                return fallback
            if isinstance(value, str) and value.strip():
                return value.strip()
            return fallback

        format_pref = _normalize_string(
            payload.get('format'),
            _normalize_string(audible_defaults.get('download_format'), 'aaxc')
        )
        quality_pref = _normalize_string(
            payload.get('quality'),
            _normalize_string(audible_defaults.get('download_quality'), 'best')
        )

        start_date = payload.get('start_date')
        end_date = payload.get('end_date')

        include_pdf = _to_bool(
            payload.get('include_pdf'),
            _to_bool(audible_defaults.get('include_pdf'), False)
        )
        include_cover = _to_bool(
            payload.get('include_cover'),
            _to_bool(audible_defaults.get('include_cover'), True)
        )
        include_chapters = _to_bool(
            payload.get('include_chapters'),
            _to_bool(audible_defaults.get('include_chapters'), True)
        )

        jobs_raw = (
            payload.get('jobs')
            or payload.get('concurrent_downloads')
            or audible_defaults.get('concurrent_downloads')
            or audible_defaults.get('max_concurrent_downloads')
            or audible_defaults.get('download_concurrency')
        )
        try:
            jobs_value = int(jobs_raw) if jobs_raw is not None else None
        except (TypeError, ValueError):
            jobs_value = None

        result = manager.library_service.download_all_books(
            output_dir=payload.get('output_dir'),
            format=format_pref,
            quality=quality_pref,
            start_date=start_date,
            end_date=end_date,
            jobs=jobs_value if jobs_value is not None else 3,
            include_pdf=include_pdf,
            include_cover=include_cover,
            include_chapters=include_chapters
        )

        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Error starting bulk download: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error starting bulk download'
        }), 500


def _start_metadata_sync(sync_mode: str, mode_label: str):
    """Helper to start metadata sync in background thread."""
    try:
        request_data: Dict[str, Any] = request.get_json(silent=True) or {}
        force_refresh = bool(request_data.get('force_refresh', False))

        socketio = getattr(current_app, 'socketio', None)
        sync_service = AudibleMetadataSyncService(logger=logger, socketio=socketio)

        status_snapshot = sync_service.get_sync_status()
        if status_snapshot.get('is_syncing'):
            return jsonify({
                'success': False,
                'error': 'Sync already in progress',
                'data': status_snapshot
            }), 409

        def run_sync():
            try:
                sync_service.sync_library(mode=sync_mode, force_refresh=force_refresh)
            except Exception as exc:  # pragma: no cover - background thread logging
                logger.error(f"Audible {mode_label} sync failed: {exc}")

        thread = threading.Thread(target=run_sync, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'data': {
                'message': f'{mode_label} sync started - monitoring in background',
                'mode': sync_mode,
                'force_refresh': force_refresh
            }
        })

    except Exception as e:
        logger.error(f"Error starting {mode_label.lower()} sync: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error starting {mode_label.lower()} sync'
        }), 500


@audible_library_api.route('/sync/quick', methods=['POST'])
def start_quick_sync():
    """Start a background quick (delta) sync."""
    return _start_metadata_sync(SyncMode.QUICK, 'Quick')


@audible_library_api.route('/sync/full', methods=['POST'])
def start_full_sync():
    """Start a background full library sync."""
    return _start_metadata_sync(SyncMode.FULL, 'Full')


@audible_library_api.route('/sync/status', methods=['GET'])
def get_sync_status():
    """Return current sync state and progress."""
    try:
        socketio = getattr(current_app, 'socketio', None)
        sync_service = AudibleMetadataSyncService(logger=logger, socketio=socketio)
        status_snapshot = sync_service.get_sync_status()

        return jsonify({
            'success': True,
            'data': status_snapshot
        })

    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error getting sync status'
        }), 500


@audible_library_api.route('/setup-info', methods=['GET'])
def get_setup_information():
    """
    Get setup instructions for Audible authentication.
    
    Returns:
        JSON response with setup instructions and requirements
    """
    try:
        manager = get_audible_manager()
        auth_handler = manager.library_service.auth_handler
        setup_info = auth_handler.get_authentication_instructions()
        
        return jsonify({
            'success': True,
            'data': setup_info
        })
        
    except Exception as e:
        logger.error(f"Error getting setup information: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error getting setup information'
        }), 500


@audible_library_api.route('/validate-credentials', methods=['GET'])
def validate_credentials():
    """
    Validate existing Audible credentials.
    
    Returns:
        JSON response with validation results and profile information
    """
    try:
        manager = get_audible_manager()
        auth_handler = manager.library_service.auth_handler
        validation_result = auth_handler.validate_credentials()
        
        return jsonify({
            'success': True,
            'data': validation_result
        })
        
    except Exception as e:
        logger.error(f"Error validating credentials: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error validating credentials'
        }), 500


# Error handlers for the blueprint
@audible_library_api.errorhandler(404)
def handle_not_found(e):
    """Handle 404 errors for this blueprint."""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'message': 'The requested library API endpoint was not found'
    }), 404


@audible_library_api.errorhandler(405)
def handle_method_not_allowed(e):
    """Handle 405 errors for this blueprint."""
    return jsonify({
        'success': False,
        'error': 'Method not allowed',
        'message': 'The HTTP method is not allowed for this endpoint'
    }), 405
