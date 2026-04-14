"""
Module Name: indexers.py
Author: TheDragonShaman
Created: August 4, 2025
Last Modified: December 23, 2025
Description:
    Indexer settings routes for CRUD, toggle, and validation of Jackett/Prowlarr.
Location:
    /routes/settings_tools/indexers.py

"""

from typing import Any, Iterable, List

import requests as _requests
from flask import Blueprint, jsonify, request  # type: ignore[import]

from config.config import Config
from services.service_manager import get_config_service, get_indexer_manager_service
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Settings.Indexers")

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
    if 'nzbhydra' in lower_key:
        return 'nzbhydra2'
    if 'prowlarr' in lower_key:
        return 'prowlarr'
    return 'jackett'


def _resolve_protocol(indexer_type: str, requested_protocol: str = '') -> str:
    """Determine protocol based on indexer type when not explicitly supplied."""
    itype = (indexer_type or '').lower()
    if requested_protocol:
        requested = requested_protocol.lower()
        if requested == 'direct':
            return 'direct'
        if requested == 'newznab':
            return 'newznab'
        return 'torznab'
    if itype == 'direct':
        return 'direct'
    if itype == 'nzbhydra2':
        return 'newznab'
    if itype == 'prowlarr':
        # Prowlarr defaults to torznab; caller can override via requested_protocol
        return 'torznab'
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
            is_nzbhydra2 = indexer_type == 'nzbhydra2'
            is_prowlarr = indexer_type == 'prowlarr'
            if is_direct:
                configured = bool(base_url and session_id)
            elif is_nzbhydra2 or is_prowlarr:
                configured = bool(base_url and api_key)
            else:
                configured = bool(indexer.get('feed_url') and api_key)
            search_type = (indexer.get('search_type') or 'all').lower()
            if search_type == 'default':
                search_type = 'all'

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
                'search_type': search_type,
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
                'has_session_id': bool(session_id),
                'indexer_id': int(indexer.get('indexer_id', 0)),
                'indexer_name': indexer.get('indexer_name', ''),
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
        is_nzbhydra2 = indexer_type == 'nzbhydra2'
        is_prowlarr = indexer_type == 'prowlarr'

        if (is_direct or is_nzbhydra2 or is_prowlarr) and not base_url:
            return jsonify({
                'success': False,
                'error': 'Base URL is required'
            }), 400
        if not is_direct and not is_nzbhydra2 and not is_prowlarr and not feed_url:
            return jsonify({
                'success': False,
                'error': 'Feed URL is required'
            }), 400

        search_type = (data.get('search_type') or existing.get('search_type') or 'all').lower()
        valid_search_types = {
            'all', 'default', 'active', 'inactive', 'fl', 'fl-vip', 'vip', 'nvip', 'nmeta'
        }
        if search_type not in valid_search_types:
            search_type = 'all'
        elif search_type == 'default':
            search_type = 'all'

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

        # Prowlarr uses base_url; clear feed_url to avoid stale data
        if is_prowlarr:
            feed_url = ''

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

        indexer_id_val = data.get('indexer_id', existing.get('indexer_id', 0))
        try:
            indexer_id = int(indexer_id_val or 0)
        except (TypeError, ValueError):
            indexer_id = 0

        indexer_name = str(data.get('indexer_name') or existing.get('indexer_name') or '').strip()

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
            'search_type': search_type,
            'indexer_id': indexer_id,
            'indexer_name': indexer_name,
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


@indexers_bp.route('/api/indexers/prowlarr-preview', methods=['POST'])
def preview_prowlarr_indexers():
    """Fetch the list of indexers from Prowlarr without saving anything.

    Returns each indexer with an ``already_synced`` flag so the frontend can
    pre-tick entries that have not been imported yet.
    """
    try:
        data = request.get_json() or {}
        prowlarr_key = (data.get('prowlarr_key') or '').strip()

        indexers = _load_indexers_config()

        prowlarr_cfg = None
        prowlarr_cfg_key = None

        if prowlarr_key and prowlarr_key in indexers:
            cfg = indexers[prowlarr_key]
            if cfg.get('type', '').lower() == 'prowlarr' and cfg.get('base_url') and cfg.get('api_key'):
                prowlarr_cfg = cfg
                prowlarr_cfg_key = prowlarr_key

        # Prefer the dedicated aggregator connection section over a legacy indexer entry
        agg_conn = config_service.get_aggregator_connection('prowlarr')
        if agg_conn.get('base_url') and agg_conn.get('api_key'):
            prowlarr_cfg = {
                'base_url': agg_conn['base_url'],
                'api_key': agg_conn['api_key'],
                'verify_ssl': agg_conn.get('verify_ssl', True),
                'timeout': agg_conn.get('timeout', 15),
            }
            prowlarr_cfg_key = '__aggregator__'

        if prowlarr_cfg is None:
            for key, cfg in indexers.items():
                if (
                    cfg.get('type', '').lower() == 'prowlarr'
                    and cfg.get('base_url')
                    and cfg.get('api_key')
                ):
                    prowlarr_cfg = cfg
                    prowlarr_cfg_key = key
                    break

        if prowlarr_cfg is None:
            return jsonify({
                'success': False,
                'error': 'No Prowlarr connection configured. Add the Base URL and API key in the Aggregator Connections section.'
            }), 400

        base_url = prowlarr_cfg['base_url'].rstrip('/')
        api_key = prowlarr_cfg['api_key']
        verify_ssl = bool(prowlarr_cfg.get('verify_ssl', True))
        timeout = int(prowlarr_cfg.get('timeout', 15))

        try:
            resp = _requests.get(
                f"{base_url}/api/v1/indexer",
                headers={'X-Api-Key': api_key},
                timeout=timeout,
                verify=verify_ssl,
            )
        except _requests.exceptions.ConnectionError as exc:
            return jsonify({'success': False, 'error': f'Could not connect to Prowlarr: {exc}'}), 400
        except _requests.exceptions.Timeout:
            return jsonify({'success': False, 'error': 'Prowlarr request timed out'}), 400

        if resp.status_code == 401:
            return jsonify({'success': False, 'error': 'Prowlarr API key rejected (401)'}), 400
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'Prowlarr returned HTTP {resp.status_code}'}), 400

        remote_indexers = resp.json()
        if not isinstance(remote_indexers, list):
            return jsonify({'success': False, 'error': 'Unexpected response format from Prowlarr'}), 400

        result = []
        for ri in sorted(remote_indexers, key=lambda x: x.get('name', '')):
            rid = ri.get('id')
            rname = (ri.get('name') or '').strip()
            if not rid or not rname:
                continue
            protocol_raw = (ri.get('protocol') or 'torrent').lower()
            protocol = 'newznab' if protocol_raw == 'usenet' else 'torznab'
            sync_key = f"prowlarr_sync_{rid}"
            result.append({
                'id': rid,
                'name': rname,
                'protocol': protocol,
                'enabled': bool(ri.get('enable', True)),
                'already_synced': sync_key in indexers,
            })

        return jsonify({'success': True, 'indexers': result, 'prowlarr_key': prowlarr_cfg_key})

    except Exception as exc:
        logger.exception("Error during Prowlarr preview")
        return jsonify({'success': False, 'error': str(exc)}), 500


@indexers_bp.route('/api/indexers/prowlarr-sync', methods=['POST'])
def sync_prowlarr_indexers():
    """Sync indexers from a configured Prowlarr instance.

    Calls GET /api/v1/indexer on Prowlarr and creates/updates one AuralArchive
    indexer config entry per Prowlarr indexer, each with the correct indexer_id
    so that search requests reach the right endpoint.
    """
    try:
        data = request.get_json() or {}
        prowlarr_key = (data.get('prowlarr_key') or '').strip()
        # Optional list of Prowlarr indexer IDs to restrict the sync to.
        # When absent or empty, all indexers are synced.
        selected_ids_raw = data.get('selected_ids')
        selected_ids = set(int(i) for i in selected_ids_raw if str(i).isdigit()) if selected_ids_raw else None

        indexers = _load_indexers_config()

        # Locate the Prowlarr master config to use for the sync.
        # Prefer the dedicated aggregator connection section.
        prowlarr_cfg = None
        prowlarr_cfg_key = None

        agg_conn = config_service.get_aggregator_connection('prowlarr')
        if agg_conn.get('base_url') and agg_conn.get('api_key'):
            prowlarr_cfg = {
                'base_url': agg_conn['base_url'],
                'api_key': agg_conn['api_key'],
                'verify_ssl': agg_conn.get('verify_ssl', True),
                'timeout': agg_conn.get('timeout', 15),
                'priority': 999,
                'categories': ['3030'],
                'rate_limit': {'requests_per_second': 1, 'max_concurrent': 1},
            }
            prowlarr_cfg_key = '__aggregator__'

        # Fall back to a legacy prowlarr indexer entry
        if prowlarr_cfg is None:
            if prowlarr_key and prowlarr_key in indexers:
                cfg = indexers[prowlarr_key]
                if cfg.get('type', '').lower() == 'prowlarr' and cfg.get('base_url') and cfg.get('api_key'):
                    prowlarr_cfg = cfg
                    prowlarr_cfg_key = prowlarr_key
        if prowlarr_cfg is None:
            for key, cfg in indexers.items():
                if (
                    cfg.get('type', '').lower() == 'prowlarr'
                    and cfg.get('base_url')
                    and cfg.get('api_key')
                ):
                    prowlarr_cfg = cfg
                    prowlarr_cfg_key = key
                    break

        if prowlarr_cfg is None:
            return jsonify({
                'success': False,
                'error': 'No Prowlarr connection configured. Add the Base URL and API key in the Aggregator Connections section.'
            }), 400

        base_url = prowlarr_cfg['base_url'].rstrip('/')
        api_key = prowlarr_cfg['api_key']
        verify_ssl = bool(prowlarr_cfg.get('verify_ssl', True))
        timeout = int(prowlarr_cfg.get('timeout', 15))
        parent_priority = int(prowlarr_cfg.get('priority', 999))
        parent_categories = prowlarr_cfg.get('categories') or ['3030']
        parent_rate_limit = prowlarr_cfg.get('rate_limit') or {'requests_per_second': 1, 'max_concurrent': 1}

        try:
            resp = _requests.get(
                f"{base_url}/api/v1/indexer",
                headers={'X-Api-Key': api_key},
                timeout=timeout,
                verify=verify_ssl,
            )
        except _requests.exceptions.ConnectionError as exc:
            return jsonify({'success': False, 'error': f'Could not connect to Prowlarr: {exc}'}), 400
        except _requests.exceptions.Timeout:
            return jsonify({'success': False, 'error': 'Prowlarr request timed out'}), 400

        if resp.status_code == 401:
            return jsonify({'success': False, 'error': 'Prowlarr API key rejected (401)'}), 400
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'Prowlarr returned HTTP {resp.status_code}'}), 400

        remote_indexers = resp.json()
        if not isinstance(remote_indexers, list):
            return jsonify({'success': False, 'error': 'Unexpected response format from Prowlarr'}), 400

        created, updated_list, errors = [], [], []

        for ri in remote_indexers:
            rid = ri.get('id')
            rname = (ri.get('name') or '').strip()
            if not rid or not rname:
                continue

            # Skip indexers the user didn't select (when a selection was made)
            if selected_ids is not None and rid not in selected_ids:
                continue

            # Map Prowlarr DownloadProtocol to our protocol string
            protocol_raw = (ri.get('protocol') or 'torrent').lower()
            protocol = 'newznab' if protocol_raw == 'usenet' else 'torznab'

            # Pick audio/book categories (3000-3999) from capabilities when available
            categories = list(parent_categories)
            caps = ri.get('capabilities') or {}
            cap_cats = caps.get('categories') or []
            if cap_cats:
                audio_cats = [
                    str(c['id'])
                    for c in cap_cats
                    if isinstance(c, dict) and 3000 <= int(c.get('id', 0)) <= 3999
                ]
                if audio_cats:
                    categories = audio_cats

            indexer_key = f"prowlarr_sync_{rid}"
            existing = indexers.get(indexer_key, {})
            is_new = indexer_key not in indexers

            config_data = {
                'name': f"Prowlarr - {rname}",
                'enabled': bool(ri.get('enable', True)),
                'feed_url': '',
                'base_url': base_url,
                'api_key': api_key,
                'session_id': '',
                'type': 'prowlarr',
                'protocol': protocol,
                'search_type': existing.get('search_type', 'all'),
                'priority': int(existing.get('priority', parent_priority)),
                'categories': categories,
                'verify_ssl': verify_ssl,
                'timeout': int(prowlarr_cfg.get('timeout', 30)),
                'rate_limit': parent_rate_limit,
                'indexer_id': rid,
            }

            if _save_indexer_config(indexer_key, config_data):
                if is_new:
                    created.append({'key': indexer_key, 'name': config_data['name']})
                else:
                    updated_list.append({'key': indexer_key, 'name': config_data['name']})
            else:
                errors.append({'key': indexer_key, 'name': rname, 'error': 'Save failed'})

        # Reload indexer service
        try:
            indexer_service = get_indexer_manager_service()
            if indexer_service and hasattr(indexer_service, 'reload_indexers'):
                indexer_service.reload_indexers()
        except Exception as reload_err:
            logger.warning("Could not reload indexer service after Prowlarr sync: %s", reload_err)

        total = len(created) + len(updated_list)
        logger.info(
            "Prowlarr sync complete: %d created, %d updated, %d errors",
            len(created), len(updated_list), len(errors),
        )
        return jsonify({
            'success': True,
            'message': f'Synced {total} indexer(s) from Prowlarr ({len(created)} new, {len(updated_list)} updated)',
            'created': created,
            'updated': updated_list,
            'errors': errors,
            'total': total,
            'prowlarr_key': prowlarr_cfg_key,
        })

    except Exception as exc:
        logger.exception("Error during Prowlarr sync")
        return jsonify({'success': False, 'error': str(exc)}), 500


import re as _re


def _safe_key(name: str) -> str:
    """Turn an arbitrary indexer name into a safe config key segment."""
    return _re.sub(r'[^a-z0-9]+', '_', name.lower().strip()).strip('_') or 'indexer'


@indexers_bp.route('/api/indexers/nzbhydra2-preview', methods=['POST'])
def preview_nzbhydra2_indexers():
    """Fetch the list of indexers from NZBHydra2 without saving anything."""
    try:
        indexers = _load_indexers_config()

        agg_conn = config_service.get_aggregator_connection('nzbhydra2')
        if not agg_conn.get('base_url') or not agg_conn.get('api_key'):
            return jsonify({
                'success': False,
                'error': 'No NZBHydra2 connection configured. Add the Base URL and API key in the Aggregator Connections section.'
            }), 400

        base_url = agg_conn['base_url'].rstrip('/')
        api_key = agg_conn['api_key']
        verify_ssl = bool(agg_conn.get('verify_ssl', True))
        timeout = int(agg_conn.get('timeout', 15))

        try:
            # NZBHydra2 GET /api/stats/indexers fails with 400/500 (Spring bug
            # #882: Spring tries to deserialize a missing request body).
            # Workaround: POST with apikey as query param (for auth) and also
            # in the JSON body (so the body is non-empty for Spring).
            resp = _requests.post(
                f"{base_url}/api/stats/indexers",
                params={'apikey': api_key},
                json={'apikey': api_key},
                timeout=timeout,
                verify=verify_ssl,
            )
        except _requests.exceptions.ConnectionError as exc:
            return jsonify({'success': False, 'error': f'Could not connect to NZBHydra2: {exc}'}), 400
        except _requests.exceptions.Timeout:
            return jsonify({'success': False, 'error': 'NZBHydra2 request timed out'}), 400

        if resp.status_code == 401:
            return jsonify({'success': False, 'error': 'NZBHydra2 API key rejected (401)'}), 400
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'NZBHydra2 returned HTTP {resp.status_code}'}), 400

        remote_indexers = resp.json()
        if not isinstance(remote_indexers, list):
            return jsonify({'success': False, 'error': 'Unexpected response format from NZBHydra2'}), 400

        result = []
        for ri in sorted(remote_indexers, key=lambda x: x.get('indexer', '')):
            rname = (ri.get('indexer') or '').strip()
            if not rname:
                continue
            state = (ri.get('state') or '').upper()
            sync_key = f"nzbhydra2_sync_{_safe_key(rname)}"
            result.append({
                'id': rname,          # NZBHydra2 uses names, not integer IDs
                'name': rname,
                'protocol': 'newznab',
                'enabled': state != 'DISABLED_USER',
                'already_synced': sync_key in indexers,
            })

        return jsonify({'success': True, 'indexers': result})

    except Exception as exc:
        logger.exception("Error during NZBHydra2 preview")
        return jsonify({'success': False, 'error': str(exc)}), 500


@indexers_bp.route('/api/indexers/nzbhydra2-sync', methods=['POST'])
def sync_nzbhydra2_indexers():
    """Sync indexers from NZBHydra2.

    Creates one per-indexer config entry keyed ``nzbhydra2_sync_{safe_name}``.
    Each entry targets the shared ``{base_url}/api`` endpoint and restricts
    searches to its specific indexer via the ``indexers`` query parameter.
    """
    try:
        data = request.get_json() or {}
        selected_ids_raw = data.get('selected_ids')
        # For NZBHydra2 the "id" is the indexer name string
        selected_names = set(str(i) for i in selected_ids_raw) if selected_ids_raw else None

        indexers = _load_indexers_config()

        agg_conn = config_service.get_aggregator_connection('nzbhydra2')
        if not agg_conn.get('base_url') or not agg_conn.get('api_key'):
            return jsonify({
                'success': False,
                'error': 'No NZBHydra2 connection configured.'
            }), 400

        base_url = agg_conn['base_url'].rstrip('/')
        api_key = agg_conn['api_key']
        verify_ssl = bool(agg_conn.get('verify_ssl', True))
        timeout = int(agg_conn.get('timeout', 15))

        try:
            # NZBHydra2 GET /api/stats/indexers fails with 400/500 (Spring bug
            # #882: Spring tries to deserialize a missing request body).
            # Workaround: POST with apikey as query param (for auth) and also
            # in the JSON body (so the body is non-empty for Spring).
            resp = _requests.post(
                f"{base_url}/api/stats/indexers",
                params={'apikey': api_key},
                json={'apikey': api_key},
                timeout=timeout,
                verify=verify_ssl,
            )
        except _requests.exceptions.ConnectionError as exc:
            return jsonify({'success': False, 'error': f'Could not connect to NZBHydra2: {exc}'}), 400
        except _requests.exceptions.Timeout:
            return jsonify({'success': False, 'error': 'NZBHydra2 request timed out'}), 400

        if resp.status_code == 401:
            return jsonify({'success': False, 'error': 'NZBHydra2 API key rejected (401)'}), 400
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'NZBHydra2 returned HTTP {resp.status_code}'}), 400

        remote_indexers = resp.json()
        if not isinstance(remote_indexers, list):
            return jsonify({'success': False, 'error': 'Unexpected response format from NZBHydra2'}), 400

        created, updated_list, errors = [], [], []

        for ri in remote_indexers:
            rname = (ri.get('indexer') or '').strip()
            if not rname:
                continue
            if selected_names is not None and rname not in selected_names:
                continue

            state = (ri.get('state') or '').upper()
            indexer_key = f"nzbhydra2_sync_{_safe_key(rname)}"
            existing = indexers.get(indexer_key, {})
            is_new = indexer_key not in indexers

            config_data = {
                'name': f"NZBHydra2 - {rname}",
                'enabled': state != 'DISABLED_USER',
                'feed_url': '',
                'base_url': base_url,
                'api_key': api_key,
                'session_id': '',
                'type': 'nzbhydra2',
                'protocol': 'newznab',
                'search_type': existing.get('search_type', 'all'),
                'priority': int(existing.get('priority', 999)),
                'categories': existing.get('categories') or ['3030'],
                'verify_ssl': verify_ssl,
                'timeout': int(agg_conn.get('timeout', 30)),
                'rate_limit': existing.get('rate_limit') or {'requests_per_second': 1, 'max_concurrent': 1},
                'indexer_id': 0,
                'indexer_name': rname,
            }

            if _save_indexer_config(indexer_key, config_data):
                if is_new:
                    created.append({'key': indexer_key, 'name': config_data['name']})
                else:
                    updated_list.append({'key': indexer_key, 'name': config_data['name']})
            else:
                errors.append({'key': indexer_key, 'name': rname, 'error': 'Save failed'})

        try:
            indexer_service = get_indexer_manager_service()
            if indexer_service and hasattr(indexer_service, 'reload_indexers'):
                indexer_service.reload_indexers()
        except Exception as reload_err:
            logger.warning("Could not reload indexer service after NZBHydra2 sync: %s", reload_err)

        total = len(created) + len(updated_list)
        logger.info(
            "NZBHydra2 sync complete: %d created, %d updated, %d errors",
            len(created), len(updated_list), len(errors),
        )
        return jsonify({
            'success': True,
            'message': f'Synced {total} indexer(s) from NZBHydra2 ({len(created)} new, {len(updated_list)} updated)',
            'created': created,
            'updated': updated_list,
            'errors': errors,
            'total': total,
        })

    except Exception as exc:
        logger.exception("Error during NZBHydra2 sync")
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Aggregator connection routes ─────────────────────────────────────────

SUPPORTED_AGGREGATORS = {'prowlarr', 'nzbhydra2'}


@indexers_bp.route('/api/aggregators', methods=['GET'])
def get_aggregators():
    """Return saved connection settings for all aggregators."""
    result = {}
    for agg in SUPPORTED_AGGREGATORS:
        conn = config_service.get_aggregator_connection(agg)
        result[agg] = {
            'base_url': conn.get('base_url', ''),
            'has_api_key': bool(conn.get('api_key', '')),
            'verify_ssl': conn.get('verify_ssl', True),
            'timeout': conn.get('timeout', 30),
        }
    return jsonify({'success': True, 'aggregators': result})


@indexers_bp.route('/api/aggregators/<aggregator>', methods=['POST'])
def save_aggregator(aggregator):
    """Save connection settings (base_url, api_key) for an aggregator."""
    if aggregator not in SUPPORTED_AGGREGATORS:
        return jsonify({'success': False, 'error': f'Unknown aggregator: {aggregator}'}), 400

    data = request.get_json() or {}
    base_url = (data.get('base_url') or '').strip()
    api_key_raw = (data.get('api_key') or '').strip()
    verify_ssl = bool(data.get('verify_ssl', True))
    timeout = int(data.get('timeout', 30))

    if not base_url:
        return jsonify({'success': False, 'error': 'base_url is required'}), 400

    # If the user submitted a sentinel / masked value, keep the stored key
    if api_key_raw in API_KEY_SENTINELS:
        existing = config_service.get_aggregator_connection(aggregator)
        api_key_raw = existing.get('api_key', '')

    ok = config_service.set_aggregator_connection(aggregator, base_url, api_key_raw, verify_ssl, timeout)
    if ok:
        return jsonify({'success': True, 'message': f'{aggregator.capitalize()} connection saved'})
    return jsonify({'success': False, 'error': 'Failed to save connection'}), 500


@indexers_bp.route('/api/aggregators/<aggregator>/test', methods=['POST'])
def test_aggregator(aggregator):
    """Test connectivity to an aggregator using its stored (or submitted) credentials."""
    if aggregator not in SUPPORTED_AGGREGATORS:
        return jsonify({'success': False, 'error': f'Unknown aggregator: {aggregator}'}), 400

    data = request.get_json() or {}
    base_url = (data.get('base_url') or '').strip()
    api_key_raw = (data.get('api_key') or '').strip()

    # Fall back to stored values when form fields are empty / masked
    stored = config_service.get_aggregator_connection(aggregator)
    if not base_url:
        base_url = stored.get('base_url', '')
    if not base_url:
        return jsonify({'success': False, 'error': 'No base URL configured'}), 400
    if api_key_raw in API_KEY_SENTINELS or not api_key_raw:
        api_key_raw = stored.get('api_key', '')

    verify_ssl = bool(data.get('verify_ssl', stored.get('verify_ssl', True)))
    timeout = int(data.get('timeout', stored.get('timeout', 15)))
    base_url = base_url.rstrip('/')

    try:
        if aggregator == 'prowlarr':
            resp = _requests.get(
                f"{base_url}/api/v1/system/status",
                headers={'X-Api-Key': api_key_raw},
                timeout=timeout,
                verify=verify_ssl,
            )
        else:  # nzbhydra2
            resp = _requests.get(
                f"{base_url}/api",
                params={'apikey': api_key_raw, 't': 'caps'},
                timeout=timeout,
                verify=verify_ssl,
            )
    except _requests.exceptions.ConnectionError as exc:
        return jsonify({'success': False, 'error': f'Could not connect: {exc}'}), 400
    except _requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Connection timed out'}), 400

    if resp.status_code == 401:
        return jsonify({'success': False, 'error': 'API key rejected (401)'}), 400
    if resp.status_code >= 400:
        return jsonify({'success': False, 'error': f'HTTP {resp.status_code}'}), 400

    return jsonify({'success': True, 'message': f'Connected to {aggregator.capitalize()} successfully'})


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
