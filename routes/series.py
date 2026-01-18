"""
Module Name: series.py
Author: TheDragonShaman
Created: July 25, 2025
Last Modified: December 23, 2025
Description:
    Series routes for views and APIs that sync Audible metadata and missing books.
Location:
    /routes/series.py

"""
from collections import Counter
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from services.service_manager import get_database_service
from services.audible.audible_service_manager import get_audible_manager
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Series")

series_bp = Blueprint('series', __name__)


def _analyze_series_authors(books):
    """Determine primary author and ranked author candidates for a series."""
    try:
        author_counter = Counter()

        for book in books or []:
            author = (book.get('author') or '').strip()
            if not author or author.lower() == 'unknown author':
                continue
            author_counter[author] += 1

        if not author_counter:
            return None, []

        ranked = sorted(author_counter.items(), key=lambda item: (-item[1], item[0].lower()))
        primary_author = ranked[0][0]
        candidates = [author for author, _ in ranked]
        return primary_author, candidates

    except Exception as exc:
        logger.debug("Author analysis failed: %s", exc)
        return None, []

@series_bp.route('/')
@login_required
def series_list():
    """Display all series in the library"""
    try:
        logger.info("Series list page accessed")
        return render_template('series.html')
    except Exception as e:
        logger.error("Error loading series list page: %s", e)
        return render_template('error.html', error=str(e)), 500


@series_bp.route('/<series_asin>')
def series_detail(series_asin):
    """Display details of a specific series"""
    try:
        logger.info("Series detail page accessed: %s", series_asin)
        return render_template('series_detail.html', series_asin=series_asin)
    except Exception as e:
        logger.error("Error loading series detail page: %s", e)
        return render_template('error.html', error=str(e)), 500


@series_bp.route('/api/list')
def api_series_list():
    """API endpoint to get all series with statistics"""
    try:
        db_service = get_database_service()
        
        # Sync series library status before returning results
        try:
            updated = db_service.series.sync_library_status()
            logger.debug("Synced series library status: %s records updated", updated)
        except Exception as e:
            logger.warning("Failed to sync series library status: %s", e)
        
        # Get all series using the new series operations
        series_list = db_service.series.get_all_series()
        
        return jsonify({
            'success': True,
            'series': series_list,
            'total_series': len(series_list)
        })
        
    except Exception as e:
        logger.error("Error fetching series list: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/<series_asin>/books')
def api_series_books(series_asin):
    """API endpoint to get all books in a specific series"""
    try:
        db_service = get_database_service()
        
        logger.info("Fetching series books for: %s", series_asin)
        
        # Sync series library status before returning results
        try:
            updated = db_service.series.sync_library_status()
            logger.debug("Synced series library status: %s records updated", updated)
        except Exception as e:
            logger.warning("Failed to sync series library status: %s", e)
        
        series_metadata = db_service.series.get_series_by_asin(series_asin)
        logger.debug("Series metadata loaded", extra={
            "series_asin": series_asin,
            "has_cover": bool(series_metadata and series_metadata.get('cover_url'))
        })
        
        if not series_metadata:
            return jsonify({
                'success': False,
                'error': 'Series not found'
            }), 404
        
        books = db_service.series.get_series_books(series_asin)
        logger.debug("Retrieved series books", extra={
            "series_asin": series_asin,
            "book_count": len(books)
        })
        
        # Calculate statistics
        total_books = len(books)
        owned_books = sum(1 for book in books if book['in_library'])
        missing_books = total_books - owned_books

        primary_author, author_candidates = _analyze_series_authors(books)
        
        return jsonify({
            'success': True,
            'series_asin': series_asin,
            'series_title': series_metadata['series_title'],
            'series_cover_url': series_metadata.get('cover_url'),
            'books': books,
            'statistics': {
                'total_books': total_books,
                'owned_books': owned_books,
                'missing_books': missing_books,
                'completion_percentage': round((owned_books / total_books * 100), 1) if total_books > 0 else 0
            },
            'primary_author': primary_author,
            'author_candidates': author_candidates,
            'import_context_available': bool(primary_author)
        })
        
    except Exception as e:
        logger.error("Error fetching series books: %s", e, exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/search-missing', methods=['POST'])
def api_search_missing_books():
    """API endpoint to initiate search for missing books in a series"""
    try:
        data = request.get_json()
        series_asin = data.get('series_asin')
        
        if not series_asin:
            return jsonify({
                'success': False,
                'error': 'Series ASIN is required'
            }), 400
        
        db_service = get_database_service()
        
        missing_books = db_service.series.get_missing_books(series_asin)
        
        # TODO: Implement search functionality
        # This would integrate with your search service to find missing books
        
        logger.info("Search initiated for %s missing books in series: %s", len(missing_books), series_asin)
        
        return jsonify({
            'success': True,
            'message': f'Found {len(missing_books)} missing books',
            'series_asin': series_asin,
            'missing_books': missing_books
        })
        
    except Exception as e:
        logger.error("Error searching for missing books: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/sync-book-series', methods=['POST'])
def api_sync_book_series():
    """API endpoint to sync series data for a specific book"""
    try:
        data = request.get_json()
        book_asin = data.get('book_asin')
        
        if not book_asin:
            return jsonify({
                'success': False,
                'error': 'Book ASIN is required'
            }), 400
        
        audible_manager = get_audible_manager()
        
        db_service = get_database_service()
        if not audible_manager.initialize_series_service(db_service):
            return jsonify({
                'success': False,
                'error': 'Series service initialization failed - check Audible authentication'
            }), 500
        
        try:
            client = audible_manager.get_client()
            if not client:
                return jsonify({
                    'success': False,
                    'error': 'Failed to get Audible client'
                }), 500
            
            with client as c:
                book_metadata = c.get(
                    f"1.0/catalog/products/{book_asin}",
                    response_groups="relationships,product_desc,product_extended_attrs,media,rating"
                )
                
                logger.debug("Fetched Audible metadata", extra={
                    "book_asin": book_asin,
                    "has_relationships": 'relationships' in book_metadata
                })
                if 'product' in book_metadata:
                    product = book_metadata['product']
                    logger.debug("Audible product wrapper present", extra={
                        "book_asin": book_asin,
                        "has_relationships": 'relationships' in product
                    })
                    if 'relationships' in product:
                        logger.debug("Audible relationships count", extra={
                            "book_asin": book_asin,
                            "relationship_count": len(product.get('relationships', []))
                        })
                        for rel in product.get('relationships', []):
                            logger.debug(
                                "Audible relationship",
                                extra={
                                    "book_asin": book_asin,
                                    "relationship_type": rel.get('type'),
                                    "relationship_title": rel.get('title', 'N/A')[:50]
                                }
                            )
                
        except Exception as e:
            logger.error("Error fetching book metadata from Audible: %s", e)
            return jsonify({
                'success': False,
                'error': f'Failed to fetch book metadata: {str(e)}'
            }), 500
        
        result = audible_manager.sync_book_series(book_asin, book_metadata)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        logger.error("Error syncing book series: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/refresh-series/<series_asin>', methods=['POST'])
def api_refresh_series(series_asin):
    """API endpoint to refresh data for a specific series from Audible"""
    try:
        if not series_asin:
            return jsonify({
                'success': False,
                'error': 'Series ASIN is required'
            }), 400
        
        logger.info("Series refresh requested: %s", series_asin)
        
        audible_manager = get_audible_manager()
        db_service = get_database_service()
        
        if not audible_manager.initialize_series_service(db_service):
            return jsonify({
                'success': False,
                'error': 'Series service initialization failed - check Audible authentication'
            }), 500
        
        result = audible_manager.refresh_series(series_asin)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        logger.error("Error refreshing series: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/sync-all-series', methods=['POST'])
def api_sync_all_series():
    """API endpoint to sync series data for all books in the library"""
    try:
        # Handle both JSON and empty requests
        data = request.get_json(silent=True) or {}
        limit = data.get('limit')  # Optional limit for batch processing
        
        logger.info("Batch series sync requested")
        
        audible_manager = get_audible_manager()
        db_service = get_database_service()
        
        if not audible_manager.initialize_series_service(db_service):
            return jsonify({
                'success': False,
                'error': 'Series service initialization failed - check Audible authentication'
            }), 500
        
        result = audible_manager.sync_all_series(limit=limit)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error("Error in batch series sync: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@series_bp.route('/api/sync-library-status', methods=['POST'])
def api_sync_library_status():
    """API endpoint to sync series library status (in_library flags) for all series books"""
    try:
        db_service = get_database_service()
        
        logger.info("Series library status sync requested")
        
        updated = db_service.series.sync_library_status()
        
        return jsonify({
            'success': True,
            'records_updated': updated,
            'message': f'Synced library status for {updated} series books'
        })
        
    except Exception as e:
        logger.error("Error syncing library status: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
