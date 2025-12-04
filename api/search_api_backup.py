"""
Legacy Search API - AuralArchive

Historic version of the search endpoints retained for reference. Provides the
old automatic/fuzzy/manual search controls that have since been replaced.

Author: AuralArchive Development Team
Updated: December 4, 2025
"""

import asyncio
from datetime import datetime
from typing import Dict, List

from flask import Blueprint, jsonify, request

from services.service_manager import get_database_service
from utils.logger import get_module_logger

# Create blueprint
search_api_bp = Blueprint('search_api', __name__, url_prefix='/api/search')
logger = get_module_logger("API.SearchLegacy")

# Global service instances (will be initialized in app.py)
automatic_search_service = None
database_service = None
enhanced_search_service = None

def init_search_services(auto_search_svc, manual_search_svc, db_service, enhanced_search_svc=None):
    """Initialize search services for the API"""
    global automatic_search_service, manual_search_service, database_service, enhanced_search_service
    automatic_search_service = auto_search_svc
    database_service = db_service
    enhanced_search_service = enhanced_search_svc

@search_api_bp.route('/automatic/status', methods=['GET'])
def get_automatic_search_status():
    """Get automatic search service status"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        status = automatic_search_service.get_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting automatic search status: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/start', methods=['POST'])
def start_automatic_search():
    """Start the automatic search service"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        success = automatic_search_service.start()
        if success:
            return jsonify({'message': 'Automatic search service started', 'success': True})
        else:
            return jsonify({'message': 'Failed to start automatic search service', 'success': False}), 500
            
    except Exception as e:
        logger.error(f"Error starting automatic search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/stop', methods=['POST'])
def stop_automatic_search():
    """Stop the automatic search service"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        success = automatic_search_service.stop()
        if success:
            return jsonify({'message': 'Automatic search service stopped', 'success': True})
        else:
            return jsonify({'message': 'Failed to stop automatic search service', 'success': False}), 500
            
    except Exception as e:
        logger.error(f"Error stopping automatic search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/pause', methods=['POST'])
def pause_automatic_search():
    """Pause the automatic search service"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        automatic_search_service.pause()
        return jsonify({'message': 'Automatic search service paused', 'success': True})
        
    except Exception as e:
        logger.error(f"Error pausing automatic search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/resume', methods=['POST'])
def resume_automatic_search():
    """Resume the automatic search service"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        automatic_search_service.resume()
        return jsonify({'message': 'Automatic search service resumed', 'success': True})
        
    except Exception as e:
        logger.error(f"Error resuming automatic search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/queue', methods=['GET'])
def get_search_queue():
    """Get current automatic search queue"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        queue = automatic_search_service.get_search_queue()
        return jsonify({'queue': queue, 'count': len(queue)})
        
    except Exception as e:
        logger.error(f"Error getting search queue: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/force/<int:book_id>', methods=['POST'])
def force_search_book(book_id):
    """Force immediate search for a specific book"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        success = automatic_search_service.force_search_book(book_id)
        if success:
            return jsonify({'message': f'Forced search queued for book {book_id}', 'success': True})
        else:
            return jsonify({'message': f'Failed to queue search for book {book_id}', 'success': False}), 404
            
    except Exception as e:
        logger.error(f"Error forcing search for book {book_id}: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/config', methods=['GET'])
def get_automatic_search_config():
    """Get automatic search configuration"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        status = automatic_search_service.get_status()
        return jsonify(status.get('configuration', {}))
        
    except Exception as e:
        logger.error(f"Error getting automatic search config: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/automatic/config', methods=['POST'])
def update_automatic_search_config():
    """Update automatic search configuration"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        config_data = request.get_json()
        if not config_data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        success = automatic_search_service.update_configuration(config_data)
        if success:
            return jsonify({'message': 'Configuration updated', 'success': True})
        else:
            return jsonify({'message': 'Failed to update configuration', 'success': False}), 500
            
    except Exception as e:
        logger.error(f"Error updating automatic search config: {e}")
        return jsonify({'error': str(e)}), 500

# Fuzzy Search API Endpoints

@search_api_bp.route('/fuzzy/search', methods=['POST'])
def fuzzy_search():
    """Perform fuzzy search with intelligent query parsing"""
    try:
        
        if not fuzzy_search_service:
            return jsonify({'error': 'Fuzzy search service not available'}), 503
        
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Query parameter required'}), 400
        
        query = data['query']
        search_options = data.get('options', {})
        
        # Perform fuzzy search
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(
            fuzzy_search_service.search(query, **search_options)
        )
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error performing fuzzy search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/fuzzy/suggestions', methods=['POST'])
def fuzzy_suggestions():
    """Get search suggestions for autocomplete"""
    try:
        
        if not fuzzy_search_service:
            return jsonify({'error': 'Fuzzy search service not available'}), 503
        
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Query parameter required'}), 400
        
        partial_query = data['query']
        
        # Get suggestions
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        suggestions = loop.run_until_complete(
            fuzzy_search_service.get_suggestions(partial_query)
        )
        
        return jsonify({
            'success': True,
            'query': partial_query,
            'suggestions': suggestions
        })
        
    except Exception as e:
        logger.error(f"Error getting fuzzy suggestions: {e}")
        return jsonify({'error': str(e)}), 500

# Manual Search API Endpoints

@search_api_bp.route('/manual/search', methods=['POST'])
def manual_search():
    """Perform manual search for downloadable audiobooks"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Query parameter required'}), 400
        
        query = data['query']
        search_options = data.get('options', {})
        use_fuzzy = data.get('use_fuzzy', False)  # Option to use fuzzy search
        
        # Use fuzzy search if requested and available
        if use_fuzzy:
            
            if fuzzy_search_service:
                # Perform async fuzzy search
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                results = loop.run_until_complete(
                    fuzzy_search_service.search(query, **search_options)
                )
                
                # Add fuzzy search indicator
                results['search_type'] = 'fuzzy'
                return jsonify(results)
        
        # Fallback to regular manual search
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(
            manual_search_service.search(query, **search_options)
        )
        
        results['search_type'] = 'manual'
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error performing manual search: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/manual/book/<int:book_id>', methods=['POST'])
def interactive_search_book(book_id):
    """Perform interactive search for a specific book by ID - Sonarr style"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        if not database_service:
            return jsonify({'error': 'Database service not available'}), 503
        
        # Get book details from database
        books = database_service.get_all_books()
        book = next((b for b in books if b.get('ID') == book_id), None)
        
        if not book:
            return jsonify({'error': f'Book with ID {book_id} not found'}), 404
        
        # Build search query from book metadata
        title = book.get('Title', '').strip()
        author = book.get('Author', '').strip()
        
        if not title:
            return jsonify({'error': 'Book title is required for search'}), 400
        
        # Create comprehensive search query
        search_query = f"{title}"
        if author:
            search_query += f" {author}"
        
        # Add series info if available
        series = book.get('Series', '').strip()
        sequence = book.get('Sequence', '').strip()
        if series and series != 'N/A':
            search_query += f" {series}"
            # Add book number if available
            if sequence and sequence != 'N/A' and sequence != '':
                # Try different book number formats for better matching
                search_query += f" Book {sequence}"
        
        search_options = {
            'book_id': book_id,
            'title': title,
            'author': author,
            'series': series,
            'sequence': sequence
        }
        
        logger.info(f"Interactive search for book {book_id}: '{search_query}'")
        
        # Perform search
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(
            manual_search_service.search(search_query, **search_options)
        )
        
        # Add book metadata to response
        results['book_info'] = {
            'id': book_id,
            'title': title,
            'author': author,
            'series': series,
            'sequence': sequence,
            'search_query': search_query
        }
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error performing interactive search for book {book_id}: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/manual/preview', methods=['POST'])
def preview_download():
    """Preview download for a search result"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        result_data = request.get_json()
        if not result_data:
            return jsonify({'error': 'Result data required'}), 400
        
        preview = manual_search_service.preview_download(result_data)
        return jsonify(preview)
        
    except Exception as e:
        logger.error(f"Error previewing download: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/manual/download', methods=['POST'])
def initiate_manual_download():
    """Initiate download for a selected result with intent-based system"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        # Import intent service
        # DownloadIntentService has been integrated into ClientManager
        
        data = request.get_json()
        if not data or 'result' not in data:
            return jsonify({'error': 'Result data required'}), 400
        
        result = data['result']
        book_info = data.get('book_info')  # Book metadata from interactive search
        
        # Create download intent with full book metadata
        intent_data = {
            'title': result.get('title', 'Unknown'),
            'source': 'manual_search'
        }
        
        # Check if we have book metadata for ASIN and clean data
        if book_info:
            # If book_info already has ASIN, use it directly (e.g., for testing or external data)
            if 'asin' in book_info:
                intent_data.update({
                    'asin': book_info.get('asin', ''),
                    'title': book_info.get('title', intent_data['title']),
                    'author': book_info.get('author', ''),
                    'narrator': book_info.get('narrator', ''),
                    'expected_duration_sec': book_info.get('expected_duration_sec')
                })
                logger.info(f"Manual download with provided book metadata - ASIN: {intent_data.get('asin')}")
            # If book_info has database ID, try to look up full data
            elif 'id' in book_info:
                database_service = get_database_service()
                if database_service and hasattr(database_service, 'get_book_by_id'):
                    book = database_service.get_book_by_id(book_info['id'])
                    if book:
                        intent_data.update({
                            'asin': book.get('ASIN', ''),
                            'title': book.get('Title', book_info.get('title', '')),
                            'author': book.get('Author', book_info.get('author', '')),
                            'narrator': book.get('Narrator', ''),
                            'expected_duration_sec': book.get('Duration_sec')
                        })
                        logger.info(f"Manual download with database book metadata - ASIN: {intent_data.get('asin')}")
        
        # Add torrent information
        if 'magnetUrl' in result:
            intent_data['magnet_uri'] = result['magnetUrl']
        elif 'downloadUrl' in result:
            intent_data['torrent_url'] = result['downloadUrl']
        
        # Create download intent using the download service
        if not download_service:
            return jsonify({'error': 'Download service not available'}), 503
            
        # Use intent-based download
        success, message = download_service.download_torrent(
            torrent_source=result.get('magnetUrl') or result.get('downloadUrl'),
            title=intent_data['title'],
            client_name=data.get('client_name'),
            asin=intent_data.get('asin'),
            author=intent_data.get('author'),
            narrator=intent_data.get('narrator'),
            expected_duration_sec=intent_data.get('expected_duration_sec')
        )
        
        return jsonify({
            'success': success,
            'message': message,
            'title': intent_data['title'],
            'asin': intent_data.get('asin')
        })
        
    except Exception as e:
        logger.error(f"Error initiating manual download: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/manual/suggestions', methods=['GET'])
def get_search_suggestions():
    """Get search suggestions"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        query = request.args.get('q', '')
        if not query:
            return jsonify({'suggestions': []})
        
        suggestions = manual_search_service.get_search_suggestions(query)
        return jsonify({'suggestions': suggestions})
        
    except Exception as e:
        logger.error(f"Error getting search suggestions: {e}")
        return jsonify({'error': str(e)}), 500

# General Search API Endpoints

@search_api_bp.route('/providers', methods=['GET'])
def get_available_providers():
    """Get list of available search providers"""
    try:
        # ClientManager not available - return empty providers list
        providers = []
        return jsonify({'providers': providers})
        
    except Exception as e:
        logger.error(f"Error getting available providers: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/books/wanted', methods=['GET'])
def get_wanted_books():
    """Get all books with 'Wanted' status"""
    try:
        if not database_service:
            return jsonify({'error': 'Database service not available'}), 503
        
        wanted_books = database_service.get_books_by_status("Wanted")
        return jsonify({
            'books': wanted_books,
            'count': len(wanted_books)
        })
        
    except Exception as e:
        logger.error(f"Error getting wanted books: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/books/<int:book_id>/status', methods=['PUT'])
def update_book_status(book_id):
    """Update book status"""
    try:
        if not database_service:
            return jsonify({'error': 'Database service not available'}), 503
        
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'error': 'Status parameter required'}), 400
        
        new_status = data['status']
        success = database_service.update_book_status(book_id, new_status)
        
        if success:
            return jsonify({
                'message': f'Book status updated to {new_status}',
                'success': True,
                'book_id': book_id,
                'new_status': new_status
            })
        else:
            return jsonify({
                'message': f'Failed to update book status',
                'success': False
            }), 404
            
    except Exception as e:
        logger.error(f"Error updating book status: {e}")
        return jsonify({'error': str(e)}), 500

@search_api_bp.route('/test', methods=['GET'])
def test_search_api():
    """Test endpoint for search API"""
    try:
        status = {
            'search_api': 'active',
            'automatic_search_available': automatic_search_service is not None,
            'manual_search_available': manual_search_service is not None,
            'database_available': database_service is not None,
            'timestamp': str(datetime.now())
        }
        
        if automatic_search_service:
            auto_status = automatic_search_service.get_status()
            status['automatic_search_status'] = {
                'running': auto_status.get('running', False),
                'paused': auto_status.get('paused', False),
                'queue_size': auto_status.get('queue_size', 0)
            }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error in search API test: {e}")
        return jsonify({'error': str(e)}), 500
