"""
Module Name: search.py
Author: TheDragonShaman
Created: July 24, 2025
Last Modified: December 23, 2025
Description:
    Catalog search routes and supporting APIs for Audible queries and download readiness.
Location:
    /routes/search.py

"""
from flask import Blueprint, render_template, request, jsonify, flash
from services.service_manager import (
    get_audible_service,
    get_database_service,
    get_metadata_update_service,
    get_config_service,
)
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
from utils.logger import get_module_logger

search_bp = Blueprint('search', __name__)
logger = get_module_logger("Routes.Search")

# ============================================================================
# UTILITY FUNCTIONS - ENHANCED
# ============================================================================

def format_search_result(
    book: Dict,
    in_library: bool = False,
    download_available: bool = False,
    library_status: str = 'not_in_library',
    library_book: Optional[Dict[str, Any]] = None,
) -> Dict:
    """Enhanced format search result for MediaVault template with download info."""
    library_record = library_book or {}
    record_id = (
        library_record.get('ID')
        or library_record.get('id')
        or book.get('ID')
        or book.get('id')
    )
    return {
        'id': record_id,
        'title': book.get('Title', book.get('title', 'Unknown Title')),
        'author': book.get('Author', book.get('author', 'Unknown Author')),
        'cover_image': book.get('Cover Image', book.get('cover_image')),
        'series': book.get('Series', book.get('series', 'N/A')),
        'sequence': book.get('Sequence', book.get('sequence', '')),
        'narrator': book.get('Narrator', book.get('narrator', 'Unknown')),
        'runtime': book.get('Runtime', book.get('runtime', '0 hrs 0 mins')),
        'rating': book.get('Overall Rating', book.get('rating', 'N/A')),
        'num_ratings': book.get('num_ratings', book.get('rating_count', 0)),
        'release_date': book.get('Release Date', book.get('release_date', 'Unknown')),
        'asin': book.get('ASIN', book.get('asin', '')),
        'publisher': book.get('Publisher', book.get('publisher', 'Unknown')),
        'language': book.get('Language', book.get('language', 'English')),
        'summary': book.get('Summary', book.get('summary', '')),
        'in_library': in_library,
        'library_status': library_status,
        'download_available': download_available,
        'ownership_status': (
            (library_record.get('ownership_status') if library_record else None)
            or book.get('ownership_status')
            or book.get('Status')
        ),
        'search_source': book.get('source', book.get('search_source', 'audible')),
        'enhanced_metadata': book.get('enhanced', False)
    }


def _is_audible_owned(status_value: Optional[str]) -> bool:
    """Return True when ownership status indicates the title is owned via Audible."""
    if not status_value:
        return False
    normalized = str(status_value).strip().lower()
    if not normalized:
        return False
    owned_tokens = {
        'audible_library',
        'audible_owned',
        'audible',
        'owned',
        'purchased',
    }
    return any(token in normalized for token in owned_tokens)

def enhance_search_results(results: List[Dict]) -> List[Dict]:
    """Enhance search results with additional metadata and download availability."""
    try:
        enhanced_results = []
        
        for book in results:
            # Mark Audible-owned items as downloadable (user-owned content)
            download_available = _is_audible_owned(
                book.get('ownership_status')
                or book.get('Status')
            )
            # Always allow items already in the library to surface a download affordance
            if not download_available and str(book.get('library_status', '')).lower() == 'in_library':
                download_available = True
            # If sourced from Audible and present in the library (even as wanted), allow download
            if (
                not download_available
                and str(book.get('search_source') or book.get('source') or '').lower() == 'audible'
                and str(book.get('library_status', '')).lower() in {'in_library', 'wanted'}
            ):
                download_available = True
            
            # Add enhancement flag
            enhanced_book = book.copy()
            enhanced_book['download_available'] = download_available
            enhanced_book['enhanced'] = True
            enhanced_results.append(enhanced_book)
        
        return enhanced_results
        
    except Exception as e:
        logger.warning(f"Failed to enhance search results: {e}")
        return results  # Return original results if enhancement fails

def get_search_analytics() -> Dict[str, Any]:
    """Get search analytics and performance metrics."""
    try:
        config_service = get_config_service()
        audible_service = get_audible_service()
        
        # Get API status
        api_status = audible_service.search.get_api_status() if hasattr(audible_service.search, 'get_api_status') else {}
        
        # Get configuration
        config_data = config_service.list_config()
        audible_config = config_data.get('audible', {})
        
        analytics = {
            'api_status': api_status,
            'max_results': int(audible_config.get('max_results', 25)),
            'default_region': audible_config.get('default_region', 'us'),
            'search_features': {
                'download_integration': True,
                'metadata_enhancement': True,
                'multi_source': True
            }
        }
        
        return analytics
        
    except Exception as e:
        logger.error(f"Failed to get search analytics: {e}")
        return {}


def resolve_status_from_book_record(book: Optional[Dict]) -> Tuple[str, bool]:
    """Determine library status based on a full book record."""
    if not book:
        return 'not_in_library', False

    file_path = str(book.get('file_path') or '').strip()
    if file_path:
        return 'in_library', True
    return 'wanted', False


def determine_library_status(
    asin: Optional[str],
    db_service,
    cache: Optional[Dict[str, Tuple[str, bool]]] = None,
    record_cache: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
) -> Tuple[str, bool]:
    """Lookup library status for an ASIN with simple caching support."""
    if not asin:
        return 'not_in_library', False

    cache_store: Dict[str, Tuple[str, bool]] = cache if cache is not None else {}
    if asin in cache_store:
        return cache_store[asin]

    book_record = None
    if record_cache is not None and asin in record_cache:
        book_record = record_cache[asin]

    if book_record is None:
        try:
            book_record = db_service.get_book_by_asin(asin)
        except Exception as exc:
            logger.debug(f"Failed to fetch book for ASIN {asin}: {exc}")
            book_record = None
        if record_cache is not None:
            record_cache[asin] = book_record

    status = resolve_status_from_book_record(book_record)
    cache_store[asin] = status
    return status

# ============================================================================
# MAIN SEARCH ROUTES - ENHANCED
# ============================================================================

@search_bp.route('/')
def search_page():
    """Enhanced search page with MediaVault design and advanced features."""
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'basic')  # basic, advanced, download
    results = []
    search_stats = {}
    
    if query:
        try:
            audible_service = get_audible_service()
            db_service = get_database_service()
            
            # Perform enhanced search based on type
            logger.info(f"Performing {search_type} search for: {query}")
            
            library_status_cache: Dict[str, Tuple[str, bool]] = {}
            library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}

            if search_type == 'download':
                # Search for downloadable content
                results, search_stats = perform_download_search(query)
            elif search_type == 'advanced':
                # Advanced search with multiple sources
                results, search_stats = perform_advanced_search(query)
            else:
                # Basic Audible search with enhancements
                raw_results = audible_service.search_books(query)
                
                # Check library status and enhance results
                for book in raw_results:
                    asin = book.get('ASIN')
                    library_status, in_library = determine_library_status(
                        asin,
                        db_service,
                        library_status_cache,
                        library_book_cache,
                    )
                    library_book = library_book_cache.get(asin)
                    formatted_result = format_search_result(
                        book,
                        in_library=in_library,
                        library_status=library_status,
                        library_book=library_book,
                    )
                    results.append(formatted_result)
                
                # Enhance with download availability
                results = enhance_search_results(results)
                in_library_count = len([r for r in results if r.get('library_status') == 'in_library'])
                wanted_count = len([r for r in results if r.get('library_status') == 'wanted'])
                search_stats = {
                    'source': 'audible',
                    'total_results': len(results),
                    'in_library': in_library_count,
                    'wanted': wanted_count,
                    'downloadable': len([r for r in results if r.get('download_available')])
                }
            
            logger.info(f"Found {len(results)} results for query: {query}")
            
        except Exception as e:
            logger.error(f"Search error for query '{query}': {e}")
            flash(f'Search failed: {str(e)}', 'error')
            results = []
            search_stats = {'error': str(e)}
    
    # Get search analytics for UI
    analytics = get_search_analytics()
    
    return render_template('search.html', 
                         title='Enhanced Search - AuralArchive',
                         query=query,
                         search_type=search_type,
                         results=results,
                         results_count=len(results),
                         search_stats=search_stats,
                         analytics=analytics)

def perform_download_search(query: str) -> Tuple[List[Dict], Dict]:
    """Perform search focused on downloadable content."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        library_status_cache: Dict[str, Tuple[str, bool]] = {}
        library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        
        # Download search is disabled until the provider is reintroduced
        download_results = []
        
        results = []
        for download in download_results[:10]:  # Limit to top 10
            # Try to match with Audible data for metadata
            audible_matches = audible_service.search_books(download.get('title', query), num_results=3)
            
            # Create enhanced result
            result = {
                'title': download.get('title', 'Unknown Title'),
                'author': 'Unknown Author',  # Extract from title if possible
                'download_info': download,
                'download_available': True,
                'source': 'download',
                'audible_matches': audible_matches[:3] if audible_matches else [],
                'library_status': 'not_in_library',
                'in_library': False
            }
            
            # If we have Audible matches, use the best one for metadata
            if audible_matches:
                best_match = audible_matches[0]
                result.update({
                    'author': best_match.get('Author', 'Unknown Author'),
                    'cover_image': best_match.get('Cover Image'),
                    'series': best_match.get('Series', 'N/A'),
                    'narrator': best_match.get('Narrator', 'Unknown'),
                    'runtime': best_match.get('Runtime', '0 hrs 0 mins'),
                    'rating': best_match.get('Overall Rating', 'N/A'),
                    'asin': best_match.get('ASIN', ''),
                    'summary': best_match.get('Summary', '')
                })

                asin = best_match.get('ASIN')
                library_status, in_library = determine_library_status(
                    asin,
                    db_service,
                    library_status_cache,
                    library_book_cache,
                )
                library_book = library_book_cache.get(asin)
                result['library_status'] = library_status
                result['in_library'] = in_library
                if library_book:
                    result['id'] = library_book.get('ID')
            
            results.append(result)
        
        stats = {
            'source': 'download',
            'total_results': len(results),
            'download_sources': len(set(r['download_info'].get('provider', 'unknown') for r in results)),
            'with_metadata': len([r for r in results if r.get('asin')])
        }
        
        return results, stats
        
    except Exception as e:
        logger.error(f"Download search failed: {e}")
        return [], {'error': str(e)}

def perform_advanced_search(query: str) -> Tuple[List[Dict], Dict]:
    """Perform advanced search using multiple sources and enhanced metadata."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        library_status_cache: Dict[str, Tuple[str, bool]] = {}
        
        # Search Audible
        audible_results = audible_service.search_books(query)
        
        # Combine and deduplicate results
        combined_results = []
        seen_asins = set()
        
        # Process Audible results first (primary source)
        for book in audible_results:
            asin = book.get('ASIN')
            if asin and asin not in seen_asins:
                book['source'] = 'audible'
                book['enhanced'] = True
                combined_results.append(book)
                seen_asins.add(asin)
        
        # Enhance with download availability
        enhanced_results = enhance_search_results(combined_results)

        formatted_results: List[Dict[str, Any]] = []
        for book in enhanced_results:
            asin = book.get('ASIN') or book.get('asin')
            library_status, in_library = determine_library_status(
                asin,
                db_service,
                library_status_cache,
                library_book_cache,
            )
            library_book = library_book_cache.get(asin)
            formatted_results.append(
                format_search_result(
                    book,
                    in_library=in_library,
                    download_available=book.get('download_available', False),
                    library_status=library_status,
                    library_book=library_book,
                )
            )
        
        stats = {
            'source': 'advanced',
            'total_results': len(formatted_results),
            'audible_results': len([r for r in formatted_results if r.get('search_source') == 'audible']),
            'downloadable': len([r for r in formatted_results if r.get('download_available')]),
            'in_library': len([r for r in formatted_results if r.get('library_status') == 'in_library']),
            'wanted': len([r for r in formatted_results if r.get('library_status') == 'wanted'])
        }
        
        return formatted_results, stats
        
    except Exception as e:
        logger.error(f"Advanced search failed: {e}")
        return [], {'error': str(e)}

# ============================================================================
# API ENDPOINTS - ENHANCED
# ============================================================================

@search_bp.route('/api/search', methods=['POST'])
def api_search():
    """Enhanced API endpoint for search with multiple options."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        
        data = request.json or {}
        query = data.get('query', '').strip()
        search_type = data.get('type', 'basic')
        include_downloads = data.get('include_downloads', False)
        max_results = data.get('max_results', 25)
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        logger.info(f"API search: '{query}' (type: {search_type})")
        
        # Perform search based on type
        if search_type == 'download':
            results, stats = perform_download_search(query)
        elif search_type == 'advanced':
            results, stats = perform_advanced_search(query)
        else:
            # Basic search with optional enhancements
            raw_results = audible_service.search_books(query, num_results=max_results)
            
            results = []
            library_status_cache: Dict[str, Tuple[str, bool]] = {}
            library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            for book in raw_results:
                asin = book.get('ASIN')
                library_status, in_library = determine_library_status(
                    asin,
                    db_service,
                    library_status_cache,
                    library_book_cache,
                )
                library_book = library_book_cache.get(asin)
                formatted_result = format_search_result(
                    book,
                    in_library=in_library,
                    library_status=library_status,
                    library_book=library_book,
                )
                results.append(formatted_result)
            
            # Optional enhancement with download availability
            if include_downloads:
                results = enhance_search_results(results)
            
            stats = {
                'source': 'audible',
                'total_results': len(results),
                'enhanced': include_downloads,
                'in_library': len([r for r in results if r.get('library_status') == 'in_library']),
                'wanted': len([r for r in results if r.get('library_status') == 'wanted'])
            }
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'stats': stats,
            'query': query,
            'search_type': search_type
        })
    
    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@search_bp.route('/api/search/audible', methods=['POST'])
def search_audible():
    """Legacy API endpoint for Audible search (maintained for compatibility)."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        
        query = request.json.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        # Perform search
        raw_results = audible_service.search_books(query)
        
        # Format results and check library status
        results = []
        library_status_cache: Dict[str, Tuple[str, bool]] = {}
        library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        for book in raw_results:
            asin = book.get('ASIN')
            library_status, in_library = determine_library_status(
                asin,
                db_service,
                library_status_cache,
                library_book_cache,
            )
            library_book = library_book_cache.get(asin)
            formatted_result = format_search_result(
                book,
                in_library=in_library,
                library_status=library_status,
                library_book=library_book,
            )
            results.append(formatted_result)
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
    
    except Exception as e:
        logger.error(f"Audible search error: {e}")
        return jsonify({'error': 'Search failed'}), 500

@search_bp.route('/api/download-search', methods=['POST'])
def api_download_search():
    """New API endpoint specifically for download search."""
    try:
        
        data = request.json or {}
        query = data.get('query', '').strip()
        category = data.get('category', 'audiobook')
        max_results = data.get('max_results', 10)
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        logger.info(f"Download search: '{query}' (category: {category})")
        
        # Search for downloads
        download_results = []
        
        # Limit results
        limited_results = download_results[:max_results]
        
        return jsonify({
            'success': True,
            'results': limited_results,
            'count': len(limited_results),
            'total_found': len(download_results),
            'providers': list(set(r.get('provider', 'unknown') for r in limited_results))
        })
    
    except Exception as e:
        logger.error(f"Download search error: {e}")
        return jsonify({'error': f'Download search failed: {str(e)}'}), 500

@search_bp.route('/api/enhance-metadata', methods=['POST'])
def api_enhance_metadata():
    """API endpoint to enhance search result metadata."""
    try:
        metadata_service = get_metadata_update_service()
    
        
        data = request.json or {}
        title = data.get('title', '')
        author = data.get('author', '')
        asin = data.get('asin', '')
        
        if not (title or asin):
            return jsonify({'error': 'Title or ASIN is required'}), 400
        
        enhanced_metadata = {}
        
        # Try different enhancement sources
        if asin:
            # Use metadata update service for ASIN-based enhancement
            try:
                # Get enhanced metadata (would need to adapt metadata service)
                enhanced_metadata['source'] = 'metadata_service'
            except Exception as e:
                logger.debug(f"Metadata service enhancement failed: {e}")
        
        if enhanced_metadata:
            return jsonify({
                'success': True,
                'enhanced_metadata': enhanced_metadata
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No additional metadata found'
            })
    
    except Exception as e:
        logger.error(f"Metadata enhancement error: {e}")
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

# ============================================================================
# BOOK MANAGEMENT - ENHANCED
# ============================================================================

@search_bp.route('/add-book', methods=['POST'])
def add_book_to_library():
    """Enhanced add book to library with validation and metadata enhancement."""
    logger.info("add_book_to_library endpoint called")
    try:
        logger.info("Getting database service...")
        db_service = get_database_service()
        logger.info("Database service obtained successfully")
        
        book_data = request.json
        logger.debug(f"Received book data: {book_data}")
        asin = book_data.get('ASIN') or book_data.get('asin')
        logger.info(f"ASIN extracted: {asin}")
        
        if not asin:
            logger.warning("No ASIN provided in request")
            return jsonify({'error': 'ASIN is required'}), 400
        
        logger.info(f"Checking if book exists: {asin}")
        if db_service.check_book_exists(asin):
            logger.info(f"Book already exists: {asin}")
            return jsonify({'error': 'Book already exists in library'}), 409
        
        # Convert and validate book data
        db_book_data = {
            'Title': book_data.get('title', book_data.get('Title', '')),
            'Author': book_data.get('author', book_data.get('Author', '')),
            'Series': book_data.get('series', book_data.get('Series', 'N/A')),
            'Sequence': book_data.get('sequence', book_data.get('Sequence', '')),
            'Narrator': book_data.get('narrator', book_data.get('Narrator', '')),
            'Runtime': book_data.get('runtime', book_data.get('Runtime', '')),
            'Overall Rating': book_data.get('rating', book_data.get('Overall Rating', '')),
            'Release Date': book_data.get('release_date', book_data.get('Release Date', '')),
            'ASIN': asin,
            'Publisher': book_data.get('publisher', book_data.get('Publisher', '')),
            'Language': book_data.get('language', book_data.get('Language', 'English')),
            'Summary': book_data.get('summary', book_data.get('Summary', '')),
            'Cover Image': book_data.get('cover_image', book_data.get('Cover Image', ''))
        }
        
        # Validate required fields
        if not db_book_data['Title'] or not db_book_data['Author']:
            return jsonify({'error': 'Title and Author are required'}), 400
        
        # Add to library
        if db_service.add_book(db_book_data, status="Wanted"):
            logger.info(f"Added book to library: {db_book_data['Title']} by {db_book_data['Author']}")
            
            # Optional: Schedule metadata enhancement
            try:
                metadata_service = get_metadata_update_service()
                # Could trigger background enhancement here
            except Exception as e:
                logger.debug(f"Metadata enhancement scheduling failed: {e}")
            
            return jsonify({
                'success': True, 
                'message': 'Book added to library successfully',
                'book': {
                    'title': db_book_data['Title'],
                    'author': db_book_data['Author'],
                    'asin': asin
                }
            })
        else:
            return jsonify({'error': 'Failed to add book to database'}), 500
    
    except Exception as e:
        logger.error(f"Error adding book: {e}")
        return jsonify({'error': f'Failed to add book: {str(e)}'}), 500

@search_bp.route('/book/<asin>')
def get_book_details(asin):
    """Get enhanced book details with multiple source integration."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        
        book_details = {}
        
        # Check if book is in library first
        if db_service.check_book_exists(asin):
            books = db_service.get_all_books()
            book = next((b for b in books if b.get('ASIN') == asin), None)
            if book:
                library_status, in_library = resolve_status_from_book_record(book)
                book_details = format_search_result(
                    book,
                    in_library=in_library,
                    library_status=library_status
                )
                book_details['source'] = 'library'
        
        # If not in library or library data is incomplete, search external sources
        if not book_details or not book_details.get('summary'):
            # Search Audible
            audible_results = audible_service.search_books(asin, num_results=1)
            if audible_results:
                audible_book = audible_results[0]
                if not book_details:
                    book_details = format_search_result(
                        audible_book,
                        in_library=False,
                        library_status='not_in_library'
                    )
                    book_details['source'] = 'audible'
                else:
                    # Merge additional data from Audible
                    for key, value in audible_book.items():
                        if not book_details.get(key) and value:
                            book_details[key] = value
                    book_details['enhanced_with'] = 'audible'
        
        # Try to enhance with download availability
        if book_details.get('title') and book_details.get('author'):
            try:
                search_query = f"{book_details['title']} {book_details['author']}"
                download_results = []
                book_details['download_available'] = len(download_results) > 0
                book_details['download_options'] = download_results[:5]  # Top 5 options
            except Exception as e:
                logger.debug(f"Download availability check failed: {e}")
                book_details['download_available'] = False
        
        if book_details:
            return jsonify({
                'success': True, 
                'book': book_details
            })
        else:
            return jsonify({'error': 'Book not found'}), 404
    
    except Exception as e:
        logger.error(f"Error getting book details for ASIN {asin}: {e}")
        return jsonify({'error': 'Failed to get book details'}), 500

@search_bp.route('/book-info/<asin>')
def get_book_info(asin):
    """Get enhanced book info WITHOUT download searching - for quick details modal."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        
        book_details = {}
        
        # Check if book is in library first
        if db_service.check_book_exists(asin):
            books = db_service.get_all_books()
            book = next((b for b in books if b.get('ASIN') == asin), None)
            if book:
                library_status, in_library = resolve_status_from_book_record(book)
                book_details = format_search_result(
                    book,
                    in_library=in_library,
                    library_status=library_status
                )
                book_details['source'] = 'library'
        
        # If not in library or library data is incomplete, search external sources
        if not book_details or not book_details.get('summary'):
            # Search Audible
            audible_results = audible_service.search_books(asin, num_results=1)
            if audible_results:
                audible_book = audible_results[0]
                if not book_details:
                    book_details = format_search_result(
                        audible_book,
                        in_library=False,
                        library_status='not_in_library'
                    )
                    book_details['source'] = 'audible'
                else:
                    # Merge additional data from Audible
                    for key, value in audible_book.items():
                        if not book_details.get(key) and value:
                            book_details[key] = value
                    book_details['enhanced_with'] = 'audible'
        
        # Skip download availability check for faster response
        book_details['download_available'] = False
        
        if book_details:
            return jsonify({
                'success': True, 
                'book': book_details
            })
        else:
            return jsonify({'error': 'Book not found'}), 404
    
    except Exception as e:
        logger.error(f"Error getting book info for ASIN {asin}: {e}")
        return jsonify({'error': 'Failed to get book info'}), 500

# ============================================================================
# SEARCH SUGGESTIONS AND ANALYTICS
# ============================================================================

@search_bp.route('/suggestions')
def get_search_suggestions():
    """Enhanced search suggestions with multiple sources."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        
        # Get unique authors and series for suggestions
        authors = set()
        series = set()
        publishers = set()
        narrators = set()
        
        for book in books:
            if book.get('Author'):
                authors.add(book['Author'])
            if book.get('Series') and book['Series'] != 'N/A':
                series.add(book['Series'])
            if book.get('Publisher'):
                publishers.add(book['Publisher'])
            if book.get('Narrator'):
                narrators.add(book['Narrator'])
        
        # Enhanced suggestions
        suggestions = {
            'authors': sorted(list(authors))[:15],
            'series': sorted(list(series))[:15],
            'publishers': sorted(list(publishers))[:10],
            'narrators': sorted(list(narrators))[:10],
            'categories': [
                'Science Fiction', 'Fantasy', 'Mystery', 'Thriller',
                'Romance', 'Biography', 'History', 'Self-Help',
                'Business', 'Non-Fiction', 'Literary Fiction'
            ]
        }
        
        return jsonify({
            'success': True,
            'suggestions': suggestions
        })
    
    except Exception as e:
        logger.error(f"Error getting search suggestions: {e}")
        return jsonify({'error': 'Failed to get suggestions'}), 500

@search_bp.route('/analytics')
def get_search_analytics_endpoint():
    """Get comprehensive search analytics and system status."""
    try:
        analytics = get_search_analytics()
        
        # Add additional metrics
        db_service = get_database_service()
        books = db_service.get_all_books()
        
        analytics['library_stats'] = {
            'total_books': len(books),
            'unique_authors': len(set(book.get('Author', '') for book in books if book.get('Author'))),
            'unique_series': len(set(book.get('Series', '') for book in books if book.get('Series') and book.get('Series') != 'N/A'))
        }
        
        # Test service availability
        analytics['service_status'] = {
            'audible': test_service_availability('audible'),
            'download': test_service_availability('download'),
            'metadata': test_service_availability('metadata')
        }
        
        return jsonify({
            'success': True,
            'analytics': analytics,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error getting search analytics: {e}")
        return jsonify({'error': 'Failed to get analytics'}), 500

def test_service_availability(service_name: str) -> Dict[str, Any]:
    """Test if a service is available and responsive."""
    try:
        if service_name == 'audible':
            audible_service = get_audible_service()
            test_results = audible_service.search_books('test', num_results=1)
            return {'available': bool(test_results), 'response_time': 'fast'}
        
        elif service_name == 'download':
            providers = []
            return {'available': len(providers) > 0, 'providers': len(providers)}
        
        elif service_name == 'metadata':
            metadata_service = get_metadata_update_service()
            status = metadata_service.get_service_status()
            return {'available': status.get('initialized', False)}
        
        return {'available': False, 'error': 'Unknown service'}
        
    except Exception as e:
        return {'available': False, 'error': str(e)}

@search_bp.route('/recent-searches')
def get_recent_searches():
    """Enhanced recent searches with analytics."""
    # This could be implemented with a database table to store search history
    # For now, returning curated trending searches
    return jsonify({
        'success': True,
        'recent_searches': [
            {'query': 'Andy Weir', 'timestamp': '2024-01-15T10:30:00Z', 'results': 8},
            {'query': 'Atomic Habits', 'timestamp': '2024-01-15T09:15:00Z', 'results': 3},
            {'query': 'Brandon Sanderson', 'timestamp': '2024-01-14T16:45:00Z', 'results': 25},
            {'query': 'Project Hail Mary', 'timestamp': '2024-01-14T14:20:00Z', 'results': 2},
            {'query': 'The Midnight Library', 'timestamp': '2024-01-14T11:10:00Z', 'results': 4}
        ],
        'analytics': {
            'total_searches_today': 47,
            'average_results_per_search': 8.4,
            'most_common_author': 'Brandon Sanderson'
        }
    })

@search_bp.route('/trending')
def get_trending_books():
    """Enhanced trending books with real-time data."""
    return jsonify({
        'success': True,
        'trending': [
            {
                'title': 'Fourth Wing',
                'author': 'Rebecca Yarros',
                'trend_score': 95,
                'category': 'Fantasy Romance'
            },
            {
                'title': 'Tom Lake',
                'author': 'Ann Patchett',
                'trend_score': 88,
                'category': 'Literary Fiction'
            },
            {
                'title': 'The Seven Husbands of Evelyn Hugo',
                'author': 'Taylor Jenkins Reid',
                'trend_score': 87,
                'category': 'Historical Fiction'
            },
            {
                'title': 'Lessons in Chemistry',
                'author': 'Bonnie Garmus',
                'trend_score': 84,
                'category': 'Historical Fiction'
            },
            {
                'title': 'The Atlas Six',
                'author': 'Olivie Blake',
                'trend_score': 82,
                'category': 'Dark Academia Fantasy'
            }
        ],
        'last_updated': datetime.now().isoformat(),
        'source': 'curated_trending'
    })

# ============================================================================
# ADVANCED SEARCH FEATURES
# ============================================================================

@search_bp.route('/api/advanced-search', methods=['POST'])
def api_advanced_search():
    """Advanced search with filters and multiple criteria."""
    try:
        audible_service = get_audible_service()
        db_service = get_database_service()
        
        data = request.json or {}
        filters = {
            'title': data.get('title', ''),
            'author': data.get('author', ''),
            'series': data.get('series', ''),
            'narrator': data.get('narrator', ''),
            'genre': data.get('genre', ''),
            'language': data.get('language', ''),
            'min_rating': data.get('min_rating', 0),
            'max_runtime': data.get('max_runtime', 0),
            'release_year_from': data.get('release_year_from', 0),
            'release_year_to': data.get('release_year_to', 0),
            'in_library_only': data.get('in_library_only', False),
            'exclude_library': data.get('exclude_library', False)
        }
        
        logger.info(f"Advanced search with filters: {filters}")
        
        results = []
        
        if filters['in_library_only']:
            # Search only library
            books = db_service.get_all_books()
            filtered_books = apply_filters_to_books(books, filters)
            
            for book in filtered_books:
                library_status, in_library = resolve_status_from_book_record(book)
                formatted_result = format_search_result(
                    book,
                    in_library=in_library,
                    library_status=library_status
                )
                results.append(formatted_result)
        else:
            # Build search query from filters
            search_terms = []
            if filters['title']:
                search_terms.append(filters['title'])
            if filters['author']:
                search_terms.append(filters['author'])
            if filters['series']:
                search_terms.append(filters['series'])
            
            if search_terms:
                query = ' '.join(search_terms)
                raw_results = audible_service.search_books(query, num_results=50)
                
                # Apply filters to results
                filtered_results = apply_filters_to_books(raw_results, filters)
                library_status_cache: Dict[str, Tuple[str, bool]] = {}
                library_book_cache: Dict[str, Optional[Dict[str, Any]]] = {}
                
                for book in filtered_results:
                    asin = book.get('ASIN')
                    library_status, in_library = determine_library_status(
                        asin,
                        db_service,
                        library_status_cache,
                        library_book_cache,
                    )
                    library_book = library_book_cache.get(asin)
                    
                    # Skip if excluding library books
                    if filters['exclude_library'] and in_library:
                        continue
                    
                    formatted_result = format_search_result(
                        book,
                        in_library=in_library,
                        library_status=library_status,
                        library_book=library_book,
                    )
                    results.append(formatted_result)
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'filters_applied': {k: v for k, v in filters.items() if v},
            'search_type': 'advanced'
        })
    
    except Exception as e:
        logger.error(f"Advanced search error: {e}")
        return jsonify({'error': f'Advanced search failed: {str(e)}'}), 500

def apply_filters_to_books(books: List[Dict], filters: Dict) -> List[Dict]:
    """Apply advanced search filters to a list of books."""
    filtered_books = []
    
    for book in books:
        # Apply each filter
        if filters['title'] and filters['title'].lower() not in book.get('Title', '').lower():
            continue
        
        if filters['author'] and filters['author'].lower() not in book.get('Author', '').lower():
            continue
        
        if filters['series'] and filters['series'].lower() not in book.get('Series', '').lower():
            continue
        
        if filters['narrator'] and filters['narrator'].lower() not in book.get('Narrator', '').lower():
            continue
        
        if filters['language'] and filters['language'].lower() != book.get('Language', '').lower():
            continue
        
        # Rating filter
        if filters['min_rating'] > 0:
            try:
                rating = float(book.get('Overall Rating', 0))
                if rating < filters['min_rating']:
                    continue
            except (ValueError, TypeError):
                continue
        
        # Runtime filter (convert to minutes for comparison)
        if filters['max_runtime'] > 0:
            try:
                runtime_str = book.get('Runtime', '0 hrs 0 mins')
                runtime_minutes = parse_runtime_to_minutes(runtime_str)
                if runtime_minutes > filters['max_runtime']:
                    continue
            except:
                continue
        
        # Release year filter
        if filters['release_year_from'] > 0 or filters['release_year_to'] > 0:
            try:
                release_date = book.get('Release Date', '')
                release_year = extract_year_from_date(release_date)
                if release_year:
                    if filters['release_year_from'] > 0 and release_year < filters['release_year_from']:
                        continue
                    if filters['release_year_to'] > 0 and release_year > filters['release_year_to']:
                        continue
            except:
                continue
        
        filtered_books.append(book)
    
    return filtered_books

def parse_runtime_to_minutes(runtime_str: str) -> int:
    """Parse runtime string to total minutes."""
    try:
        total_minutes = 0
        if 'hrs' in runtime_str:
            hours = int(runtime_str.split(' hrs')[0])
            total_minutes += hours * 60
        if 'mins' in runtime_str:
            mins_part = runtime_str.split(' hrs ')[1] if ' hrs ' in runtime_str else runtime_str
            minutes = int(mins_part.split(' mins')[0])
            total_minutes += minutes
        return total_minutes
    except:
        return 0

def extract_year_from_date(date_str: str) -> Optional[int]:
    """Extract year from various date formats."""
    try:
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if year_match:
            return int(year_match.group())
        return None
    except:
        return None

# ============================================================================
# SEARCH COMPARISON AND BATCH OPERATIONS
# ============================================================================

@search_bp.route('/api/compare-sources', methods=['POST'])
def api_compare_sources():
    """Compare search results across different sources."""
    try:
        data = request.json or {}
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        logger.info(f"Comparing sources for query: {query}")
        
        comparison_results = {}
        
        # Search Audible
        try:
            audible_service = get_audible_service()
            audible_results = audible_service.search_books(query, num_results=10)
            comparison_results['audible'] = {
                'count': len(audible_results),
                'results': audible_results[:5],  # Top 5 for comparison
                'status': 'success'
            }
        except Exception as e:
            comparison_results['audible'] = {
                'count': 0,
                'results': [],
                'status': 'error',
                'error': str(e)
            }
        
        # Search Downloads
        try:
            download_results = []
            comparison_results['downloads'] = {
                'count': len(download_results),
                'results': download_results[:5],
                'status': 'success',
                'providers': list(set(r.get('provider', 'unknown') for r in download_results))
            }
        except Exception as e:
            comparison_results['downloads'] = {
                'count': 0,
                'results': [],
                'status': 'error',
                'error': str(e)
            }
        
        # Calculate comparison metrics
        total_results = sum(source['count'] for source in comparison_results.values())
        working_sources = sum(1 for source in comparison_results.values() if source['status'] == 'success')
        
        return jsonify({
            'success': True,
            'query': query,
            'comparison': comparison_results,
            'summary': {
                'total_results': total_results,
                'working_sources': working_sources,
                'total_sources': len(comparison_results)
            }
        })
    
    except Exception as e:
        logger.error(f"Source comparison error: {e}")
        return jsonify({'error': f'Comparison failed: {str(e)}'}), 500

@search_bp.route('/api/batch-add', methods=['POST'])
def api_batch_add_books():
    """Batch add multiple books to library from search results."""
    try:
        db_service = get_database_service()
        
        data = request.json or {}
        books = data.get('books', [])
        
        if not books:
            return jsonify({'error': 'No books provided'}), 400
        
        logger.info(f"Batch adding {len(books)} books to library")
        
        results = {
            'total': len(books),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'details': []
        }
        
        for book_data in books:
            try:
                asin = book_data.get('ASIN') or book_data.get('asin')
                title = book_data.get('title', book_data.get('Title', 'Unknown'))
                
                if not asin:
                    results['failed'] += 1
                    results['details'].append({
                        'title': title,
                        'status': 'failed',
                        'reason': 'Missing ASIN'
                    })
                    continue
                
                if db_service.check_book_exists(asin):
                    results['skipped'] += 1
                    results['details'].append({
                        'title': title,
                        'asin': asin,
                        'status': 'skipped',
                        'reason': 'Already in library'
                    })
                    continue
                
                # Convert book data
                db_book_data = {
                    'Title': book_data.get('title', book_data.get('Title', '')),
                    'Author': book_data.get('author', book_data.get('Author', '')),
                    'Series': book_data.get('series', book_data.get('Series', 'N/A')),
                    'Sequence': book_data.get('sequence', book_data.get('Sequence', '')),
                    'Narrator': book_data.get('narrator', book_data.get('Narrator', '')),
                    'Runtime': book_data.get('runtime', book_data.get('Runtime', '')),
                    'Overall Rating': book_data.get('rating', book_data.get('Overall Rating', '')),
                    'Release Date': book_data.get('release_date', book_data.get('Release Date', '')),
                    'ASIN': asin,
                    'Publisher': book_data.get('publisher', book_data.get('Publisher', '')),
                    'Language': book_data.get('language', book_data.get('Language', 'English')),
                    'Summary': book_data.get('summary', book_data.get('Summary', '')),
                    'Cover Image': book_data.get('cover_image', book_data.get('Cover Image', ''))
                }
                
                if db_service.add_book(db_book_data, status="Wanted"):
                    results['successful'] += 1
                    results['details'].append({
                        'title': title,
                        'asin': asin,
                        'status': 'added',
                        'reason': 'Successfully added to library'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'title': title,
                        'asin': asin,
                        'status': 'failed',
                        'reason': 'Database error'
                    })
            
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'title': book_data.get('title', 'Unknown'),
                    'status': 'failed',
                    'reason': str(e)
                })
        
        logger.info(f"Batch add completed: {results['successful']} successful, {results['failed']} failed, {results['skipped']} skipped")
        
        return jsonify({
            'success': True,
            'message': f"Batch operation completed: {results['successful']} added, {results['skipped']} skipped, {results['failed']} failed",
            'results': results
        })
    
    except Exception as e:
        logger.error(f"Batch add error: {e}")
        return jsonify({'error': f'Batch add failed: {str(e)}'}), 500

# ============================================================================
# SEARCH EXPORT AND SHARING
# ============================================================================

@search_bp.route('/api/export-results', methods=['POST'])
def api_export_search_results():
    """Export search results in various formats."""
    try:
        data = request.json or {}
        results = data.get('results', [])
        format_type = data.get('format', 'json')  # json, csv, txt
        
        if not results:
            return jsonify({'error': 'No results to export'}), 400
        
        export_data = {
            'export_info': {
                'timestamp': datetime.now().isoformat(),
                'total_results': len(results),
                'format': format_type,
                'source': 'AuralArchive Search'
            },
            'results': results
        }
        
        if format_type == 'csv':
            # Convert to CSV-friendly format
            import io
            import csv
            
            output = io.StringIO()
            if results:
                fieldnames = ['title', 'author', 'series', 'narrator', 'runtime', 'rating', 'asin', 'in_library']
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in results:
                    writer.writerow({
                        'title': result.get('title', ''),
                        'author': result.get('author', ''),
                        'series': result.get('series', ''),
                        'narrator': result.get('narrator', ''),
                        'runtime': result.get('runtime', ''),
                        'rating': result.get('rating', ''),
                        'asin': result.get('asin', ''),
                        'in_library': result.get('in_library', False)
                    })
            
            return jsonify({
                'success': True,
                'export_data': output.getvalue(),
                'filename': f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            })
        
        elif format_type == 'txt':
            # Convert to text format
            text_lines = [f"AuralArchive Search Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
            
            for i, result in enumerate(results, 1):
                text_lines.extend([
                    f"{i}. {result.get('title', 'Unknown Title')}",
                    f"   Author: {result.get('author', 'Unknown Author')}",
                    f"   Series: {result.get('series', 'N/A')}",
                    f"   Narrator: {result.get('narrator', 'Unknown')}",
                    f"   Runtime: {result.get('runtime', 'Unknown')}",
                    f"   Rating: {result.get('rating', 'N/A')}",
                    f"   ASIN: {result.get('asin', 'N/A')}",
                    f"   In Library: {'Yes' if result.get('in_library') else 'No'}",
                    ""
                ])
            
            return jsonify({
                'success': True,
                'export_data': '\n'.join(text_lines),
                'filename': f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            })
        
        else:  # JSON format (default)
            return jsonify({
                'success': True,
                'export_data': export_data,
                'filename': f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            })
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

# ============================================================================
# SEARCH PERFORMANCE AND CACHING
# ============================================================================

@search_bp.route('/api/search-performance')
def api_search_performance():
    """Get search performance metrics and optimization suggestions."""
    try:
        analytics = get_search_analytics()
        
        # Add performance metrics
        performance_data = {
            'api_status': analytics.get('api_status', {}),
            'service_status': {
                'audible': test_service_availability('audible'),
                'download': test_service_availability('download'),
                'metadata': test_service_availability('metadata')
            },
            'optimization_suggestions': [],
            'cache_status': {
                'enabled': False,  # Would implement caching in future
                'hit_rate': 0,
                'size': 0
            }
        }
        
        # Generate optimization suggestions
        if not performance_data['service_status']['download']['available']:
            performance_data['optimization_suggestions'].append({
                'type': 'warning',
                'message': 'Download service unavailable - download search disabled',
                'action': 'Check download service configuration'
            })
        
        if analytics.get('max_results', 25) > 50:
            performance_data['optimization_suggestions'].append({
                'type': 'info',
                'message': 'High max_results setting may slow searches',
                'action': 'Consider reducing max_results for faster searches'
            })
        
        return jsonify({
            'success': True,
            'performance': performance_data,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        return jsonify({'error': f'Performance check failed: {str(e)}'}), 500