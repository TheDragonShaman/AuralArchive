"""
Indexer Settings Routes - AuralArchive

Exposes CRUD, toggle, and validation APIs for Jackett/Prowlarr
indexers in the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from typing import Any, Iterable, List

from flask import Blueprint, jsonify, request  # type: ignore[import]

from config.config import Config
from services.service_manager import get_config_service, get_indexer_manager_service
from utils.logger import get_module_logger

logger = get_module_logger("SettingsIndexers")

# Use the shared config service from the service manager so the settings UI
# and API endpoints read/update the same configuration instance.
config_service = get_config_service()

indexers_bp = Blueprint('indexers_settings', __name__)

API_KEY_SENTINELS = {'***', '••••', 'REDACTED', 'MASKED'}


def _infer_indexer_type(indexer_key: str, feed_url: str = '', protocol: str = '') -> str:
    """Infer indexer type from key, feed URL, or protocol."""
    lower_key = (indexer_key or '').lower()
    lower_url = (feed_url or '').lower()
    lower_protocol = (protocol or '').lower()

    if lower_protocol == 'direct':
        return 'direct'
    if 'direct' in lower_key:
        return 'direct'
    if 'prowlarr' in lower_key:
        return 'prowlarr'
    return 'jackett'


def _resolve_protocol(indexer_type: str, requested_protocol: str = '') -> str:
    """Determine protocol based on indexer type when not explicitly supplied."""
    if requested_protocol:
        requested = requested_protocol.lower()
        if requested == 'direct':
            return 'direct'
        # Force torznab for all other cases; alternative protocols are disabled
        return 'torznab'
    if (indexer_type or '').lower() == 'direct':
        return 'direct'
    return 'torznab'


def _normalize_categories(raw_categories: Any, fallback: Iterable[str] = None) -> List[str]:
    """Normalize categories payload into a list of strings."""
    categories: List[str] = []

    if isinstance(raw_categories, list):
        categories = [str(item).strip() for item in raw_categories if str(item).strip()]
    elif isinstance(raw_categories, str):
        categories = [part.strip() for part in raw_categories.split(',') if part.strip()]

    if not categories and fallback:
        categories = [str(item).strip() for item in fallback if str(item).strip()]

    return categories or ['3030']


def _mask_api_key(api_key: str) -> str:
    """Return masked representation for display purposes."""
    if not api_key:
        return ''
    visible = api_key[:4]
    masked_len = max(len(api_key) - 4, 0)
    return f"{visible}{'*' * masked_len}"


def _load_indexers_config():
    """Load indexers configuration from config service or fallback defaults."""
    indexers = config_service.list_indexers_config()
    if indexers:
        return indexers
    return getattr(Config, 'INDEXERS', {}).copy()


def _save_indexer_config(indexer_key: str, config_data: dict) -> bool:
    """Persist a single indexer configuration via config service."""
    return config_service.set_indexer_config(indexer_key, config_data)


def _delete_indexer_config(indexer_key: str) -> bool:
    """Remove a single indexer configuration."""
    return config_service.delete_indexer_config(indexer_key)


@indexers_bp.route('/api/indexers', methods=['GET'])
def get_indexers():
    """Get all configured indexers"""
    try:
        indexers = _load_indexers_config()
        
        # Format for frontend
        formatted_indexers = {}
        for key, indexer in indexers.items():
            indexer_type = (indexer.get('type') or _infer_indexer_type(key, indexer.get('feed_url'), indexer.get('protocol'))).lower()
            categories = _normalize_categories(indexer.get('categories', []))
            api_key = indexer.get('api_key', '')
            base_url = indexer.get('base_url', '')
            session_id = indexer.get('session_id', '')
            protocol = _resolve_protocol(indexer_type, indexer.get('protocol', ''))
            is_direct = indexer_type == 'direct'
            configured = bool(base_url and session_id) if is_direct else bool(indexer.get('feed_url') and api_key)

            formatted_indexers[key] = {
                'name': indexer.get('name', key.capitalize()),
                'enabled': indexer.get('enabled', False),
                'feed_url': indexer.get('feed_url', ''),
                'base_url': base_url,
                'api_key': api_key,
                'api_key_masked': _mask_api_key(api_key),
                'session_id': session_id,
                'session_id_masked': _mask_api_key(session_id),
                'type': indexer_type,
                'protocol': protocol,
                'priority': int(indexer.get('priority', 999)),
                'categories': categories,
                'verify_ssl': bool(indexer.get('verify_ssl', True)),
                'timeout': int(indexer.get('timeout', 30)),
                'rate_limit': indexer.get('rate_limit', {
                    'requests_per_second': 1,
                    'max_concurrent': 1
                }),
                'configured': configured,
                'has_api_key': bool(api_key),
                'has_session_id': bool(session_id)
            }
        
        return jsonify({
            'success': True,
            'indexers': formatted_indexers
        })
    except Exception as e:
        logger.exception("Error getting indexers")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@indexers_bp.route('/api/indexers/<indexer_key>', methods=['PUT'])
def update_indexer(indexer_key):
    """Update or add indexer configuration"""
    try:
        data = request.get_json() or {}

        name = (data.get('name') or '').strip()
        feed_url = (data.get('feed_url') or '').strip()
        base_url = (data.get('base_url') or '').strip()
        priority_value = data.get('priority')

        if not name:
            return jsonify({
                'success': False,
                'error': 'Display name is required'
            }), 400

        indexers = _load_indexers_config()
        existing = indexers.get(indexer_key, {})

        # Get protocol from data or default based on indexer type
        indexer_type = (data.get('type') or existing.get('type') or _infer_indexer_type(indexer_key, feed_url or base_url)).lower()
        protocol = _resolve_protocol(indexer_type, data.get('protocol') or existing.get('protocol', ''))
        is_direct = indexer_type == 'direct'

        if is_direct and not base_url:
            return jsonify({
                'success': False,
                'error': 'Base URL is required'
            }), 400
        if not is_direct and not feed_url:
            return jsonify({
                'success': False,
                'error': 'Feed URL is required'
            }), 400

        # Normalize API key handling, allowing masked values to preserve existing secrets
        raw_api_key = (data.get('api_key') or '').strip()
        preserve_existing_api = raw_api_key in API_KEY_SENTINELS or raw_api_key == ''
        if preserve_existing_api and existing.get('api_key'):
            api_key = existing['api_key']
        else:
            api_key = raw_api_key

        raw_session_id = (data.get('session_id') or '').strip()
        preserve_existing_session = raw_session_id in API_KEY_SENTINELS or raw_session_id == ''
        if preserve_existing_session and existing.get('session_id'):
            session_id = existing['session_id']
        else:
            session_id = raw_session_id

        if is_direct and not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID is required'
            }), 400
        if not is_direct and not api_key:
            return jsonify({
                'success': False,
                'error': 'API key is required'
            }), 400

        categories = _normalize_categories(data.get('categories'), existing.get('categories', []))
        rate_limit = data.get('rate_limit') or existing.get('rate_limit') or {
            'requests_per_second': 1,
            'max_concurrent': 1
        }

        try:
            priority = int(priority_value if priority_value is not None else existing.get('priority', 999))
        except (TypeError, ValueError):
            priority = 999

        timeout_value = data.get('timeout', existing.get('timeout', 30))
        try:
            timeout = int(timeout_value) if timeout_value is not None else 30
        except (TypeError, ValueError):
            timeout = 30

        # Update indexer configuration
        updated_indexer = {
            'name': name,
            'enabled': bool(data.get('enabled', True)),
            'feed_url': feed_url.rstrip('/'),
            'base_url': base_url.rstrip('/'),
            'api_key': api_key,
            'session_id': session_id,
            'type': indexer_type,
            'protocol': protocol,
            'priority': priority,
            'categories': categories,
            'rate_limit': rate_limit,
            'verify_ssl': bool(data.get('verify_ssl', existing.get('verify_ssl', True))),
            'timeout': timeout
        }

        indexers[indexer_key] = updated_indexer

        # Save to config service
        if not _save_indexer_config(indexer_key, updated_indexer):
            return jsonify({
                'success': False,
                'error': 'Failed to save indexer configuration'
            }), 500
        
        # Reload indexer service manager
        try:
            indexer_service = get_indexer_manager_service()
            if indexer_service and hasattr(indexer_service, 'reload_indexers'):
                indexer_service.reload_indexers()
                logger.info("Reloaded indexer service after updating %s", indexer_key)
        except Exception as reload_error:
            logger.warning("Could not reload indexer service: %s", reload_error)
        
        return jsonify({
            'success': True,
            'message': f'Indexer {indexer_key} updated successfully',
            'indexer': {
                indexer_key: {
                    **indexers[indexer_key],
                    'api_key_masked': _mask_api_key(indexers[indexer_key].get('api_key', '')),
                    'has_api_key': bool(indexers[indexer_key].get('api_key')),
                    'session_id_masked': _mask_api_key(indexers[indexer_key].get('session_id', '')),
                    'has_session_id': bool(indexers[indexer_key].get('session_id'))
                }
            }
        })
    except Exception as e:
        logger.exception("Error updating indexer %s", indexer_key)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@indexers_bp.route('/api/indexers/<indexer_key>', methods=['DELETE'])
def delete_indexer(indexer_key):
    """Delete indexer configuration"""
    try:
        indexers = _load_indexers_config()
        
        if indexer_key not in indexers:
            return jsonify({
                'success': False,
                'error': f'Indexer {indexer_key} not found'
            }), 404
        
        # Remove indexer
        del indexers[indexer_key]

        # Save to config
        if not _delete_indexer_config(indexer_key):
            return jsonify({
                'success': False,
                'error': 'Failed to save indexer configuration'
            }), 500
        
        # Reload indexer service manager
        try:
            indexer_service = get_indexer_manager_service()
            if indexer_service and hasattr(indexer_service, 'reload_indexers'):
                indexer_service.reload_indexers()
                logger.info("Reloaded indexer service after deleting %s", indexer_key)
        except Exception as reload_error:
            logger.warning("Could not reload indexer service: %s", reload_error)
        
        return jsonify({
            'success': True,
            'message': f'Indexer {indexer_key} deleted successfully'
        })
    except Exception as e:
        logger.exception("Error deleting indexer %s", indexer_key)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@indexers_bp.route('/api/indexers/<indexer_key>/toggle', methods=['POST'])
def toggle_indexer(indexer_key):
    """Toggle indexer enabled/disabled"""
    try:
        indexers = _load_indexers_config()
        
        if indexer_key not in indexers:
            return jsonify({
                'success': False,
                'error': f'Indexer {indexer_key} not found'
            }), 404
        
        # Toggle enabled state
        current_state = indexers[indexer_key].get('enabled', False)
        indexers[indexer_key]['enabled'] = not current_state

        # Save to config
        if not _save_indexer_config(indexer_key, indexers[indexer_key]):
            return jsonify({
                'success': False,
                'error': 'Failed to save indexer configuration'
            }), 500
        
        # Reload indexer service manager
        try:
            indexer_service = get_indexer_manager_service()
            if indexer_service and hasattr(indexer_service, 'reload_indexers'):
                indexer_service.reload_indexers()
                logger.info("Reloaded indexer service after toggling %s", indexer_key)
        except Exception as reload_error:
            logger.warning("Could not reload indexer service: %s", reload_error)
        
        new_state = 'enabled' if not current_state else 'disabled'
        return jsonify({
            'success': True,
            'message': f'Indexer {indexer_key} {new_state}',
            'enabled': not current_state
        })
    except Exception as e:
        logger.exception("Error toggling indexer %s", indexer_key)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@indexers_bp.route('/api/indexers/<indexer_key>/test', methods=['POST'])
def test_indexer(indexer_key):
    """Test indexer connection"""
    try:
        indexer_service = get_indexer_manager_service()
        
        if not indexer_service:
            return jsonify({
                'success': False,
                'error': 'Indexer service not available'
            }), 500
        
        if hasattr(indexer_service, 'reload_indexers'):
            try:
                indexer_service.reload_indexers()
            except Exception as reload_error:
                logger.warning("Failed to reload indexers before test: %s", reload_error)

        # Get the specific indexer from the service
        if not hasattr(indexer_service, 'indexers') or indexer_key not in indexer_service.indexers:
            return jsonify({
                'success': False,
                'error': f'Indexer {indexer_key} not found in service'
            }), 404
        
        indexer = indexer_service.indexers[indexer_key]
        
        # Test connection
        try:
            result = indexer.test_connection()
            
            if result.get('success'):
                return jsonify({
                    'success': True,
                    'message': f'Successfully connected to {indexer_key}',
                    'capabilities': result.get('capabilities', {})
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Connection test failed')
                })
        except Exception as test_error:
            logger.error("Error testing indexer %s: %s", indexer_key, test_error)
            return jsonify({
                'success': False,
                'error': str(test_error)
            })
            
    except Exception as e:
        logger.error(f"Error in test_indexer for {indexer_key}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@indexers_bp.route('/api/indexers/test-all', methods=['POST'])
def test_all_indexers():
    """Test all configured indexers"""
    try:
        indexer_service = get_indexer_manager_service()
        
        if not indexer_service:
            return jsonify({
                'success': False,
                'error': 'Indexer service not available'
            }), 500
        
        # Test all connections
        results = {}
        
        if hasattr(indexer_service, 'test_all_connections'):
            results = indexer_service.test_all_connections()
        elif hasattr(indexer_service, 'indexers'):
            # Fallback: test each indexer individually
            for key, indexer in indexer_service.indexers.items():
                try:
                    results[key] = indexer.test_connection()
                except Exception as e:
                    results[key] = {
                        'success': False,
                        'error': str(e)
                    }
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.exception("Error testing all indexers")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
