"""
Audible Download Queue API - AuralArchive

Unified download queue integration for Audible books.
Routes Audible download requests through the main download queue system
instead of using separate streaming downloads.

Author: AuralArchive Development Team  
Created: September 19, 2025
Updated: November 4, 2025 - Migrated to unified download queue
"""

from flask import Blueprint, request, jsonify

from services.service_manager import get_database_service
from services.audible.ownership_validator import assess_audible_ownership, fetch_audible_library_entry
from utils.logger import get_module_logger

# Create blueprint
streaming_download_api = Blueprint('streaming_download_api', __name__)

# Initialize logger
logger = get_module_logger("API.StreamingDownload")



@streaming_download_api.route('/api/stream-download', methods=['POST'])
def start_streaming_download():
    """
    Queue an Audible book for download through the unified download pipeline.
    
    This endpoint creates a download queue entry with download_type='audible'.
    The DownloadManagementService handles the actual download, conversion, and import.
    
    Expected JSON payload:
    {
        "asin": "B123456789",       // Required: Audible ASIN
        "title": "Book Title",       // Optional: Book title for display
        "author": "Author Name",     // Optional: Author name
        "format": "aaxc",            // Optional: Download format (aaxc, aax, aax-fallback)
        "quality": "best",           // Optional: Download quality (best, high, normal)
        "priority": 5                // Optional: Queue priority (1-10, default 5)
    }
    
    Returns:
        JSON response with download queue ID and status
    """
    try:
        logger.debug("Streaming download endpoint called")
        data = request.get_json()
        logger.debug("Streaming download payload: %s", data)
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        # Extract required fields
        asin = data.get('asin')
        if not asin:
            return jsonify({
                'success': False,
                'error': 'ASIN is required'
            }), 400
        
        # Extract optional fields
        title = data.get('title', f'Audible Book {asin}')
        author = data.get('author', 'Unknown Author')
        format_type = data.get('format', 'aaxc')
        quality = data.get('quality', 'best')
        priority = data.get('priority', 5)
        
        database_service = get_database_service()
        audible_entry = fetch_audible_library_entry(database_service, asin)
        owned_via_audible, ownership_details = assess_audible_ownership(audible_entry)

        if not owned_via_audible:
            reason = ownership_details.get('reason') if ownership_details else 'Ownership verification failed.'
            logger.warning(f"Blocked Audible queue request for ASIN {asin}: {reason}")
            return jsonify({
                'success': False,
                'error': 'Audible ownership verification failed',
                'message': reason,
                'asin': asin,
                'ownership_details': ownership_details
            }), 403

        logger.info(
            "Queuing Audible download asin=%s title='%s' format=%s quality=%s priority=%s",
            asin,
            title,
            format_type,
            quality,
            priority,
        )
        
        # Get DownloadManagementService
        from services.service_manager import get_download_management_service
        download_service = get_download_management_service()
        
        # Add to queue with download_type='audible'
        result = download_service.add_to_queue(
            book_asin=asin,
            priority=priority,
            download_type='audible',
            title=title,
            author=author,
            audible_format=format_type,
            audible_quality=quality,
            ownership_details=ownership_details
        )
        
        if result['success']:
            logger.info(
                "Queued Audible download asin=%s queue_id=%s",
                asin,
                result.get('download_id')
            )
            return jsonify({
                'success': True,
                'download_id': result['download_id'],
                'message': f"Queued download for {title}",
                'asin': asin,
                'title': title,
                'status': 'QUEUED',
                'ownership_details': ownership_details
            })
        else:
            logger.error(
                "Streaming API failed to queue Audible download: asin=%s, error=%s",
                asin,
                result.get('message')
            )
            return jsonify({
                'success': False,
                'error': result.get('message', 'Failed to queue download')
            }), 400
        
    except Exception as e:
        logger.error(f"Error queueing Audible download: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error queueing download'
        }), 500




@streaming_download_api.route('/api/stream-download/status', methods=['GET'])
def get_streaming_downloads_status():
    """
    Get status of downloads in the queue (for backward compatibility).
    
    This endpoint now queries the download queue instead of tracking
    separate streaming downloads.
    
    Returns:
        JSON response with download queue information
    """
    try:
        from services.service_manager import get_download_management_service
        download_service = get_download_management_service()
        
        # Get all Audible downloads from queue
        all_downloads = download_service.get_queue()
        audible_downloads = [d for d in all_downloads if d.get('download_type') == 'audible']
        
        # Count active (not terminal states)
        active_states = ['QUEUED', 'SEARCHING', 'FOUND', 'DOWNLOADING', 'COMPLETE', 'CONVERTING', 'IMPORTING']
        active_count = len([d for d in audible_downloads if d.get('status') in active_states])
        
        # Format downloads for response
        downloads_status = {}
        for download in audible_downloads:
            downloads_status[str(download['id'])] = {
                'asin': download.get('book_asin'),
                'title': download.get('title', 'Unknown'),
                'status': download.get('status'),
                'progress': download.get('progress_percentage', 0),
                'created_at': download.get('created_at'),
                'updated_at': download.get('updated_at')
            }
        
        return jsonify({
            'success': True,
            'active_downloads': active_count,
            'total_downloads': len(audible_downloads),
            'downloads': downloads_status
        })
        
    except Exception as e:
        logger.error(f"Error getting download status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error getting downloads status'
        }), 500


@streaming_download_api.route('/api/stream-download/<int:download_id>', methods=['GET'])
def get_download_status(download_id):
    """
    Get status of a specific download from the queue.
    
    Args:
        download_id: The download queue ID (integer)
    """
    try:
        from services.service_manager import get_download_management_service
        download_service = get_download_management_service()
        
        # Get download from queue
        download = download_service.queue_manager.get_download(download_id)
        
        if not download:
            return jsonify({
                'success': False,
                'error': 'Download not found'
            }), 404
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'asin': download.get('book_asin'),
            'title': download.get('title', 'Unknown'),
            'author': download.get('author', 'Unknown'),
            'status': download.get('status'),
            'progress': download.get('progress_percentage', 0),
            'created_at': download.get('created_at'),
            'updated_at': download.get('updated_at'),
            'download_type': download.get('download_type'),
            'error_message': download.get('error_message')
        })
        
    except Exception as e:
        logger.error(f"Error getting download status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@streaming_download_api.route('/api/test-socketio', methods=['GET'])
def test_socketio():
    """
    Test endpoint to verify SocketIO is working.
    """
    try:
        from app import socketio
        from datetime import datetime
        
        logger.debug("*** TESTING SOCKETIO EMISSION ***")
        
        def emit_test_event():
            """Function to emit test event in background task context"""
            logger.debug("*** SOCKETIO TEST EVENT EMITTED ***")
            socketio.emit('test_event', {
                'message': 'SocketIO test successful from background task!',
                'timestamp': datetime.now().isoformat()
            })
        
        # Use SocketIO background task instead of direct emit
        socketio.start_background_task(emit_test_event)
        
        return jsonify({
            'success': True,
            'message': 'SocketIO test event emitted via background task'
        })
        
    except Exception as e:
        logger.error(f"SocketIO test error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
