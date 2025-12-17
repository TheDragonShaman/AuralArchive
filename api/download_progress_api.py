"""
Download Progress API - AuralArchive

Provides REST endpoints for polling download progress as an alternative to
SocketIO push updates.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from flask import Blueprint, request, jsonify
from services.audible.audible_service_manager import get_audible_manager
from utils.logger import get_module_logger

# Create blueprint
download_progress_api = Blueprint('download_progress_api', __name__)

# Initialize logger
logger = get_module_logger("Route.DownloadProgress")


@download_progress_api.route('/api/download-progress/<download_id>', methods=['GET'])
def get_download_progress(download_id):
    """
    Get progress for a specific download.
    
    Args:
        download_id: The unique identifier for the download
        
    Returns:
        JSON response with progress information
    """
    try:
        manager = get_audible_manager()
        audible_service = manager.library_service
        
        logger.debug("Download progress request", extra={
            "download_id": download_id,
            "service_id": id(audible_service),
            "store_size": len(audible_service.download_progress_store)
        })

        progress_data = audible_service.get_download_progress(download_id)
        
        return jsonify(progress_data)
        
    except Exception as e:
        logger.error(f"Error getting download progress for {download_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error getting download progress: {str(e)}'
        }), 500


@download_progress_api.route('/api/download-progress', methods=['GET'])
def get_all_download_progress():
    """
    Get progress for all active downloads.
    
    Returns:
        JSON response with all download progress information
    """
    try:
        manager = get_audible_manager()
        audible_service = manager.library_service
        progress_data = audible_service.get_all_download_progress()
        
        return jsonify(progress_data)
        
    except Exception as e:
        logger.error(f"Error getting all download progress: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error getting download progress: {str(e)}'
        }), 500


@download_progress_api.route('/api/download-progress/<download_id>', methods=['DELETE'])
def clear_download_progress(download_id):
    """
    Clear progress data for a completed download.
    
    Args:
        download_id: The unique identifier for the download
        
    Returns:
        JSON response confirming deletion
    """
    try:
        manager = get_audible_manager()
        audible_service = manager.library_service
        audible_service.clear_download_progress(download_id)
        
        return jsonify({
            'success': True,
            'message': f'Progress data cleared for download {download_id}'
        })
        
    except Exception as e:
        logger.error(f"Error clearing download progress for {download_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error clearing download progress: {str(e)}'
        }), 500