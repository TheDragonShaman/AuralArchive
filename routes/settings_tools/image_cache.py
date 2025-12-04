"""
Image Cache Routes - AuralArchive

Expose cache statistics plus clear/preload actions for author artwork from the
settings interface.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from flask import Blueprint, jsonify, request

from services.image_cache import (
    get_image_cache_service,
    preload_author_images_from_database,
)
from utils.logger import get_module_logger

cache_management_bp = Blueprint('cache_management', __name__)
logger = get_module_logger("Route.Settings.ImageCache")

@cache_management_bp.route('/image-cache/stats')
def get_image_cache_stats():
    """Get image cache statistics for the settings page."""
    try:
        cache_service = get_image_cache_service()
        stats = cache_service.get_cache_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@cache_management_bp.route('/image-cache/clear', methods=['POST'])
def clear_image_cache():
    """Clear all cached images."""
    try:
        cache_service = get_image_cache_service()
        success = cache_service.clear_cache()
        
        if success:
            logger.info("Image cache cleared successfully")
            return jsonify({
                'success': True,
                'message': 'Image cache cleared successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to clear image cache'
            }), 500
            
    except Exception as e:
        logger.error(f"Error clearing image cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@cache_management_bp.route('/image-cache/preload', methods=['POST'])
def preload_image_cache():
    """Preload all author images into cache."""
    try:
        logger.info("Starting author image preload...")
        results = preload_author_images_from_database()
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        return jsonify({
            'success': True,
            'message': f'Preloaded {success_count}/{total_count} author images',
            'total_images': total_count,
            'successful': success_count,
            'failed': total_count - success_count
        })
        
    except Exception as e:
        logger.error(f"Error preloading author images: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
