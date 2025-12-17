"""
Download Management API
=======================

REST API endpoints for download queue management and control.

IMPORTANT: Currently only qBittorrent is supported as a download client.
Additional torrent clients (Deluge, Transmission) will be added soon.

Endpoints:
- POST   /api/downloads/queue         - Add book to download queue
- GET    /api/downloads/queue         - Get all queue items
- GET    /api/downloads/queue/<id>    - Get specific download
- DELETE /api/downloads/queue/<id>    - Cancel/remove download
- POST   /api/downloads/queue/<id>/pause   - Pause download
- POST   /api/downloads/queue/<id>/resume  - Resume download
- POST   /api/downloads/queue/<id>/retry   - Retry failed download
- GET    /api/downloads/status        - Get service status
- GET    /api/downloads/statistics    - Get queue statistics
- POST   /api/downloads/service/start - Start monitoring service
- POST   /api/downloads/service/stop  - Stop monitoring service
"""

from flask import Blueprint, request, jsonify
import logging
from typing import Dict, Any

from services.service_manager import get_download_management_service

logger = logging.getLogger(__name__)

# Create blueprint
download_management_bp = Blueprint('download_management', __name__)


# ============================================================================
# QUEUE MANAGEMENT ENDPOINTS
# ============================================================================

@download_management_bp.route('/queue', methods=['POST'])
def add_to_queue():
    """
    Add a book to the download queue.
    
    Request JSON:
    {
        "book_asin": "B00XXXXXX",          # Required: Book ASIN
        "search_result_id": 123,            # Optional: Pre-selected search result
        "priority": 5,                      # Optional: Queue priority (1-10, default 5)
        "seeding_enabled": true,            # Optional: Override seeding config
        "delete_source": false              # Optional: Override delete source config
    }
    
    Returns:
    {
        "success": true,
        "download_id": 123,
        "message": "Added to queue"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        # Validate required fields
        book_asin = data.get('book_asin')
        if not book_asin:
            return jsonify({
                'success': False,
                'error': 'book_asin is required'
            }), 400
        
        # Get service
        dm_service = get_download_management_service()

        result = dm_service.add_to_queue(
            book_asin,
            search_result_id=data.get('search_result_id'),
            priority=data.get('priority', 5),
            seeding_enabled=data.get('seeding_enabled'),
            delete_source=data.get('delete_source')
        )

        return jsonify(result), 200 if result.get('success') else 400

    except Exception as e:
        logger.error(f"Error adding to download queue: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@download_management_bp.route('/queue', methods=['GET'])
def get_queue():
    """
    Get all download queue items with optional filtering.
    
    Query Parameters:
    - status: Filter by status (e.g., QUEUED, DOWNLOADING, COMPLETE)
    - limit: Maximum number of results (default: 100)
    - offset: Pagination offset (default: 0)
    
    Returns:
    {
        "success": true,
        "downloads": [
            {
                "id": 123,
                "book_asin": "B00XXXXXX",
                "status": "DOWNLOADING",
                "progress": 45,
                "created_at": "2025-10-28T10:30:00",
                ...
            }
        ],
        "total": 25,
        "limit": 100,
        "offset": 0
    }
    """
    try:
        # Get query parameters
        status_filter = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Get service
        dm_service = get_download_management_service()
        
        # Get queue items
        queue_items = dm_service.get_queue(
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        return jsonify({
            'success': True,
            'downloads': queue_items,
            'total': len(queue_items),
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error getting download queue: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/<int:download_id>', methods=['GET'])
def get_download(download_id: int):
    """
    Get details for a specific download.
    
    Returns:
    {
        "success": true,
        "download": {
            "id": 123,
            "book_asin": "B00XXXXXX",
            "status": "DOWNLOADING",
            "progress": 45,
            "download_speed": "2.5 MB/s",
            "eta": "5 minutes",
            ...
        }
    }
    """
    try:
        dm_service = get_download_management_service()
        download = dm_service.queue_manager.get_download(download_id)
        
        if not download:
            return jsonify({
                'success': False,
                'error': 'Download not found'
            }), 404
        
        return jsonify({
            'success': True,
            'download': download
        })
        
    except Exception as e:
        logger.error(f"Error getting download {download_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/<int:download_id>', methods=['DELETE'])
def cancel_download(download_id: int):
    """
    Cancel and remove a download from the queue.
    
    Returns:
    {
        "success": true,
        "message": "Download cancelled"
    }
    """
    try:
        dm_service = get_download_management_service()
        result = dm_service.cancel_download(download_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error cancelling download {download_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/<int:download_id>/pause', methods=['POST'])
def pause_download(download_id: int):
    """
    Pause an active download.
    
    Note: Only works during DOWNLOADING state.
    
    Returns:
    {
        "success": true,
        "message": "Download paused"
    }
    """
    try:
        dm_service = get_download_management_service()
        result = dm_service.pause_download(download_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error pausing download {download_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/<int:download_id>/resume', methods=['POST'])
def resume_download(download_id: int):
    """
    Resume a paused download.
    
    Returns:
    {
        "success": true,
        "message": "Download resumed"
    }
    """
    try:
        dm_service = get_download_management_service()
        result = dm_service.resume_download(download_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error resuming download {download_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/<int:download_id>/retry', methods=['POST'])
def retry_download(download_id: int):
    """
    Retry a failed download.
    
    Resets retry counters and moves download back to appropriate stage.
    
    Returns:
    {
        "success": true,
        "message": "Download retry initiated"
    }
    """
    try:
        dm_service = get_download_management_service()
        
        # Get current download
        download = dm_service.queue_manager.get_download(download_id)
        if not download:
            return jsonify({
                'success': False,
                'error': 'Download not found'
            }), 404
        
        if download['status'] != 'FAILED':
            return jsonify({
                'success': False,
                'error': f"Cannot retry download in {download['status']} state"
            }), 400
        
        # Reset retry counters and move back to QUEUED
        dm_service.queue_manager.update_download(download_id, {
            'status': 'QUEUED',
            'retry_count': 0,
            'last_error': None,
            'failed_stage': None
        })
        
        dm_service.event_emitter.emit_state_changed(
            download_id, 
            'QUEUED', 
            'Manual retry initiated'
        )
        
        return jsonify({
            'success': True,
            'message': 'Download retry initiated'
        })
        
    except Exception as e:
        logger.error(f"Error retrying download {download_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# STATUS & STATISTICS ENDPOINTS
# ============================================================================

@download_management_bp.route('/status', methods=['GET'])
def get_service_status():
    """
    Get download management service status.
    
    Returns:
    {
        "success": true,
        "status": {
            "monitoring_active": true,
            "polling_interval": 2,
            "queue_statistics": {
                "total": 25,
                "queued": 5,
                "downloading": 3,
                "complete": 12,
                "failed": 2
            },
            "active_downloads": 3
        }
    }
    """
    try:
        dm_service = get_download_management_service()
        status = dm_service.get_service_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get detailed queue statistics.
    
    Returns:
    {
        "success": true,
        "statistics": {
            "by_status": {
                "QUEUED": 5,
                "SEARCHING": 2,
                "DOWNLOADING": 3,
                ...
            },
            "success_rate": 85.5,
            "average_download_time": "15 minutes",
            "total_size_downloaded": "25.5 GB",
            "recent_completions": [...]
        }
    }
    """
    try:
        dm_service = get_download_management_service()
        stats = dm_service.queue_manager.get_queue_statistics()
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# SERVICE CONTROL ENDPOINTS
# ============================================================================

@download_management_bp.route('/service/start', methods=['POST'])
def start_monitoring():
    """
    Start the download monitoring service.
    
    Returns:
    {
        "success": true,
        "message": "Monitoring service started"
    }
    """
    try:
        dm_service = get_download_management_service()
        dm_service.start_monitoring()
        
        return jsonify({
            'success': True,
            'message': 'Monitoring service started'
        })
        
    except Exception as e:
        logger.error(f"Error starting monitoring service: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/service/stop', methods=['POST'])
def stop_monitoring():
    """
    Stop the download monitoring service.
    
    Note: Active downloads will not be monitored until service is restarted.
    
    Returns:
    {
        "success": true,
        "message": "Monitoring service stopped"
    }
    """
    try:
        dm_service = get_download_management_service()
        dm_service.stop_monitoring()
        
        return jsonify({
            'success': True,
            'message': 'Monitoring service stopped'
        })
        
    except Exception as e:
        logger.error(f"Error stopping monitoring service: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@download_management_bp.route('/queue/bulk/cancel', methods=['POST'])
def bulk_cancel():
    """
    Cancel multiple downloads.
    
    Request JSON:
    {
        "download_ids": [123, 124, 125]
    }
    
    Returns:
    {
        "success": true,
        "results": {
            "123": {"success": true, "message": "Download cancelled"},
            "124": {"success": false, "message": "Download not found"},
            ...
        }
    }
    """
    try:
        data = request.get_json()
        download_ids = data.get('download_ids', [])
        
        if not download_ids:
            return jsonify({
                'success': False,
                'error': 'download_ids array is required'
            }), 400
        
        dm_service = get_download_management_service()
        results = {}
        
        for download_id in download_ids:
            try:
                result = dm_service.cancel_download(download_id)
                results[str(download_id)] = result
            except Exception as e:
                results[str(download_id)] = {
                    'success': False,
                    'error': str(e)
                }
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in bulk cancel: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/bulk/retry', methods=['POST'])
def bulk_retry():
    """
    Retry multiple failed downloads.
    
    Request JSON:
    {
        "download_ids": [123, 124, 125]  # Optional: retry specific IDs
    }
    
    If no IDs provided, retries all failed downloads.
    
    Returns:
    {
        "success": true,
        "retried": 5,
        "results": {...}
    }
    """
    try:
        data = request.get_json() or {}
        download_ids = data.get('download_ids')
        dm_service = get_download_management_service()
        
        # If no IDs provided, get all failed downloads
        if not download_ids:
            failed_downloads = dm_service.queue_manager.get_queue(status_filter='FAILED')
            download_ids = [d['id'] for d in failed_downloads]
        
        results = {}
        success_count = 0
        
        for download_id in download_ids:
            try:
                download = dm_service.queue_manager.get_download(download_id)
                if download and download['status'] == 'FAILED':
                    dm_service.queue_manager.update_download(download_id, {
                        'status': 'QUEUED',
                        'retry_count': 0,
                        'last_error': None,
                        'failed_stage': None
                    })
                    results[str(download_id)] = {'success': True, 'message': 'Retry initiated'}
                    success_count += 1
                else:
                    results[str(download_id)] = {
                        'success': False, 
                        'message': 'Not in FAILED state'
                    }
            except Exception as e:
                results[str(download_id)] = {
                    'success': False,
                    'error': str(e)
                }
        
        return jsonify({
            'success': True,
            'retried': success_count,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in bulk retry: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@download_management_bp.route('/queue/clear', methods=['POST'])
def clear_queue():
    """
    Clear download queue entries for recovery.

    Request JSON (optional):
    {
        "include_active": true,        # Include active DOWNLOADING items
        "include_imported": false,     # Also remove imported history entries
        "statuses": ["FAILED", ...]   # Custom statuses to clear
    }
    """
    try:
        data = request.get_json() or {}
        include_active = bool(data.get('include_active', False))
        include_imported = bool(data.get('include_imported', False))
        statuses = data.get('statuses')

        if statuses is not None and not isinstance(statuses, list):
            return jsonify({
                'success': False,
                'error': 'statuses must be an array'
            }), 400

        dm_service = get_download_management_service()
        result = dm_service.clear_queue(
            include_active=include_active,
            include_imported=include_imported,
            statuses=statuses
        )

        status_code = 200 if result.get('success', False) else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Error clearing download queue: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# CLEANUP ENDPOINTS
# ============================================================================

@download_management_bp.route('/queue/cleanup', methods=['POST'])
def cleanup_queue():
    """
    Cleanup old completed/failed downloads.
    
    Query Parameters:
    - days: Remove items older than N days (default: 7)
    - status: Only cleanup items with this status (default: FAILED)
    
    Returns:
    {
        "success": true,
        "removed": 12,
        "message": "Cleanup complete"
    }
    """
    try:
        days = int(request.args.get('days', 7))
        status_filter = request.args.get('status', 'FAILED')
        
        dm_service = get_download_management_service()
        
        # Get old items
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_items = dm_service.queue_manager.get_queue(status_filter=status_filter)
        removed_count = 0
        
        for item in old_items:
            item_date = datetime.fromisoformat(item['created_at'])
            if item_date < cutoff_date:
                # Remove from queue
                dm_service.queue_manager.delete_download(item['id'])
                removed_count += 1
        
        return jsonify({
            'success': True,
            'removed': removed_count,
            'message': f'Removed {removed_count} old {status_filter} downloads'
        })
        
    except Exception as e:
        logger.error(f"Error in cleanup: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


logger.info("Download Management API initialized")
