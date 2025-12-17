"""
Search API - Audiobook search endpoints using SearchEngineService and IndexerServiceManager
Location: api/search_api.py
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import logging
from typing import Any, Dict, List

from services.service_manager import get_config_service, get_status_service
from utils.search_normalization import normalize_search_terms

search_api_bp = Blueprint('search_api', __name__, url_prefix='/api/search')
logger = logging.getLogger("SearchAPI")

search_engine_service = None
indexer_manager_service = None
database_service = None


def _status_tracker():
    try:
        return get_status_service()
    except Exception:
        return None


def _result_count(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("total_results", "count", "matches"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    results = payload.get('results')
    if isinstance(results, list):
        return len(results)
    return None


def init_search_api(search_engine_svc, indexer_manager_svc, db_service):
    global search_engine_service, indexer_manager_service, database_service
    search_engine_service = search_engine_svc
    indexer_manager_service = indexer_manager_svc
    database_service = db_service
    logger.info("Search API initialized with services")


@search_api_bp.route('/manual', methods=['POST'])
def manual_search():
    try:
        if not search_engine_service:
            return jsonify({'success': False, 'error': 'Search engine service not available'}), 503
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        
        title = data.get('title', '').strip()
        author = data.get('author', '').strip()
        
        if not title:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        logger.info(f"Manual search requested: {title} by {author}")
        tracker = _status_tracker()
        status_id = None
        if tracker:
            event = tracker.start_event(
                category='search',
                title=f"Searching for {title}",
                message=author or 'Author unknown',
                source='Search API',
                metadata={'title': title, 'author': author}
            )
            status_id = event['id']
        try:
            result = search_engine_service.search_for_audiobook(title=title, author=author, manual_search=True)
            if status_id:
                count = _result_count(result)
                tracker.complete_event(status_id, message=f"{count if count is not None else 'Results'} ready")
            return jsonify(result)
        except Exception as exc:
            if status_id:
                tracker.fail_event(status_id, message='Search failed', error=str(exc))
            raise
        
    except Exception as e:
        logger.error(f"Error in manual search: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@search_api_bp.route('/direct', methods=['POST'])
def direct_provider_search():
    """Search only the configured direct providers."""
    try:
        if not indexer_manager_service:
            return jsonify({'success': False, 'error': 'Indexer manager not available'}), 503

        payload = request.get_json() or {}
        raw_query = (payload.get('query') or payload.get('title') or '').strip()
        author = (payload.get('author') or '').strip()
        title = (payload.get('title') or '').strip()
        limit = int(payload.get('limit', 50) or 50)

        if not any([raw_query, title, author]):
            return jsonify({'success': False, 'error': 'Provide a title, query, or author'}), 400

        normalized_query, normalized_title, normalized_author = normalize_search_terms(
            raw_query or title,
            title,
            author,
        )
        query = normalized_query or raw_query or title or normalized_author
        search_title = normalized_title or title or normalized_query
        search_author = normalized_author or author

        direct_indexers = [
            (name, indexer)
            for name, indexer in indexer_manager_service.indexers.items()
            if getattr(indexer, 'protocol', None) and getattr(indexer.protocol, 'value', indexer.protocol) == 'direct'
        ]

        if not direct_indexers:
            return jsonify({'success': False, 'error': 'No direct providers configured'}), 400

        aggregated: List[Dict[str, Any]] = []
        provider_stats: Dict[str, int] = {}

        for name, indexer in direct_indexers:
            try:
                results = indexer.search(
                    query=query,
                    author=search_author,
                    title=search_title,
                    limit=limit
                )
                provider_stats[name] = len(results)
                aggregated.extend(results or [])
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Direct provider %s search failed: %s", name, exc)
                provider_stats[name] = 0

        return jsonify({
            'success': True,
            'results': aggregated,
            'result_count': len(aggregated),
            'providers_queried': len(direct_indexers),
            'provider_breakdown': provider_stats
        })
    except Exception as exc:
        logger.error(f"Error searching direct providers: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


# ============================================================================
# Automatic Search Endpoints (for download-automation-manager.js)
# ============================================================================

@search_api_bp.route('/automatic/status', methods=['GET'])
def get_automatic_status():
    """Get automatic search status - stub for now"""
    try:
        return jsonify({
            'success': True,
            'running': False,
            'paused': False,
            'queue_size': 0,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error getting automatic status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/start', methods=['POST'])
def start_automatic_search():
    """Start automatic search - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error starting automatic search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/stop', methods=['POST'])
def stop_automatic_search():
    """Stop automatic search - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error stopping automatic search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/pause', methods=['POST'])
def pause_automatic_search():
    """Pause automatic search - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error pausing automatic search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/resume', methods=['POST'])
def resume_automatic_search():
    """Resume automatic search - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error resuming automatic search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/queue', methods=['GET'])
def get_automatic_queue():
    """Get automatic search queue - stub for now"""
    try:
        return jsonify({
            'success': True,
            'queue': [],
            'count': 0
        })
    except Exception as e:
        logger.error(f"Error getting automatic queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/config', methods=['GET'])
def get_automatic_config():
    """Get automatic search config - stub for now"""
    try:
        return jsonify({
            'success': True,
            'config': {}
        })
    except Exception as e:
        logger.error(f"Error getting automatic config: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/automatic/config', methods=['POST'])
def update_automatic_config():
    """Update automatic search config - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Automatic search service not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error updating automatic config: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@search_api_bp.route('/manual/search', methods=['POST'])
def manual_search_legacy():
    """Legacy endpoint - handles both new format (title/author) and old format (query)"""
    try:
        if not search_engine_service:
            return jsonify({'success': False, 'error': 'Search engine service not available'}), 503
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        
        # Support both formats:
        # New format: {"title": "Book", "author": "Author"}
        # Old format: {"query": "Book by Author", "options": {...}}
        
        if 'query' in data:
            # Old format from download-automation-manager.js
            query = data.get('query', '').strip()
            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400
            
            # Try to parse "title by author" format
            if ' by ' in query.lower():
                parts = query.lower().split(' by ', 1)
                title = parts[0].strip()
                author = parts[1].strip() if len(parts) > 1 else ''
            else:
                # Just use query as title
                title = query
                author = ''
        else:
            # New format
            title = data.get('title', '').strip()
            author = data.get('author', '').strip()
            
            if not title:
                return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        logger.info(f"Manual search requested: {title} by {author}")
        tracker = _status_tracker()
        status_id = None
        if tracker:
            event = tracker.start_event(
                category='search',
                title=f"Searching for {title}",
                message=author or 'Author unknown',
                source='Search API',
                metadata={'title': title, 'author': author, 'legacy': True}
            )
            status_id = event['id']
        try:
            result = search_engine_service.search_for_audiobook(title=title, author=author, manual_search=True)
            if status_id:
                count = _result_count(result)
                tracker.complete_event(status_id, message=f"{count if count is not None else 'Results'} ready")
            return jsonify(result)
        except Exception as exc:
            if status_id:
                tracker.fail_event(status_id, message='Search failed', error=str(exc))
            raise
        
    except Exception as e:
        logger.error(f"Error in manual search: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@search_api_bp.route('/manual/download', methods=['POST'])
def manual_download():
    """
    Manual download - send .torrent files directly to qBittorrent.
    
    User manually selects a search result and it goes straight to the download client.
    No queue involvement - the queue is only for automatic search task ordering.
    """
    try:
        from services.download_clients.qbittorrent_client import QBittorrentClient
        
        data = request.get_json()
        if not data or 'result' not in data:
            return jsonify({
                'success': False,
                'error': 'Result data required'
            }), 400
        
        result = data['result']
        
        # Extract download link (.torrent or NZB only)
        download_link = None
        if result.get('download_url'):
            download_link = result['download_url']
        elif result.get('nzb_url'):
            download_link = result['nzb_url']
        
        if not download_link:
            return jsonify({
                'success': False,
                'error': 'No torrent URL found in result'
            }), 400

        if download_link.lower().startswith('magnet:'):
            return jsonify({
                'success': False,
                'error': 'Magnet links are not supported. Provide a .torrent URL.'
            }), 400
        
        # Replace localhost with host IP for Docker compatibility
        config_service = get_config_service()
        qb_host = config_service.get_config_value('qbittorrent', 'qb_host', fallback='172.19.0.1')

        if 'localhost' in download_link or '127.0.0.1' in download_link:
            download_link = download_link.replace('localhost', qb_host)
            download_link = download_link.replace('127.0.0.1', qb_host)
            logger.info(f"Replaced localhost with host IP {qb_host}")
        
        logger.info(f"Manual download: {result.get('title', 'Unknown')}")
        
        # Get qBittorrent settings from config
        qb_port = config_service.get_config_value('qbittorrent', 'qb_port', fallback='8080')
        qb_username = config_service.get_config_value('qbittorrent', 'qb_username', fallback='admin')
        qb_password = config_service.get_config_value('qbittorrent', 'qb_password', fallback='adminadmin')
        category = config_service.get_config_value('qbittorrent', 'category', fallback='audiobooks')

        qb_config = {
            'host': qb_host or 'localhost',
            'port': int(qb_port or 8080),
            'username': qb_username or 'admin',
            'password': (qb_password or 'adminadmin').strip('"'),
            'use_ssl': False
        }
        
        # Initialize and connect to qBittorrent
        qb_client = QBittorrentClient(qb_config)
        
        if not qb_client.connect():
            error_msg = f'Failed to connect to qBittorrent: {qb_client.last_error}'
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
        
        logger.info("Connected to qBittorrent")
        
        # Send directly to qBittorrent - it handles everything from here
        add_result = qb_client.add_torrent(
            torrent_data=download_link,
            category=category,
            save_path=None,
            paused=False
        )
        
        if not add_result.get('success'):
            error_msg = add_result.get('error', 'Failed to add torrent')
            logger.error(f"qBittorrent error: {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
        
        logger.info(f"Successfully sent to qBittorrent: {result.get('title')}")
        
        return jsonify({
            'success': True,
            'message': f'"{result.get("title", "Unknown")}" sent to qBittorrent',
            'title': result.get('title')
        })
        
    except Exception as e:
        logger.error(f"Error in manual download: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@search_api_bp.route('/manual/preview', methods=['POST'])
def preview_download():
    """Preview download - stub for now"""
    try:
        return jsonify({
            'success': False,
            'message': 'Download preview not yet implemented - Phase 2'
        })
    except Exception as e:
        logger.error(f"Error in download preview: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Test & Validation Endpoints
# ============================================================================

@search_api_bp.route('/test', methods=['GET'])
def test_search_functionality():
    try:
        if not search_engine_service:
            return jsonify({'success': False, 'error': 'Search engine service not available'}), 503
        
        logger.info("Running search functionality test...")
        result = search_engine_service.test_search_functionality()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in search test: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'test_timestamp': datetime.now().isoformat()}), 500


@search_api_bp.route('/health', methods=['GET'])
def health_check():
    try:
        health = {
            'status': 'healthy',
            'services': {
                'search_engine': search_engine_service is not None,
                'indexer_manager': indexer_manager_service is not None,
                'database': database_service is not None
            },
            'timestamp': datetime.now().isoformat()
        }
        
        if not all(health['services'].values()):
            health['status'] = 'degraded'
        
        return jsonify(health)
        
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return jsonify({'status': 'unhealthy', 'error': str(e), 'timestamp': datetime.now().isoformat()}), 500
