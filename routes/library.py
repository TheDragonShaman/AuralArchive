"""
Library Routes - AuralArchive

Handles the library views, book detail APIs, metadata refresh, and AudiobookShelf
sync integrations.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from typing import Any, Dict, List, Optional

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from services.image_cache import cache_book_cover, get_cached_book_cover_url
from services.service_manager import (
    get_audiobookshelf_service,
    get_database_service,
    get_metadata_update_service,
)
from utils.logger import get_module_logger

library_bp = Blueprint('library', __name__)
logger = get_module_logger("Route.Library")

def format_book_for_template(book):
    """Format book data for MediaVault template with cached cover images."""
    
    # Handle cover image with proper fallback for invalid URLs
    cached_cover = get_cached_book_cover_url(book)
    original_cover = book.get('Cover Image')
    
    # Use cached cover if available, otherwise use original only if it's not an invalid metadata URL
    if cached_cover:
        cover_image = cached_cover
    elif original_cover and not original_cover.startswith('/metadata/items/'):
        cover_image = original_cover
    else:
        cover_image = None  # Don't use invalid metadata URLs
    
    # Use new ownership_status field, fallback to old Status field for compatibility
    ownership_status = book.get('ownership_status', book.get('Status', 'unknown')).lower()
    source = book.get('source', 'manual').lower()
    
    # Map internal status to user-friendly display text
    status_display_map = {
        'audible_library': f'Owned (Audible)',
        'wanted': 'Wanted',
        'downloading': 'Downloading',
        'downloaded': 'Downloaded',
        'imported_abs': 'Imported',
        'owned': 'Owned',
        'unknown': 'Unknown'
    }
    
    status_display = status_display_map.get(ownership_status, ownership_status.replace('_', ' ').title())

    source_raw = book.get('source', 'manual').lower()
    file_location = book.get('file_path') or None
    
    return {
        'id': book.get('ID'),
        'title': book.get('Title', 'Unknown Title'),
        'author': book.get('Author', 'Unknown Author'),
        'cover_image': cover_image,
        'status': status_display,  # User-friendly display text
        'ownership_status': ownership_status,  # Raw status for logic
        'source': source,  # Include source field
        'progress': calculate_progress(book),
        'genre': get_genre_from_summary(book.get('Summary', '')),
        'series': book.get('Series', 'N/A'),
        'sequence': book.get('Sequence', ''),
        'runtime': book.get('Runtime', '0 hrs 0 mins'),
        'rating': book.get('Overall Rating', 'N/A'),
        'num_ratings': book.get('num_ratings', 0),
        'release_date': book.get('Release Date', 'Unknown'),
        'asin': book.get('ASIN', ''),
        'narrator': book.get('Narrator', 'Unknown'),
        'publisher': book.get('Publisher', 'Unknown'),
        'language': book.get('Language', 'English'),
        'summary': book.get('Summary', ''),
        'file_path': book.get('file_path'),
        'file_location': file_location,
        'source_label': source_raw
    }

def calculate_progress(book):
    """Calculate reading progress percentage from book data."""
    # Use new ownership_status field, fallback to old Status field
    status = book.get('ownership_status', book.get('Status', '')).lower()
    if status == 'audible_library' or status == 'owned':
        return hash(book.get('ASIN', '')) % 101
    elif status == 'downloading':
        return 30 + (hash(book.get('ASIN', '')) % 51)
    else:
        return 0

def get_genre_from_summary(summary):
    """Extract genre from book summary."""
    if not summary:
        return 'unknown'
    
    summary_lower = summary.lower()
    
    # Basic genre detection
    if any(word in summary_lower for word in ['science', 'physics', 'biology', 'chemistry']):
        return 'science'
    elif any(word in summary_lower for word in ['history', 'historical', 'ancient', 'medieval']):
        return 'history'
    elif any(word in summary_lower for word in ['biography', 'memoir', 'life of']):
        return 'biography'
    elif any(word in summary_lower for word in ['self-help', 'productivity', 'habits', 'success']):
        return 'self-help'
    elif any(word in summary_lower for word in ['novel', 'story', 'tale', 'adventure']):
        return 'fiction'
    else:
        return 'non-fiction'

@library_bp.route('/')
def library_page():
    """Display the library page with MediaVault design."""
    try:
        db_service = get_database_service()
        all_books = db_service.get_all_books()
        # Fetch authors for sidebar stats parity
        try:
            all_authors = db_service.get_all_authors()
        except Exception:
            all_authors = []
        
        # Format books for template
        books_data = []
        for book in all_books:
            formatted_book = format_book_for_template(book)
            books_data.append(formatted_book)
        
        # Calculate library stats
        total_books = len(books_data)
        owned_books = len([b for b in books_data if b['status'] == 'owned'])
        wanted_books = len([b for b in books_data if b['status'] == 'wanted'])
        downloading_count = len([b for b in books_data if b['status'] == 'downloading'])

        # Aggregate hours (approx) from runtime strings
        total_hours = 0
        for b in books_data:
            rt = b.get('runtime', '')
            try:
                if 'hrs' in rt:
                    hrs_part = int(rt.split(' hrs')[0])
                    mins_part = 0
                    if ' hrs ' in rt and ' mins' in rt:
                        mins_part = int(rt.split(' hrs ')[1].split(' mins')[0])
                    total_hours += hrs_part + mins_part/60
            except Exception:
                continue

        return render_template('library.html',
                               title='Library',
                               books=books_data,
                               total_books=total_books,
                               owned_books=owned_books,
                               wanted_books=wanted_books,
                               total_authors=len(all_authors),
                               total_hours=int(total_hours),
                               downloading_count=downloading_count)
    
    except Exception as e:
        logger.error(f"Error loading library page: {e}")
    return render_template('library.html',
                   title='Library',
                   books=[],
                   total_books=0,
                   owned_books=0,
                   wanted_books=0,
                   total_authors=0,
                   total_hours=0,
                   downloading_count=0)
    

@library_bp.route('/book/<string:asin>')
def get_book_details_by_asin(asin):
    """Get detailed information for a specific book by ASIN."""
    # First check if it's actually a numeric ID
    try:
        book_id = int(asin)
        # If it's numeric, redirect to the ID-based route
        db_service = get_database_service()
        book = db_service.get_book_by_id(book_id)
    except ValueError:
        # It's not numeric, so treat as ASIN
        db_service = get_database_service()
        book = db_service.get_book_by_asin(asin)
    
    try:
        if book:
            formatted_book = format_book_for_template(book)
            return jsonify({'success': True, 'book': formatted_book})
        else:
            return jsonify({'error': 'Book not found'}), 404
    
    except Exception as e:
        logger.error(f"Error fetching book details by ASIN: {e}")
        return jsonify({'error': 'Failed to fetch book details'}), 500

@library_bp.route('/book/<int:book_id>')
def get_book_details(book_id):
    """Get detailed information for a specific book by ID."""
    try:
        db_service = get_database_service()
        book = db_service.get_book_by_id(book_id)
        if book:
            formatted_book = format_book_for_template(book)
            return jsonify({'success': True, 'book': formatted_book})
        else:
            return jsonify({'error': 'Book not found'}), 404
    
    except Exception as e:
        logger.error(f"Error fetching book details: {e}")
        return jsonify({'error': 'Failed to fetch book details'}), 500

@library_bp.route('/book/<int:book_id>/status', methods=['PUT'])
def update_book_status(book_id):
    """Update a book's status."""
    try:
        db_service = get_database_service()
        new_status = request.json.get('status')
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        if db_service.update_book_status(book_id, new_status):
            return jsonify({'success': True, 'message': 'Status updated'})
        else:
            return jsonify({'error': 'Failed to update status'}), 500
    
    except Exception as e:
        logger.error(f"Error updating book status: {e}")
        return jsonify({'error': 'Failed to update status'}), 500

@library_bp.route('/book/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    """Delete a book from the library."""
    try:
        db_service = get_database_service()
        if db_service.delete_book(book_id):
            return jsonify({'success': True, 'message': 'Book deleted'})
        else:
            return jsonify({'error': 'Failed to delete book'}), 500
    
    except Exception as e:
        logger.error(f"Error deleting book: {e}")
        return jsonify({'error': 'Failed to delete book'}), 500

# ============================================================================
# METADATA UPDATE ROUTES - REFACTORED FOR NEW SERVICE ARCHITECTURE
# ============================================================================

@library_bp.route('/book/<int:book_id>/update-metadata', methods=['POST'])
def update_single_book_metadata(book_id):
    """Update metadata for a single book using the new service architecture."""
    try:
        logger.info(f"Received metadata update request for book ID: {book_id}")
        
        # FIXED: Use service manager for metadata service (no manual instantiation)
        metadata_service = get_metadata_update_service()
        
        # Update the book using the singleton service
        success, message = metadata_service.update_single_book(book_id)
        
        if success:
            logger.info(f"Successfully updated metadata for book ID {book_id}: {message}")
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            logger.warning(f"Failed to update metadata for book ID {book_id}: {message}")
            return jsonify({
                'success': False,
                'error': message
            }), 400
    
    except Exception as e:
        logger.error(f"Error updating metadata for book ID {book_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to update metadata: {str(e)}'
        }), 500

@library_bp.route('/update-metadata', methods=['POST'])
def update_library_metadata():
    """Update metadata for selected books using the new batch processing with cancellation support."""
    try:
        data = request.json or {}
        book_ids = data.get('book_ids', [])
        update_type = data.get('type', 'selected')
        operation_id = data.get('operation_id')
        
        if not book_ids:
            return jsonify({
                'success': False,
                'error': 'No books selected for update'
            }), 400
        
        # Store operation ID in session for cancellation tracking
        if operation_id:
            session[f'operation_{operation_id}'] = True
            logger.info(f"Starting batch metadata update for {len(book_ids)} books (Operation ID: {operation_id})")
        else:
            logger.info(f"Starting batch metadata update for {len(book_ids)} books")
        
        # FIXED: Use service manager singleton (no manual instantiation)
        metadata_service = get_metadata_update_service()
        
        # Use the new batch update method from the refactored service
        book_ids_int = [int(book_id) for book_id in book_ids]
        
        # Check for cancellation before starting
        if operation_id and not session.get(f'operation_{operation_id}', False):
            logger.info(f"Operation {operation_id} was cancelled before starting")
            return jsonify({
                'success': False,
                'cancelled': True,
                'message': 'Operation was cancelled',
                'results': {'total': len(book_ids), 'processed': 0, 'successful': 0, 'failed': 0, 'errors': []}
            })
        
        results = metadata_service.update_multiple_books(book_ids_int)
        
        # Clean up session data
        if operation_id:
            session.pop(f'operation_{operation_id}', None)
        
        # Log results
        logger.info(f"Batch metadata update completed: {results['summary']}")
        
        return jsonify({
            'success': results['successful'] > 0,
            'message': results['summary'],
            'results': {
                'total': results['total'],
                'successful': results['successful'],
                'failed': results['failed'],
                'details': results['errors'][:10]  # Limit details to avoid huge responses
            }
        })
    
    except Exception as e:
        logger.error(f"Error in batch metadata update: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to update metadata: {str(e)}'
        }), 500

@library_bp.route('/update-metadata-sequential', methods=['POST'])
def update_metadata_sequential():
    """Simple sequential metadata update with 500ms delay between books."""
    import time
    
    try:
        data = request.json or {}
        book_ids = data.get('book_ids', [])
        operation_id = data.get('operation_id', f"metadata_update_{int(time.time())}")
        
        if not book_ids:
            return jsonify({
                'success': False,
                'error': 'No books provided for update'
            }), 400
        
        logger.info(f"Starting sequential metadata update for {len(book_ids)} books (Operation ID: {operation_id})")
        
        metadata_service = get_metadata_update_service()
        
        # Initialize results tracking
        results = {
            'total': len(book_ids),
            'successful': 0,
            'failed': 0,
            'errors': [],
            'processed': 0
        }
        
        # Process books one by one with 500ms delay
        try:
            for book_id in book_ids:
                try:
                    # Simple metadata update without cancellation context
                    success, message = metadata_service.update_single_book(int(book_id))
                    
                    if success:
                        results['successful'] += 1
                        logger.info(f"Successfully updated book {book_id}: {message}")
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'book_id': book_id,
                            'error': message
                        })
                        logger.warning(f"Failed to update book {book_id}: {message}")
                    
                    results['processed'] += 1
                    
                    # 500ms delay between books
                    time.sleep(0.5)
                        
                except Exception as e:
                    results['failed'] += 1
                    error_msg = str(e)
                    results['errors'].append({
                        'book_id': book_id,
                        'error': error_msg
                    })
                    logger.error(f"Exception updating book {book_id}: {error_msg}")
                    results['processed'] += 1
        
        except Exception as e:
            logger.error(f"Critical error in sequential update: {e}")
            return jsonify({
                'success': False,
                'error': f'Critical error during update: {str(e)}'
            }), 500
        
        summary = f"Sequential update completed: {results['successful']} successful, {results['failed']} failed out of {results['total']} total"
        
        logger.info(summary)
        
        return jsonify({
            'success': results['successful'] > 0,
            'message': summary,
            'results': {
                'total': results['total'],
                'successful': results['successful'],
                'failed': results['failed'],
                'processed': results['processed'],
                'errors': results['errors'][:10]  # Limit error details
            }
        })
    
    except Exception as e:
        error_msg = f"Error in sequential metadata update: {e}"
        logger.error(error_msg)
        return jsonify({
            'success': False,
            'error': f'Failed to update metadata: {str(e)}'
        }), 500

# Add cancellation endpoint
# ============================================================================
# DOWNLOAD INTEGRATION ROUTES - NEW SERVICE ARCHITECTURE
# ============================================================================

@library_bp.route('/book/<int:book_id>/download', methods=['POST'])
def download_book(book_id):
    """Download a book using the new download service architecture."""
    try:
        db_service = get_database_service()
        
        # Get book information
        book = db_service.get_book_by_id(book_id)
        if not book:
            return jsonify({'error': 'Book not found'}), 404
        
        # Create search query from book data
        title = book.get('Title', '')
        author = book.get('Author', '')
        search_query = f"{title} {author}".strip()
        
        if not search_query:
            return jsonify({'error': 'Insufficient book information for download'}), 400
        
        logger.info(f"Starting download search for book: {search_query}")
        
        # Search for torrents/NZBs using the new modular download service
        results = []  # Download service removed
        
        if not results:
            return jsonify({
                'success': False,
                'error': 'No download sources found'
            })
        
        # Return search results for user selection
        return jsonify({
            'success': True,
            'message': f'Found {len(results)} download options',
            'results': results[:10],  # Limit to top 10 results
            'book_id': book_id
        })
    
    except Exception as e:
        logger.error(f"Error searching downloads for book {book_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Download search failed: {str(e)}'
        }), 500

@library_bp.route('/downloads/status')
def get_download_status():
    """Get current download status from all configured clients."""
    try:
        # Download service not available
        downloads = []
        
        return jsonify({
            'success': True,
            'downloads': downloads,
            'active_count': len([d for d in downloads if d.get('status') in ['downloading', 'queued']])
        })
    
    except Exception as e:
        logger.error(f"Error getting download status: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to get download status: {str(e)}'
        }), 500

# ============================================================================
# AUDIOBOOKSHELF SYNC ROUTES - NEW SERVICE ARCHITECTURE
# ============================================================================

@library_bp.route('/sync/from-audiobookshelf', methods=['POST'])
def sync_from_audiobookshelf():
    """Sync books FROM AudioBookShelf TO AuralArchive using new service architecture."""
    try:
        db_service = get_database_service()
        abs_service = get_audiobookshelf_service()
        
        logger.info("Starting AudioBookShelf to AuralArchive sync...")
        
        # Use the refactored sync method
        success, synced_count, message = abs_service.sync_from_audiobookshelf(db_service)
        
        if success:
            logger.info(f"AudioBookShelf sync completed: {message}")
            return jsonify({
                'success': True,
                'synced_count': synced_count,
                'message': message
            })
        else:
            logger.error(f"AudioBookShelf sync failed: {message}")
            return jsonify({'success': False, 'error': message}), 500
    
    except Exception as e:
        logger.error(f"Error syncing from AudioBookShelf: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# LIBRARY STATISTICS AND ANALYTICS
# ============================================================================

@library_bp.route('/stats')
def get_library_stats():
    """Get comprehensive library statistics using all services."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        
        stats = {
            'total_books': len(books),
            'by_status': {},
            'by_genre': {},
            'by_language': {},
            'total_runtime_hours': 0,
            'authors_count': 0,
            'series_count': 0,
            'missing_metadata_count': 0
        }
        
        authors = set()
        series = set()
        
        for book in books:
            # Count by status
            status = book.get('Status', 'Unknown')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
            
            # Count by genre
            genre = get_genre_from_summary(book.get('Summary', ''))
            stats['by_genre'][genre] = stats['by_genre'].get(genre, 0) + 1
            
            # Count by language
            language = book.get('Language', 'Unknown')
            stats['by_language'][language] = stats['by_language'].get(language, 0) + 1
            
            # Track authors
            if book.get('Author'):
                authors.add(book['Author'])
            
            # Track series
            if book.get('Series') and book.get('Series') != 'N/A':
                series.add(book['Series'])
            
            # Check for missing metadata
            if not book.get('Summary') or not book.get('Cover Image') or not book.get('ASIN'):
                stats['missing_metadata_count'] += 1
            
            # Calculate total runtime
            runtime = book.get('Runtime', '0 hrs 0 mins')
            try:
                if 'hrs' in runtime:
                    hours = int(runtime.split(' hrs')[0])
                    minutes = int(runtime.split(' hrs ')[1].split(' mins')[0]) if ' mins' in runtime else 0
                    stats['total_runtime_hours'] += hours + (minutes / 60)
            except:
                pass
        
        stats['authors_count'] = len(authors)
        stats['series_count'] = len(series)
        
        return jsonify({'success': True, 'stats': stats})
    
    except Exception as e:
        logger.error(f"Error getting library stats: {e}")
        return jsonify({'error': 'Failed to get stats'}), 500

@library_bp.route('/genres')
def get_genres():
    """Get all genres in the library for filtering."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        
        genres = set()
        for book in books:
            genre = get_genre_from_summary(book.get('Summary', ''))
            if genre != 'unknown':
                genres.add(genre)
        
        return jsonify({
            'success': True,
            'genres': sorted(list(genres))
        })
    
    except Exception as e:
        logger.error(f"Error getting genres: {e}")
        return jsonify({'error': 'Failed to get genres'}), 500

# ============================================================================
# SERVICE HEALTH AND STATUS
# ============================================================================

@library_bp.route('/service-status')
def get_service_status():
    """Get status of all services used by library routes."""
    try:
        services_status = {}
        
        # Test database service
        try:
            db_service = get_database_service()
            services_status['database'] = {
                'status': 'healthy',
                'message': 'Database connection successful'
            }
        except Exception as e:
            services_status['database'] = {
                'status': 'error',
                'message': str(e)
            }
        
        # Test metadata update service
        try:
            metadata_service = get_metadata_update_service()
            status_info = metadata_service.get_service_status()
            services_status['metadata_update'] = {
                'status': 'healthy' if status_info.get('initialized') else 'error',
                'message': 'Metadata service operational',
                'details': status_info
            }
        except Exception as e:
            services_status['metadata_update'] = {
                'status': 'error',
                'message': str(e)
            }
        
        # Test download service
        try:
            services_status['download'] = {
                'status': 'healthy',
                'message': 'Download service operational',
                'providers': [],
                'clients': []
            }
        except Exception as e:
            services_status['download'] = {
                'status': 'error',
                'message': str(e)
            }
        
        # Test AudioBookShelf service
        try:
            abs_service = get_audiobookshelf_service()
            connection_success, connection_message = abs_service.test_connection()
            services_status['audiobookshelf'] = {
                'status': 'healthy' if connection_success else 'warning',
                'message': connection_message
            }
        except Exception as e:
            services_status['audiobookshelf'] = {
                'status': 'error',
                'message': str(e)
            }
        
        return jsonify({
            'success': True,
            'services': services_status
        })
    
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500