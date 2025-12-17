"""
Manual Download API - AuralArchive

Provides manual and automatic search endpoints that drive the download queue,
including status controls, ownership checks, and metadata normalization.

Author: AuralArchive Development Team
Updated: December 3, 2025
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify

from utils.logger import get_module_logger
from utils.search_normalization import normalize_search_terms
from services.service_manager import (
    get_audible_service_manager,
    get_config_service,
    get_database_service,
)
from services.audible.ownership_validator import assess_audible_ownership, fetch_audible_library_entry

logger = get_module_logger("API.ManualDownload")

# Create blueprint
manual_search_api_bp = Blueprint('manual_search_api', __name__)

# Global service instances (will be initialized in app.py)
automatic_search_service = None
manual_search_service = None
database_service = None


def init_search_services(auto_search_svc, manual_search_svc, db_service):
    """Initialize search services for the API"""
    global automatic_search_service, manual_search_service, database_service
    automatic_search_service = auto_search_svc
    manual_search_service = manual_search_svc
    database_service = db_service


NUMBER_WORD_MAP = {
    'zero': 0,
    'one': 1,
    'two': 2,
    'three': 3,
    'four': 4,
    'five': 5,
    'six': 6,
    'seven': 7,
    'eight': 8,
    'nine': 9,
    'ten': 10,
    'eleven': 11,
    'twelve': 12,
    'thirteen': 13,
    'fourteen': 14,
    'fifteen': 15,
    'sixteen': 16,
    'seventeen': 17,
    'eighteen': 18,
    'nineteen': 19,
    'twenty': 20
}


def _normalize_sequence_number(sequence_value: Optional[str]) -> Optional[str]:
    if not sequence_value:
        return None
    sequence_str = str(sequence_value).strip()
    if not sequence_str or sequence_str.upper() == 'N/A':
        return None

    digit_match = re.search(r"\d+(?:\.\d+)?", sequence_str)
    if digit_match:
        return digit_match.group(0)

    tokens = re.split(r"[^a-zA-Z]+", sequence_str.lower())
    for token in tokens:
        if token in NUMBER_WORD_MAP:
            return str(NUMBER_WORD_MAP[token])
    return None


def _build_series_book_queries(series: Optional[str], sequence_value: Optional[str]) -> List[str]:
    if not series:
        return []
    normalized_number = _normalize_sequence_number(sequence_value)
    if not normalized_number:
        return []

    base = series.strip()
    candidates = [
        f"{base} Book {normalized_number}",
        f"{base}: Book {normalized_number}",
        f"{base} {normalized_number}"
    ]
    seen = set()
    deduped: List[str] = []
    for candidate in candidates:
        text = candidate.strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        deduped.append(text)
    return deduped

@manual_search_api_bp.route('/automatic/status', methods=['GET'])
def get_automatic_status():
    """Get automatic search service status"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        status = automatic_search_service.get_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting automatic search status: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/automatic/start', methods=['POST'])
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

@manual_search_api_bp.route('/automatic/stop', methods=['POST'])
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

@manual_search_api_bp.route('/automatic/pause', methods=['POST'])
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

@manual_search_api_bp.route('/automatic/resume', methods=['POST'])
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

@manual_search_api_bp.route('/automatic/queue', methods=['GET'])
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

@manual_search_api_bp.route('/automatic/force/<int:book_id>', methods=['POST'])
def force_search_book(book_id):
    """Force immediate search for a specific book"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        result = automatic_search_service.force_search_book(book_id)
        if result.get('success'):
            return jsonify({'message': f'Forced search queued for book {book_id}', 'success': True, 'details': result})
        else:
            return jsonify({'message': result.get('error', f'Failed to queue search for book {book_id}'), 'success': False}), 400
            
    except Exception as e:
        logger.error(f"Error forcing search for book {book_id}: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/automatic/config', methods=['GET'])
def get_automatic_config():
    """Get automatic search configuration"""
    try:
        if not automatic_search_service:
            return jsonify({'error': 'Automatic search service not available'}), 503
        
        config_service = get_config_service()
        config = config_service.get_section('auto_search') or {}
        return jsonify(config)
        
    except Exception as e:
        logger.error(f"Error getting automatic search config: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/automatic/config', methods=['POST'])
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

# Manual Search API Endpoints

@manual_search_api_bp.route('/manual/search', methods=['POST'])
def manual_search():
    """Perform manual search"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Query parameter required'}), 400
        
        query = data['query']
        search_options = data.get('options', {})
        
        # Perform search
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(
            manual_search_service.search(query, **search_options)
        )
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error performing manual search: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/manual/book/<int:book_id>', methods=['POST'])
def interactive_search_book(book_id):
    """Perform interactive search for a specific book by ID - Sonarr style"""
    try:
        if not manual_search_service:
            return jsonify({'error': 'Manual search service not available'}), 503
        
        if not database_service:
            return jsonify({'error': 'Database service not available'}), 503
        
        # Get book details from database
        book = database_service.get_book_by_id(book_id)

        if not book:
            return jsonify({'error': f'Book with ID {book_id} not found'}), 404
        
        def _safe_str(value) -> str:
            if value is None:
                return ''
            if isinstance(value, str):
                return value.strip()
            return str(value).strip()

        # Build search query from book metadata
        title = _safe_str(book.get('Title', ''))
        author = _safe_str(book.get('Author', ''))
        
        if not title:
            return jsonify({'error': 'Book title is required for search'}), 400

        series = _safe_str(book.get('Series', ''))
        sequence_value = _safe_str(book.get('Sequence', ''))

        _, normalized_title, normalized_author = normalize_search_terms(
            title,
            title,
            author,
        )
        fallback_title = normalized_title or title
        fallback_author = normalized_author or author

        def _add_attempt(attempts_list, seen, attempt_title, attempt_author):
            title_candidate = _safe_str(attempt_title)
            author_candidate = _safe_str(attempt_author)
            if not title_candidate and not author_candidate:
                return
            key = (title_candidate.lower(), author_candidate.lower())
            if key in seen:
                return
            seen.add(key)
            attempts_list.append((title_candidate, author_candidate))

        asin = book.get('ASIN')
        audible_library_entry = fetch_audible_library_entry(database_service, asin)
        owned_via_audible, ownership_details = assess_audible_ownership(audible_library_entry)
        
        logger.info(f"Interactive search for book {book_id}: title='{title}', author='{author}'")

        search_attempts = []
        seen_attempts = set()
        # Prefer normalized/fallback title queries first (broader, subtitle-stripped)
        _add_attempt(search_attempts, seen_attempts, fallback_title, fallback_author)
        _add_attempt(search_attempts, seen_attempts, fallback_title, '')
        _add_attempt(search_attempts, seen_attempts, title, author)
        _add_attempt(search_attempts, seen_attempts, title, '')
        fallback_titles = _build_series_book_queries(series, sequence_value)
        for candidate in fallback_titles:
            _add_attempt(search_attempts, seen_attempts, candidate, author or "")
            _add_attempt(search_attempts, seen_attempts, candidate, '')
            # Normalized candidate combination helps when subtitles exist in DB title
            if candidate != fallback_title:
                _add_attempt(search_attempts, seen_attempts, candidate, fallback_author)

        raw_results: List[Dict[str, Any]] = []
        effective_query = {'title': title, 'author': author or ""}
        for attempt_title, attempt_author in search_attempts:
            raw_results = manual_search_service.search_all_indexers(
                title=attempt_title,
                author=attempt_author,
                manual_search=True
            )
            if raw_results:
                effective_query = {'title': attempt_title, 'author': attempt_author}
                logger.info(
                    "Interactive search succeeded with fallback query title='%s' author='%s'",
                    attempt_title,
                    attempt_author
                )
                break
        search_title_for_scoring = effective_query['title']
        search_author_for_scoring = effective_query['author']
        
        # Quality assess and rank the results (adds quality_assessment to each result)
        from services.search_engine.quality_assessor import QualityAssessor
        quality_assessor = QualityAssessor()
        scored_results = quality_assessor.rank_results_by_quality(
            raw_results,
            search_title=search_title_for_scoring,
            search_author=search_author_for_scoring
        )
        
        # Process results for manual selection (converts quality_assessment dataclass to dict)
        processed_results = manual_search_service.process_manual_search_results(
            raw_results=scored_results,  # Use scored_results instead of raw_results
            title=search_title_for_scoring,
            author=search_author_for_scoring
        )

        audible_result = None
        try:
            if asin and owned_via_audible:
                audible_manager = get_audible_service_manager()
                library_service = getattr(audible_manager, 'library_service', None) if audible_manager else None

                if library_service:
                    auth_status = library_service.check_authentication_status()
                    if auth_status.get('authenticated'):
                        audible_format = (audible_library_entry or {}).get('format', 'AAXC')
                        file_size = (audible_library_entry or {}).get('file_size') or 0
                        audible_result = {
                            'id': f'audible-{asin}',
                            'title': f"{title} [Audible Library]",
                            'format': (audible_format or 'AAXC').upper(),
                            'size_bytes': file_size,
                            'quality_assessment': {
                                'total_score': 10.0,
                                'confidence': 100.0,
                                'notes': 'Direct download from owned Audible library'
                            },
                            'confidence': 100.0,
                            'quality_score': 100.0,
                            'seeders': None,
                            'peers': None,
                            'indexer': 'Audible Library',
                            'source': 'Audible',
                            'download_type': 'audible',
                            'asin': asin,
                            'ownership_status': book.get('ownership_status'),
                            'download_url': None,
                            'info_url': None,
                            'tags': (audible_library_entry or {}).get('tags'),
                            'description': 'Download directly from your Audible account',
                            'ownership_reason': ownership_details.get('reason')
                        }
                        if audible_library_entry and audible_library_entry.get('summary'):
                            audible_result['description'] = audible_library_entry['summary']
        except Exception as exc:
            logger.warning(f"Failed to prepare Audible download option for ASIN {asin}: {exc}")
            audible_result = None

        if audible_result:
            processed_results = processed_results or []
            processed_results.insert(0, audible_result)
        
        # Debug logging
        if processed_results and len(processed_results) > 0:
            logger.info(f"First result structure: {processed_results[0]}")
            logger.info(f"First result has quality_assessment: {'quality_assessment' in processed_results[0]}")
            if 'quality_assessment' in processed_results[0]:
                logger.info(f"Quality assessment: {processed_results[0]['quality_assessment']}")
        
        # Build response
        response = {
            'success': True,
            'results': processed_results,
            'book_info': {
                'id': book_id,
                'title': title,
                'author': author,
                'series': series
            },
            'stats': manual_search_service.get_processing_stats(processed_results) if processed_results else {},
            'audible_download_available': bool(audible_result),
            'audible_ownership_details': ownership_details if owned_via_audible else None
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error performing interactive search for book {book_id}: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/manual/preview', methods=['POST'])
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

@manual_search_api_bp.route('/manual/download', methods=['POST'])
def initiate_manual_download():
    """Initiate download for a selected result with book metadata support"""
    try:
        data = request.get_json()
        if not data or 'result' not in data:
            return jsonify({'error': 'Result data required'}), 400
        
        result = data['result']
        book_id = data.get('book_id')
        
        # Get database service to fetch book info
        database_service = get_database_service()
        
        if not book_id or not database_service:
            return jsonify({'error': 'Book ID and database service required'}), 400
        
        # Get book from database
        book = database_service.get_book_by_id(book_id)
        if not book:
            return jsonify({'error': 'Book not found'}), 404
        
        book_asin = book.get('ASIN')
        if not book_asin:
            return jsonify({'error': 'Book ASIN not found'}), 400

        audible_library_entry = fetch_audible_library_entry(database_service, book_asin)
        owned_via_audible, ownership_details = assess_audible_ownership(audible_library_entry)

        download_type = (result.get('download_type') or result.get('source') or '').lower()

        from services.service_manager import get_download_management_service
        dm_service = get_download_management_service()

        if not dm_service:
            return jsonify({'error': 'Download management service not available'}), 503

        priority = data.get('priority')
        if priority is None:
            priority = getattr(dm_service, 'queue_priority_default', 5)
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = getattr(dm_service, 'queue_priority_default', 5)
        priority = max(1, min(10, priority))

        if 'audible' in download_type:
            audible_manager = get_audible_service_manager()
            library_service = getattr(audible_manager, 'library_service', None) if audible_manager else None

            if not library_service:
                return jsonify({'error': 'Audible library service not available'}), 503

            auth_status = library_service.check_authentication_status()
            if not auth_status.get('authenticated'):
                return jsonify({
                    'success': False,
                    'error': 'Not authenticated with Audible',
                    'message': 'Authenticate via Settings > Audible before downloading owned titles.'
                }), 403

            if not owned_via_audible:
                reason = ownership_details.get('reason') if ownership_details else 'Ownership not verified.'
                logger.warning(
                    "Blocked Audible download for ASIN %s: %s",
                    book_asin,
                    reason
                )
                return jsonify({
                    'success': False,
                    'error': 'Audible ownership verification failed',
                    'message': reason or 'Audible library verification is required before downloading.'
                }), 403

            config_service = get_config_service()
            audible_config = config_service.get_section('audible') if config_service else {}
            asin_override = result.get('asin') or book_asin
            if not asin_override:
                return jsonify({'error': 'ASIN required for Audible download'}), 400

            format_pref = (result.get('format_preference') or result.get('format') or audible_config.get('download_format') or 'aaxc').lower()
            quality_pref = (result.get('quality') or audible_config.get('download_quality') or 'best').lower()

            valid_formats = {'aax', 'aaxc', 'aax-fallback'}
            if format_pref not in valid_formats:
                format_pref = audible_config.get('download_format', 'aaxc').lower()
            if format_pref not in valid_formats:
                format_pref = 'aaxc'

            valid_qualities = {'best', 'high', 'normal'}
            if quality_pref not in valid_qualities:
                quality_pref = audible_config.get('download_quality', 'best').lower()
            if quality_pref not in valid_qualities:
                quality_pref = 'best'

            logger.info(
                "Manual download queuing Audible title: asin=%s, title='%s', format=%s, quality=%s, priority=%s",
                asin_override,
                book.get('Title', 'Unknown'),
                format_pref,
                quality_pref,
                priority
            )

            queue_kwargs = {
                'title': book.get('Title', 'Unknown'),
                'author': book.get('Author', 'Unknown'),
                'download_type': 'audible',
                'audible_format': format_pref,
                'audible_quality': quality_pref,
                'indexer': result.get('indexer', 'Audible Library') or 'Audible Library',
                'file_size': result.get('size_bytes') or 0,
                'ownership_details': ownership_details
            }

            download_result = dm_service.add_to_queue(
                asin_override,
                search_result_id=None,
                priority=priority,
                **queue_kwargs
            )

            if download_result.get('success'):
                logger.info(
                    "Queued Audible download via manual download: asin=%s queue_id=%s",
                    asin_override,
                    download_result.get('download_id')
                )
                return jsonify({
                    'success': True,
                    'message': f"Audible download queued for {book.get('Title', 'Unknown')}",
                    'download_id': download_result.get('download_id'),
                    'audible_download': True,
                    'ownership_details': ownership_details
                }), 200

            error_message = download_result.get('message', 'Failed to queue Audible download')
            logger.error(
                "Failed to queue Audible download via manual download: asin=%s, error=%s",
                asin_override,
                error_message
            )
            if 'already in queue' in error_message.lower():
                return jsonify({
                    'success': False,
                    'error': 'This book is already in the download queue. Check the Downloads page to view its progress.',
                    'duplicate': True
                }), 409

            logger.error(f"Failed to queue Audible download for {book_asin}: {error_message}")
            return jsonify({'success': False, 'error': error_message}), 400
        
        # Prepare book metadata for queue
        queue_kwargs = {
            'title': book.get('Title', 'Unknown'),
            'author': book.get('Author', 'Unknown'),
            'download_url': result.get('download_url', ''),
            'indexer': result.get('indexer', 'Unknown'),
            'file_format': result.get('format', 'M4B'),
            'file_size': result.get('size_bytes', 0),
            'quality_score': result.get('quality_assessment', {}).get('total_score', 0) if isinstance(result.get('quality_assessment'), dict) else 0,
            'download_type': 'torrent'
        }
        
        # Add to download queue with the search result
        logger.info(f"Attempting to queue download for book {book_asin}: {book.get('Title', 'Unknown')}")
        logger.debug(f"Queue kwargs: {queue_kwargs}")
        
        download_result = dm_service.add_to_queue(
            book_asin,
            search_result_id=result.get('id'),
            priority=priority,
            **queue_kwargs
        )

        if download_result.get('success'):
            logger.info(f"Download queued via manual download: asin={book_asin}, id={download_result.get('download_id')}")
            return jsonify({
                'success': True,
                'message': f"Download queued for {book.get('Title', 'Unknown')}",
                'download_id': download_result.get('download_id')
            })
        else:
            logger.error(f"Failed to queue download for {book_asin}: {download_result.get('message')}")
            return jsonify({'success': False, 'error': download_result.get('message', 'Failed to queue download')}), 400
        
    except Exception as e:
        logger.error(f"Error initiating manual download: {e}")
        return jsonify({'error': str(e)}), 500

@manual_search_api_bp.route('/manual/suggestions', methods=['GET'])
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

@manual_search_api_bp.route('/books/wanted', methods=['GET'])
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

@manual_search_api_bp.route('/books/<int:book_id>/status', methods=['PUT'])
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

@manual_search_api_bp.route('/test', methods=['GET'])
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
