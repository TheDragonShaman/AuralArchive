"""
Module Name: authors.py
Author: TheDragonShaman
Created: July 15, 2025
Last Modified: December 23, 2025
Description:
    Route handlers for author dashboards, metadata enrichment, and catalog imports.
Location:
    /routes/authors.py

"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from services.service_manager import (
    get_database_service,
    get_audible_service,
    get_hybrid_audiobook_service,
    get_audnexus_service,
    get_metadata_update_service,
    get_download_management_service,
    get_config_service,
)
from services.image_cache import get_cached_author_image_url, cache_author_image
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
from utils.logger import get_module_logger

authors_bp = Blueprint('authors', __name__)
logger = get_module_logger("Routes.Authors")

# Author metadata refresh cadence (hours)
_AUTHOR_METADATA_MAX_AGE_HOURS = 24


def get_preferred_author_languages() -> Optional[Set[str]]:
    """Fetch the configured language preferences for author catalog filtering."""

    try:
        config_service = get_config_service()
        return config_service.get_author_preferred_languages()
    except Exception as exc:
        logger.debug(f"Unable to load preferred author languages: {exc}")
        return None


def _normalize_language_candidates(language_value: Any) -> Set[str]:
    """Derive matching tokens for a language string to compare with preferences."""

    if language_value is None:
        return set()

    normalized = str(language_value).strip().lower()
    if not normalized:
        return set()

    candidates: Set[str] = {normalized}

    if '-' in normalized:
        candidates.add(normalized.split('-', 1)[0])

    if '(' in normalized:
        candidates.add(normalized.split('(', 1)[0].strip())

    if '/' in normalized:
        candidates.update(part.strip() for part in normalized.split('/') if part.strip())

    if ' ' in normalized:
        candidates.add(normalized.split(' ', 1)[0])

    return candidates


def language_allowed(language_value: Any, preferred_languages: Optional[Set[str]]) -> bool:
    """Determine whether a language value matches the preferred language configuration."""

    if not preferred_languages:
        return True

    candidates = _normalize_language_candidates(language_value)
    if not candidates:
        return True

    return any(token in preferred_languages for token in candidates)


def format_language_labels(preferred_languages: Optional[Set[str]]) -> List[str]:
    """Convert language preference tokens into human-readable labels."""

    if not preferred_languages:
        return []

    labels: List[str] = []
    for token in sorted(preferred_languages):
        if token in {'english', 'en'}:
            labels.append('English')
        elif len(token) <= 3:
            labels.append(token.upper())
        else:
            labels.append(token.title())

    return labels


def gather_import_candidates(
    author_name: str,
    preferred_languages: Optional[Set[str]],
    series_name: Optional[str] = None,
    standalone_only: bool = False,
    asin_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Collect catalog entries suitable for import, applying filters and tracking skips."""

    response: Dict[str, Any] = {
        'subset_raw': [],
        'subset_formatted': [],
        'total_candidates': 0,
        'language_skipped': 0,
        'missing_raw': 0,
        'error': None,
    }

    try:
        hybrid_service = get_hybrid_audiobook_service()
        raw_books, formatted_books = hybrid_service.fetch_author_catalog(author_name)
    except Exception as exc:
        response['error'] = f"Failed to retrieve catalog for {author_name}: {exc}"
        logger.error(response['error'])
        return response

    if not formatted_books:
        response['error'] = f"No catalog data available for {author_name}."
        return response

    raw_lookup = {
        product.get('asin'): product
        for product in raw_books
        if product.get('asin')
    }

    if series_name:
        series_name = series_name.strip()
        standalone_only = False  # Series selection takes precedence

    if asin_filter:
        asin_filter = asin_filter.strip()

    for book in formatted_books:
        series_value = book.get('Series') or book.get('series')
        series_value_clean = (series_value or '').strip()
        asin_value = book.get('ASIN') or book.get('asin')

        if series_name and series_value_clean != series_name:
            continue

        if standalone_only and series_value_clean not in ('', 'N/A'):
            continue

        if asin_filter and asin_value != asin_filter:
            continue

        response['total_candidates'] += 1

        language_value = book.get('Language') or book.get('language')
        if not language_allowed(language_value, preferred_languages):
            response['language_skipped'] += 1
            continue

        if not asin_value:
            response['missing_raw'] += 1
            continue

        raw_product = raw_lookup.get(asin_value)
        if not raw_product:
            response['missing_raw'] += 1
            continue

        response['subset_formatted'].append(book)
        response['subset_raw'].append(raw_product)

    return response

# ============================================================================
# UTILITY FUNCTIONS - ENHANCED
# ============================================================================

def format_author_for_template(author_name: str, books: List[Dict], enhanced: bool = False) -> Dict[str, Any]:
    """Enhanced format author data for MediaVault template with advanced analytics."""
    total_books = len(books)
    
    # Enhanced series analysis
    series_books = defaultdict(list)
    standalone_books = []
    
    for book in books:
        series = book.get('Series', 'N/A')
        if series == 'N/A':
            standalone_books.append(book)
        else:
            series_books[series].append(book)
    
    # Calculate comprehensive runtime statistics
    total_hours = 0
    runtimes = []
    for book in books:
        runtime = book.get('Runtime', '0 hrs 0 mins')
        try:
            if 'hrs' in runtime:
                hours = int(runtime.split(' hrs')[0])
                minutes = int(runtime.split(' hrs ')[1].split(' mins')[0]) if ' mins' in runtime else 0
                total_runtime = hours + (minutes / 60)
                total_hours += total_runtime
                runtimes.append(total_runtime)
        except:
            pass
    
    # Enhanced status analysis
    status_counts = {}
    owned_count = 0
    missing_count = 0
    
    for book in books:
        status = book.get('Status', 'Unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
        
        if status == 'Owned':
            owned_count += 1
        else:
            missing_count += 1
    
    # Get most recent book
    books_with_dates = [b for b in books if b.get('Created At')]
    recent_book = max(books_with_dates, key=lambda x: x.get('Created At', ''), default=None)
    
    # Narrator and publisher analysis
    narrators = set()
    publishers = set()
    for book in books:
        if book.get('Narrator') and book.get('Narrator') != 'Unknown':
            narrators.add(book.get('Narrator'))
        if book.get('Publisher') and book.get('Publisher') != 'Unknown':
            publishers.add(book.get('Publisher'))
    
    # Get author metadata from database
    db_service = get_database_service()
    author_metadata = db_service.authors.get_author_metadata(author_name)
    
    # Calculate completion rate
    completion_rate = (owned_count / total_books * 100) if total_books > 0 else 0
    
    # Find primary publisher
    publisher_counts = {}
    for book in books:
        publisher = book.get('Publisher', 'Unknown')
        if publisher != 'Unknown':
            publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1
    primary_publisher = max(publisher_counts, key=publisher_counts.get, default='Unknown') if publisher_counts else 'Unknown'
    
    # Build enhanced author data
    author_data = {
        'name': author_name,
        'book_count': total_books,
        'series_count': len(series_books),
        'standalone_count': len(standalone_books),
        'total_hours': int(total_hours),
        'avg_runtime': round(sum(runtimes) / len(runtimes), 1) if runtimes else 0,
        'status_counts': status_counts,
        'owned_count': owned_count,
        'missing_count': missing_count,
        'completion_rate': round(completion_rate, 1),
        'primary_publisher': primary_publisher,
        'recent_book': recent_book.get('Title', 'Unknown') if recent_book else 'No books',
        'cover_image': recent_book.get('Cover Image') if recent_book else None,
        'most_common_narrator': max(narrators, key=lambda n: sum(1 for b in books if b.get('Narrator') == n), default='Unknown') if narrators else 'Unknown',
        
        # Author metadata from database with cached images
        'author_image': get_cached_author_image_url(author_metadata) or author_metadata.get('author_image_url'),
        'author_bio': author_metadata.get('author_bio'),
        'audible_author_id': author_metadata.get('audible_author_id'),
        'author_page_url': author_metadata.get('author_page_url'),
        'last_fetched_at': author_metadata.get('last_fetched_at'),
        
        # Series information for similarity calculations
        'series_info': {
            'series_names': list(series_books.keys()),
            'series_count': len(series_books),
            'series_books': dict(series_books)
        }
    }
    
    # Add enhancement flags
    if enhanced:
        author_data['enhanced'] = True
        author_data['analytics_timestamp'] = datetime.now().isoformat()
    
    return author_data

def update_author_data_with_asin(author_name: str, author_asin: str = None) -> Dict[str, Any]:
    """
    Update author data in database using author ASIN with Audnexus lookup.
    
    Args:
        author_name: Name of the author
        author_asin: Optional author ASIN (if not provided, will try to get from Audnexus search)
    
    Returns:
        Dictionary with update status and author data
    """
    try:
        audnexus_service = get_audnexus_service()
        db_service = get_database_service()
        
        # If no ASIN provided, try to find author by name
        if not author_asin:
            logger.info(f"Looking up author ASIN for: {author_name}")
            authors = audnexus_service.search_authors(author_name, num_results=5)
            
            if not authors:
                return {
                    'success': False,
                    'error': f'No authors found for "{author_name}" on Audnexus',
                    'source': 'audnexus_search'
                }
            
            # Try to find exact match or closest match
            exact_match = None
            for author in authors:
                if author.get('name', '').lower() == author_name.lower():
                    exact_match = author
                    break
            
            if exact_match:
                author_asin = exact_match.get('asin')
                logger.info(f"Found exact match for {author_name}: {author_asin}")
            else:
                # Use first result as best match
                author_asin = authors[0].get('asin')
                logger.info(f"Using best match for {author_name}: {author_asin}")
        
        if not author_asin:
            return {
                'success': False,
                'error': f'Could not determine author ASIN for "{author_name}"',
                'source': 'asin_lookup'
            }
        
        # Get detailed author info using ASIN
        logger.info(f"Fetching detailed author info for ASIN: {author_asin}")
        author_details = audnexus_service.get_author_details(author_asin)
        
        if not author_details:
            return {
                'success': False,
                'error': f'Could not fetch author details for ASIN "{author_asin}"',
                'source': 'audnexus_details'
            }
        
        # Prepare author metadata for database
        author_image_url = author_details.get('image')
        
        # Cache the image if available and prefer the cached URL for storage
        if author_image_url:
            cached_image_url = cache_author_image(author_image_url)
            author_image_url = cached_image_url or author_image_url
            logger.debug(f"Cached author image for {author_name}: {author_image_url} -> {cached_image_url}")
        
        author_metadata = {
            'name': author_name,
            'audible_author_id': author_asin,
            'author_image_url': author_image_url,
            'author_bio': author_details.get('description'),
            'author_page_url': f"https://www.audible.com/author/{author_details.get('name', '').replace(' ', '-')}/{author_asin}",
            'total_books_count': len(author_details.get('titles', [])),
            'audible_books_count': len(author_details.get('titles', []))
        }
        
        # Save to database
        success = db_service.authors.upsert_author_metadata(author_metadata)
        
        if success:
            logger.info(f"Successfully updated author data for {author_name} (ASIN: {author_asin})")
            return {
                'success': True,
                'author_name': author_name,
                'author_asin': author_asin,
                'author_data': author_metadata,
                'source': 'audnexus_asin'
            }
        else:
            return {
                'success': False,
                'error': f'Failed to save author metadata to database',
                'source': 'database_save'
            }
    
    except Exception as e:
        logger.error(f"Error updating author data for {author_name}: {e}")
        return {
            'success': False,
            'error': f'Exception during author update: {str(e)}',
            'source': 'exception'
        }


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Safely parse SQLite timestamp strings into datetime objects."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def enhance_author_with_external_data(author_name: str, author_data: Dict) -> Dict[str, Any]:
    """Enhance author data with external sources using hybrid service."""
    try:
        # Use hybrid service for better data quality
        hybrid_service = get_hybrid_audiobook_service()
        enhanced_data = author_data.copy()
        
        # Search for author to get additional books and metadata
        try:
            # Get enhanced author info from hybrid service
            author_info = hybrid_service.search_author_page(author_name)
            
            if author_info:
                # Update author data with enhanced information
                enhanced_data.update({
                    'author_image': author_info.get('author_image') or enhanced_data.get('author_image'),
                    'author_bio': author_info.get('author_bio') or enhanced_data.get('author_bio'),
                    'audible_author_id': author_info.get('audible_author_id') or enhanced_data.get('audible_author_id'),
                    'author_page_url': author_info.get('author_page_url') or enhanced_data.get('author_page_url'),
                    'data_source': author_info.get('source', 'hybrid')
                })
            
            # Get books by author using hybrid service
            audible_results = hybrid_service.get_author_books_from_audible(author_name, limit=30)
            
            # Get ASINs from current library
            db_service = get_database_service()
            library_books = db_service.get_books_by_author(author_name)
            library_asins = set(book.get('ASIN', '') for book in library_books if book.get('ASIN'))
            
            # Find books not in library
            missing_books = []
            for book in audible_results:
                if book.get('ASIN') and book.get('ASIN') not in library_asins:
                    missing_books.append({
                        'title': book.get('Title', ''),
                        'asin': book.get('ASIN', ''),
                        'series': book.get('Series', 'N/A'),
                        'release_date': book.get('Release Date', ''),
                        'runtime': book.get('Runtime', ''),
                        'rating': book.get('Overall Rating', ''),
                        'enhanced_by': book.get('enhanced_by', 'unknown')
                    })
            
            enhanced_data['external_discovery'] = {
                'missing_books_count': len(missing_books),
                'missing_books': missing_books[:10],
                'total_audible_books': len(audible_results),
                'library_coverage': round((len(library_asins) / len(audible_results)) * 100, 1) if audible_results else 100,
                'data_quality': 'hybrid_enhanced'
            }
            
        except Exception as e:
            logger.debug(f"Hybrid discovery failed for {author_name}: {e}")
            # Fallback to original audible service
            try:
                audible_service = get_audible_service()
                audible_results = audible_service.search_books(f"author:{author_name}", num_results=20)
                
                db_service = get_database_service()
                library_books = db_service.get_books_by_author(author_name)
                library_asins = set(book.get('ASIN', '') for book in library_books if book.get('ASIN'))
                
                missing_books = []
                for book in audible_results:
                    if book.get('ASIN') and book.get('ASIN') not in library_asins:
                        missing_books.append({
                            'title': book.get('Title', ''),
                            'asin': book.get('ASIN', ''),
                            'series': book.get('Series', 'N/A'),
                            'release_date': book.get('Release Date', ''),
                            'runtime': book.get('Runtime', ''),
                            'rating': book.get('Overall Rating', '')
                        })
                
                enhanced_data['external_discovery'] = {
                    'missing_books_count': len(missing_books),
                    'missing_books': missing_books[:10],
                    'total_audible_books': len(audible_results),
                    'library_coverage': round((len(library_asins) / len(audible_results)) * 100, 1) if audible_results else 100,
                    'data_quality': 'audible_fallback'
                }
                
            except Exception as fallback_error:
                logger.error(f"Both hybrid and fallback discovery failed for {author_name}: {fallback_error}")
                enhanced_data['external_discovery'] = {'error': str(e)}
        
        enhanced_data['enhancement_successful'] = True
        return enhanced_data
        
    except Exception as e:
        logger.error(f"Author enhancement failed for {author_name}: {e}")
        author_data['enhancement_error'] = str(e)
        return author_data

def update_author_from_asin(author_name: str, author_asin: str) -> Dict[str, Any]:
    """
    Update author metadata using author ASIN from Audnexus.
    This is the preferred method for accurate author data updates.
    """
    try:
        from services.service_manager import get_audnexus_service, get_database_service
        
        logger.info(f"Updating author {author_name} using ASIN: {author_asin}")
        
        audnexus_service = get_audnexus_service()
        db_service = get_database_service()
        
        # Get detailed author information from Audnexus using ASIN
        author_details = audnexus_service.get_author_details(author_asin)
        
        if not author_details:
            logger.warning(f"No author details found for ASIN {author_asin}")
            return {
                'success': False,
                'error': 'Author not found in Audnexus',
                'asin': author_asin
            }
        
        # Prepare author metadata for database
        author_metadata = {
            'name': author_name,
            'audible_author_id': author_asin,
            'author_image_url': author_details.get('image'),
            'author_bio': author_details.get('description'),
            'author_page_url': f"https://www.audible.com/author/{author_details.get('name', '').replace(' ', '-')}/{author_asin}",
            'total_books_count': 0,  # Will be calculated from actual library
            'audible_books_count': len(author_details.get('titles', [])) if author_details.get('titles') else 0
        }
        
        # Save to database
        success = db_service.authors.upsert_author_metadata(author_metadata)
        
        if success:
            logger.info(f"Successfully updated author {author_name} with ASIN {author_asin}")
            return {
                'success': True,
                'author_name': author_name,
                'asin': author_asin,
                'has_image': bool(author_metadata.get('author_image_url')),
                'has_bio': bool(author_metadata.get('author_bio')),
                'source': 'audnexus_asin'
            }
        else:
            return {
                'success': False,
                'error': 'Failed to save author metadata to database',
                'asin': author_asin
            }
    
    except Exception as e:
        logger.error(f"Error updating author {author_name} from ASIN {author_asin}: {e}")
        return {
            'success': False,
            'error': str(e),
            'asin': author_asin
        }


def ensure_author_metadata_cached(author_name: str, *, refresh_if_stale: bool = True) -> Dict[str, Any]:
    """Ensure author metadata exists and stays fresh; cache image locally."""

    db_service = get_database_service()
    metadata = db_service.authors.get_author_metadata(author_name) or {}

    needs_refresh = not metadata
    if refresh_if_stale and metadata:
        last_fetched = _parse_timestamp(metadata.get('last_fetched_at')) or _parse_timestamp(metadata.get('updated_at'))
        if not last_fetched:
            needs_refresh = True
        else:
            age = datetime.utcnow() - last_fetched
            if age > timedelta(hours=_AUTHOR_METADATA_MAX_AGE_HOURS):
                needs_refresh = True

    if needs_refresh:
        if metadata.get('audible_author_id'):
            refresh_result = update_author_from_asin(author_name, metadata['audible_author_id'])
        else:
            refresh_result = update_author_data_with_asin(author_name)

        if not refresh_result.get('success'):
            logger.debug(
                "Author metadata refresh skipped",
                extra={
                    "author": author_name,
                    "reason": refresh_result.get('error')
                }
            )
        else:
            metadata = db_service.authors.get_author_metadata(author_name) or {}

    image_url = metadata.get('author_image_url')
    if image_url:
        cached_url = cache_author_image(image_url)
        if cached_url and cached_url != image_url:
            metadata['author_image_url'] = cached_url
            db_service.authors.upsert_author_metadata(metadata)

    return metadata

def process_book_contributors_for_authors(book_data: Dict) -> List[Dict]:
    """
    Extract author ASINs from book contributors data and update author metadata.
    Call this function when a new book is added to automatically update author data.
    """
    results = []
    
    try:
        contributors = book_data.get('Contributors', [])
        if not isinstance(contributors, list):
            return results
        
        # Extract author contributors
        author_contributors = [
            c for c in contributors 
            if (isinstance(c, dict) and 
                c.get('Role') == 'Author' and 
                c.get('Name') and 
                c.get('ASIN'))
        ]
        
        for contributor in author_contributors:
            author_name = contributor.get('Name')
            author_asin = contributor.get('ASIN')
            
            if author_name and author_asin:
                logger.info(f"Processing author {author_name} with ASIN {author_asin} from book contributors")
                
                # Update author data using ASIN
                result = update_author_from_asin(author_name, author_asin)
                results.append({
                    'author_name': author_name,
                    'author_asin': author_asin,
                    'update_result': result
                })
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing book contributors for authors: {e}")
        return []

def calculate_author_similarity(author1_data: Dict, author2_data: Dict) -> float:
    """Calculate similarity score between two authors based on various factors."""
    score = 0.0
    
    # Series overlap
    series1 = set(author1_data.get('series_info', {}).get('series_names', []))
    series2 = set(author2_data.get('series_info', {}).get('series_names', []))
    if series1 and series2:
        series_overlap = len(series1 & series2) / len(series1 | series2)
        score += series_overlap * 0.3
    
    # Publisher similarity
    pub1 = author1_data.get('primary_publisher', '')
    pub2 = author2_data.get('primary_publisher', '')
    if pub1 and pub2 and pub1 == pub2 and pub1 != 'Unknown':
        score += 0.2
    
    # Book count similarity
    count1 = author1_data.get('book_count', 0)
    count2 = author2_data.get('book_count', 0)
    if count1 > 0 and count2 > 0:
        count_ratio = min(count1, count2) / max(count1, count2)
        score += count_ratio * 0.1
    
    # Publication timeline overlap
    span1 = author1_data.get('publication_span', {})
    span2 = author2_data.get('publication_span', {})
    if (span1.get('earliest') and span1.get('latest') and 
        span2.get('earliest') and span2.get('latest')):
        
        overlap_start = max(span1['earliest'], span2['earliest'])
        overlap_end = min(span1['latest'], span2['latest'])
        
        if overlap_end >= overlap_start:
            overlap_years = overlap_end - overlap_start + 1
            total_span = max(span1['latest'], span2['latest']) - min(span1['earliest'], span2['earliest']) + 1
            timeline_similarity = overlap_years / total_span if total_span > 0 else 0
            score += timeline_similarity * 0.2
    
    return score

# ============================================================================
# MAIN AUTHOR ROUTES - ENHANCED
# ============================================================================

@authors_bp.route('/')
@login_required
def authors_page():
    """Enhanced authors page with MediaVault design and advanced analytics."""
    try:
        db_service = get_database_service()
        all_authors = db_service.get_all_authors()
        
        # Get sorting and filtering parameters
        sort_by = request.args.get('sort', 'book_count')
        order = request.args.get('order', 'desc')
        filter_by = request.args.get('filter', '')
        enhance = request.args.get('enhance', 'false').lower() == 'true'
        
        logger.info(f"Loading authors page: {len(all_authors)} authors, sort={sort_by}, enhance={enhance}")
        
        # Format authors for template
        authors_data = []
        for author in all_authors:
            books = db_service.get_books_by_author(author)
            
            # Apply filter if specified
            if filter_by:
                books = [book for book in books if book.get('Status', '').lower() == filter_by.lower()]
                if not books:
                    continue
            
            formatted_author = format_author_for_template(author, books, enhanced=enhance)
            
            # Optional enhancement with external data
            if enhance:
                formatted_author = enhance_author_with_external_data(author, formatted_author)
            
            authors_data.append(formatted_author)
        
        # Sort authors
        reverse_order = order == 'desc'
        if sort_by == 'name':
            authors_data.sort(key=lambda x: x['name'].lower(), reverse=reverse_order)
        elif sort_by == 'hours':
            authors_data.sort(key=lambda x: x['total_hours'], reverse=reverse_order)
        elif sort_by == 'completion':
            authors_data.sort(key=lambda x: x['completion_rate'], reverse=reverse_order)
        else:  # Default: book_count
            authors_data.sort(key=lambda x: x['book_count'], reverse=reverse_order)
        
        # Calculate summary statistics
        summary_stats = {
            'total_authors': len(authors_data),
            'total_books': sum(author['book_count'] for author in authors_data),
            'total_hours': sum(author['total_hours'] for author in authors_data),
            'avg_books_per_author': round(sum(author['book_count'] for author in authors_data) / len(authors_data), 1) if authors_data else 0,
            'top_author': max(authors_data, key=lambda x: x['book_count'], default={'name': 'None', 'book_count': 0})
        }
        
        return render_template('authors.html',
                             title='Authors - Enhanced Analytics',
                             authors=authors_data,
                             summary_stats=summary_stats,
                             sort_by=sort_by,
                             order=order,
                             filter_by=filter_by,
                             enhanced=enhance)
    
    except Exception as e:
        logger.error(f"Error loading authors page: {e}")
        return render_template('authors.html',
                             title='Authors',
                             authors=[],
                             summary_stats={'total_authors': 0},
                             error=str(e))

@authors_bp.route('/<author_name>')
def author_detail_page(author_name):
    """Detailed author page with comprehensive analytics."""
    # Ignore browser requests for favicon
    if author_name in ('favicon.ico', 'robots.txt', 'sitemap.xml'):
        from flask import abort
        abort(404)
    
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return render_template('author_detail.html',
                                 title=f'Author: {author_name}',
                                 author_name=author_name,
                                 error='Author not found'), 404

        ensure_author_metadata_cached(author_name, refresh_if_stale=True)
        
        # Build library lookup for quick enrichment
        library_book_map = {}
        library_asins = set()
        for book in books:
            asin = book.get('ASIN')
            if asin:
                library_asins.add(asin)
                library_book_map[asin] = book
        
        # Get comprehensive author data
        author_data = format_author_for_template(author_name, books, enhanced=True)
        author_data = enhance_author_with_external_data(author_name, author_data)
        
        # Fetch complete catalogue from hybrid service to compare library coverage
        hybrid_catalog = []
        catalog_error = None
        try:
            hybrid_service = get_hybrid_audiobook_service()
            hybrid_catalog = hybrid_service.get_author_books_from_audible(
                author_name,
                persist_to_database=False
            )
        except Exception as catalog_exc:
            catalog_error = str(catalog_exc)
            logger.warning(f"Hybrid catalogue lookup failed for {author_name}: {catalog_exc}")
        
        catalog_books = []
        missing_books = []
        series_catalog = defaultdict(list)
        catalog_standalones = []

        preferred_languages = get_preferred_author_languages()
        language_filtered_count = 0
        if preferred_languages:
            logger.debug(
                "Applying author language filter for %s (allowed: %s)",
                author_name,
                ', '.join(sorted(preferred_languages))
            )
        
        def _to_number(value: str) -> float:
            try:
                if value is None:
                    return 9999
                value_str = str(value).strip()
                if value_str == '':
                    return 9999
                return float(value_str)
            except Exception:
                return 9999
        
        if hybrid_catalog:
            for catalog_book in hybrid_catalog:
                asin = catalog_book.get('ASIN') or ''
                in_library = asin in library_asins if asin else False
                library_info = library_book_map.get(asin, {}) if asin else {}
                status = library_info.get('Status') or ('Owned' if in_library else 'Missing')
                language_value = (
                    catalog_book.get('Language')
                    or catalog_book.get('language')
                    or library_info.get('Language')
                )
                if isinstance(language_value, str):
                    language_value = language_value.strip()
                entry = {
                    'title': catalog_book.get('Title') or library_info.get('Title', 'Unknown Title'),
                    'asin': asin,
                    'series': catalog_book.get('Series', library_info.get('Series', 'N/A')) or 'N/A',
                    'sequence': catalog_book.get('Sequence', library_info.get('Sequence', '')),
                    'runtime': catalog_book.get('Runtime', library_info.get('Runtime', '')),
                    'rating': catalog_book.get('Overall Rating', library_info.get('Overall Rating', '')),
                    'release_date': catalog_book.get('Release Date', library_info.get('Release Date', 'Unknown')),
                    'summary': catalog_book.get('Summary', library_info.get('Summary')),
                    'cover_image': catalog_book.get('Cover Image', library_info.get('Cover Image')),
                    'status': status,
                    'in_library': in_library,
                    'source': catalog_book.get('enhanced_by', 'audible'),
                    'language': language_value
                }
                if not language_allowed(entry.get('language'), preferred_languages):
                    language_filtered_count += 1
                    continue
                catalog_books.append(entry)
                if not in_library:
                    missing_books.append(entry)
                if entry['series'] and entry['series'] != 'N/A':
                    series_catalog[entry['series']].append(entry)
                else:
                    catalog_standalones.append(entry)
        else:
            # Fallback to library data if catalogue lookup failed
            for library_book in books:
                asin = library_book.get('ASIN', '')
                language_value = library_book.get('Language', '')
                if isinstance(language_value, str):
                    language_value = language_value.strip()
                entry = {
                    'title': library_book.get('Title', 'Unknown Title'),
                    'asin': asin,
                    'series': library_book.get('Series', 'N/A'),
                    'sequence': library_book.get('Sequence', ''),
                    'runtime': library_book.get('Runtime', ''),
                    'rating': library_book.get('Overall Rating', ''),
                    'release_date': library_book.get('Release Date', 'Unknown'),
                    'summary': library_book.get('Summary'),
                    'cover_image': library_book.get('Cover Image'),
                    'status': library_book.get('Status', 'Owned'),
                    'in_library': True,
                    'source': 'library',
                    'language': language_value
                }
                if not language_allowed(entry.get('language'), preferred_languages):
                    language_filtered_count += 1
                    continue
                catalog_books.append(entry)
                if entry['series'] and entry['series'] != 'N/A':
                    series_catalog[entry['series']].append(entry)
                else:
                    catalog_standalones.append(entry)

        # Ensure every library book appears in the catalogue even if the external source missed it
        catalog_asins = {entry.get('asin') for entry in catalog_books if entry.get('asin')}
        for library_book in books:
            asin = library_book.get('ASIN')
            if not asin or asin in catalog_asins:
                continue

            language_value = library_book.get('Language', '')
            if isinstance(language_value, str):
                language_value = language_value.strip()

            entry = {
                'title': library_book.get('Title', 'Unknown Title'),
                'asin': asin,
                'series': library_book.get('Series', 'N/A'),
                'sequence': library_book.get('Sequence', ''),
                'runtime': library_book.get('Runtime', ''),
                'rating': library_book.get('Overall Rating', ''),
                'release_date': library_book.get('Release Date', 'Unknown'),
                'summary': library_book.get('Summary'),
                'cover_image': library_book.get('Cover Image'),
                'status': library_book.get('Status', 'Owned'),
                'in_library': True,
                'source': 'library',
                'language': language_value
            }

            if not language_allowed(entry.get('language'), preferred_languages):
                language_filtered_count += 1
                continue

            catalog_books.append(entry)
            catalog_asins.add(asin)
            if entry['series'] and entry['series'] != 'N/A':
                series_catalog[entry['series']].append(entry)
            else:
                catalog_standalones.append(entry)
        
        # Sort catalogue groupings for display
        for series_name in series_catalog:
            series_catalog[series_name].sort(key=lambda x: (_to_number(x.get('sequence')), x.get('title')))
        ordered_series_catalog = dict(sorted(series_catalog.items(), key=lambda item: item[0].lower()))
        catalog_standalones.sort(key=lambda x: x.get('title', '').lower())
        catalog_books.sort(key=lambda x: (x.get('series', 'ZZZ').lower(), _to_number(x.get('sequence')), x.get('title', '').lower()))
        missing_books.sort(key=lambda x: (x.get('series', 'ZZZ').lower(), _to_number(x.get('sequence')), x.get('title', '').lower()))

        for index, book in enumerate(catalog_books, start=1):
            book['catalogue_index'] = index
        
        if catalog_books:
            owned_catalog = sum(1 for book in catalog_books if book.get('in_library'))
            coverage_percentage = round((owned_catalog / len(catalog_books)) * 100, 1)
        elif hybrid_catalog:
            coverage_percentage = 0
        else:
            coverage_percentage = 100

        display_language_values = format_language_labels(preferred_languages)
        
        catalogue_context = {
            'books': catalog_books,
            'missing_books': missing_books,
            'series_catalog': ordered_series_catalog,
            'standalone_catalog': catalog_standalones,
            'coverage_percentage': coverage_percentage,
            'catalogue_error': catalog_error,
            'catalogue_size': len(catalog_books),
            'language_filter_applied': bool(preferred_languages),
            'language_filter_values': display_language_values,
            'language_filtered_count': language_filtered_count
        }
        
        return render_template('author_detail.html',
                             title=f'Author: {author_name}',
                             author_data=author_data,
                             catalogue=catalogue_context)
    
    except Exception as e:
        logger.error(f"Error loading author detail for {author_name}: {e}")
        return render_template('author_detail.html',
                             title=f'Author: {author_name}',
                             author_name=author_name,
                             error=str(e)), 500


@authors_bp.post('/api/import-series')
def import_author_series():
    """Persist all books for a specific series into the library database."""

    payload = request.get_json(silent=True) or {}
    author_name = (payload.get('author_name') or request.form.get('author_name') or '').strip()
    series_name = (payload.get('series_name') or request.form.get('series_name') or '').strip()

    if not author_name:
        return jsonify({'success': False, 'error': 'Author name is required.'}), 400

    if not series_name:
        return jsonify({'success': False, 'error': 'Series name is required.'}), 400

    preferred_languages = get_preferred_author_languages()

    candidates = gather_import_candidates(author_name, preferred_languages, series_name=series_name)

    if candidates.get('error'):
        return jsonify({'success': False, 'error': candidates['error']}), 500

    subset_raw = candidates['subset_raw']
    subset_formatted = candidates['subset_formatted']

    if not subset_formatted:
        message = 'No matching titles found for import.'
        if candidates['language_skipped']:
            message = (
                f"No titles matched your language filters for series '{series_name}'."
            )
        return jsonify({
            'success': False,
            'error': message,
            'language_skipped': candidates['language_skipped'],
            'missing_raw': candidates['missing_raw'],
            'total_candidates': candidates['total_candidates'],
        }), 200

    audible_service = get_audible_service()
    result = audible_service.persist_author_catalog(author_name, subset_raw, subset_formatted)

    imported = result.get('books_successful', 0)
    failed = result.get('books_failed', 0)

    message = (
        f"Imported {imported} title{'s' if imported != 1 else ''} from "
        f"series '{series_name}'."
    )

    return jsonify({
        'success': True,
        'imported': imported,
        'failed': failed,
        'series_imported': result.get('series_successful', 0),
        'series_failed': result.get('series_failed', 0),
        'language_skipped': candidates['language_skipped'],
        'missing_raw': candidates['missing_raw'],
        'total_candidates': candidates['total_candidates'],
        'message': message,
    })


@authors_bp.post('/api/import-author')
def import_author_catalog():
    """Persist the entire filtered author catalog into the library database."""

    payload = request.get_json(silent=True) or {}
    author_name = (payload.get('author_name') or request.form.get('author_name') or '').strip()

    if not author_name:
        return jsonify({'success': False, 'error': 'Author name is required.'}), 400

    preferred_languages = get_preferred_author_languages()
    candidates = gather_import_candidates(author_name, preferred_languages)

    if candidates.get('error'):
        return jsonify({'success': False, 'error': candidates['error']}), 500

    subset_raw = candidates['subset_raw']
    subset_formatted = candidates['subset_formatted']

    if not subset_formatted:
        message = 'No catalog titles available for import.'
        if candidates['language_skipped']:
            message = 'No catalog titles matched your language filters.'
        return jsonify({
            'success': False,
            'error': message,
            'language_skipped': candidates['language_skipped'],
            'missing_raw': candidates['missing_raw'],
            'total_candidates': candidates['total_candidates'],
        }), 200

    audible_service = get_audible_service()
    result = audible_service.persist_author_catalog(author_name, subset_raw, subset_formatted)

    imported = result.get('books_successful', 0)
    failed = result.get('books_failed', 0)

    message = (
        f"Imported {imported} catalog title{'s' if imported != 1 else ''} for {author_name}."
    )

    return jsonify({
        'success': True,
        'imported': imported,
        'failed': failed,
        'series_imported': result.get('series_successful', 0),
        'series_failed': result.get('series_failed', 0),
        'language_skipped': candidates['language_skipped'],
        'missing_raw': candidates['missing_raw'],
        'total_candidates': candidates['total_candidates'],
        'message': message,
    })


@authors_bp.post('/api/import-standalone')
def import_author_standalones():
    """Persist all standalone catalog titles for an author into the library."""

    payload = request.get_json(silent=True) or {}
    author_name = (payload.get('author_name') or request.form.get('author_name') or '').strip()

    if not author_name:
        return jsonify({'success': False, 'error': 'Author name is required.'}), 400

    preferred_languages = get_preferred_author_languages()
    candidates = gather_import_candidates(
        author_name,
        preferred_languages,
        standalone_only=True,
    )

    if candidates.get('error'):
        return jsonify({'success': False, 'error': candidates['error']}), 500

    subset_raw = candidates['subset_raw']
    subset_formatted = candidates['subset_formatted']

    if not subset_formatted:
        message = 'No standalone titles available for import.'
        if candidates['language_skipped']:
            message = 'No standalone titles matched your language filters.'
        return jsonify({
            'success': False,
            'error': message,
            'language_skipped': candidates['language_skipped'],
            'missing_raw': candidates['missing_raw'],
            'total_candidates': candidates['total_candidates'],
        }), 200

    audible_service = get_audible_service()
    result = audible_service.persist_author_catalog(author_name, subset_raw, subset_formatted)

    imported = result.get('books_successful', 0)
    failed = result.get('books_failed', 0)

    message = (
        f"Imported {imported} standalone title{'s' if imported != 1 else ''} for {author_name}."
    )

    return jsonify({
        'success': True,
        'imported': imported,
        'failed': failed,
        'series_imported': result.get('series_successful', 0),
        'series_failed': result.get('series_failed', 0),
        'language_skipped': candidates['language_skipped'],
        'missing_raw': candidates['missing_raw'],
        'total_candidates': candidates['total_candidates'],
        'message': message,
    })


@authors_bp.post('/api/import-book')
def import_single_catalog_book():
    """Persist a single catalog title for an author into the library."""

    payload = request.get_json(silent=True) or {}
    author_name = (payload.get('author_name') or request.form.get('author_name') or '').strip()
    asin = (payload.get('asin') or request.form.get('asin') or '').strip()

    if not author_name:
        return jsonify({'success': False, 'error': 'Author name is required.'}), 400

    if not asin:
        return jsonify({'success': False, 'error': 'ASIN is required.'}), 400

    preferred_languages = get_preferred_author_languages()
    candidates = gather_import_candidates(
        author_name,
        preferred_languages,
        asin_filter=asin,
    )

    if candidates.get('error'):
        return jsonify({'success': False, 'error': candidates['error']}), 500

    subset_raw = candidates['subset_raw']
    subset_formatted = candidates['subset_formatted']

    if not subset_formatted:
        message = 'Catalog title not available for import.'
        if candidates['language_skipped']:
            message = 'This title does not match your language filters.'
        elif candidates['missing_raw']:
            message = 'Full metadata for this title was not available.'
        return jsonify({
            'success': False,
            'error': message,
            'language_skipped': candidates['language_skipped'],
            'missing_raw': candidates['missing_raw'],
            'total_candidates': candidates['total_candidates'],
        }), 200

    audible_service = get_audible_service()
    result = audible_service.persist_author_catalog(author_name, subset_raw, subset_formatted)

    imported = result.get('books_successful', 0)
    failed = result.get('books_failed', 0)

    message = 'Title imported successfully.' if imported else 'No updates were applied.'

    return jsonify({
        'success': imported > 0,
        'imported': imported,
        'failed': failed,
        'series_imported': result.get('series_successful', 0),
        'series_failed': result.get('series_failed', 0),
        'language_skipped': candidates['language_skipped'],
        'missing_raw': candidates['missing_raw'],
        'total_candidates': candidates['total_candidates'],
        'message': message,
    })

def get_author_recommendations(target_author: str, target_data: Dict) -> List[Dict]:
    """Get author recommendations based on similarity analysis."""
    try:
        db_service = get_database_service()
        all_authors = db_service.get_all_authors()
        
        recommendations = []
        
        for author in all_authors:
            if author == target_author:
                continue
            
            books = db_service.get_books_by_author(author)
            if len(books) < 2:  # Skip authors with very few books
                continue
            
            author_data = format_author_for_template(author, books)
            similarity_score = calculate_author_similarity(target_data, author_data)
            
            if similarity_score > 0.3:  # Threshold for recommendations
                recommendations.append({
                    'author': author,
                    'similarity_score': round(similarity_score, 3),
                    'book_count': author_data['book_count'],
                    'primary_publisher': author_data['primary_publisher'],
                    'reason': get_similarity_reason(target_data, author_data)
                })
        
        # Sort by similarity score and limit to top 10
        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:10]
        
    except Exception as e:
        logger.error(f"Error getting recommendations for {target_author}: {e}")
        return []

def get_similarity_reason(author1_data: Dict, author2_data: Dict) -> str:
    """Generate human-readable reason for author similarity."""
    reasons = []
    
    # Check publisher
    if (author1_data.get('primary_publisher') == author2_data.get('primary_publisher') and 
        author1_data.get('primary_publisher') != 'Unknown'):
        reasons.append(f"Same publisher ({author1_data['primary_publisher']})")
    
    # Check book count similarity
    count1 = author1_data.get('book_count', 0)
    count2 = author2_data.get('book_count', 0)
    if count1 > 0 and count2 > 0:
        ratio = min(count1, count2) / max(count1, count2)
        if ratio > 0.7:
            reasons.append(f"Similar productivity ({min(count1, count2)}-{max(count1, count2)} books)")
    
    return "; ".join(reasons) if reasons else "Similar publishing patterns"

# ============================================================================
# API ENDPOINTS - ENHANCED
# ============================================================================

@authors_bp.route('/api/list')
def api_get_authors():
    """Enhanced API endpoint for getting authors with analytics."""
    try:
        db_service = get_database_service()
        
        # Get parameters
        include_stats = request.args.get('include_stats', 'false').lower() == 'true'
        sort_by = request.args.get('sort', 'book_count')
        limit = request.args.get('limit', type=int)
        search = request.args.get('search', '').strip()
        
        all_authors = db_service.get_all_authors()
        authors_data = []
        
        for author in all_authors:
            # Apply search filter
            if search and search.lower() not in author.lower():
                continue
            
            books = db_service.get_books_by_author(author)
            
            if include_stats:
                author_info = format_author_for_template(author, books)
            else:
                # Basic info only for performance
                author_info = {
                    'name': author,
                    'book_count': len(books)
                }
            
            authors_data.append(author_info)
        
        # Sort authors
        if sort_by == 'name':
            authors_data.sort(key=lambda x: x['name'].lower())
        elif sort_by == 'hours' and include_stats:
            authors_data.sort(key=lambda x: x.get('total_hours', 0), reverse=True)
        else:  # Default: book_count
            authors_data.sort(key=lambda x: x['book_count'], reverse=True)
        
        # Apply limit
        if limit:
            authors_data = authors_data[:limit]
        
        return jsonify({
            'success': True,
            'authors': authors_data,
            'count': len(authors_data),
            'total_authors': len(all_authors),
            'include_stats': include_stats
        })
    
    except Exception as e:
        logger.error(f"Error getting authors list: {e}")
        return jsonify({'error': f'Failed to get authors: {str(e)}'}), 500

@authors_bp.route('/api/top')
def api_get_top_authors():
    """Enhanced API endpoint for getting top authors by various metrics."""
    try:
        db_service = get_database_service()
        all_authors = db_service.get_all_authors()
        
        metric = request.args.get('metric', 'books')  # books, hours, rating, completion
        limit = request.args.get('limit', 10, type=int)
        
        author_data = []
        for author in all_authors:
            books = db_service.get_books_by_author(author)
            if len(books) < 2:  # Skip authors with very few books
                continue
            
            formatted_author = format_author_for_template(author, books)
            author_data.append(formatted_author)
        
        # Sort by specified metric
        if metric == 'books':
            author_data.sort(key=lambda x: x['book_count'], reverse=True)
        elif metric == 'hours':
            author_data.sort(key=lambda x: x['total_hours'], reverse=True)
        elif metric == 'completion':
            author_data.sort(key=lambda x: x['completion_rate'], reverse=True)
        elif metric == 'series':
            author_data.sort(key=lambda x: x['series_count'], reverse=True)
        
        # Apply limit
        top_authors = author_data[:limit]
        
        return jsonify({
            'success': True,
            'metric': metric,
            'top_authors': top_authors,
            'count': len(top_authors)
        })
    
    except Exception as e:
        logger.error(f"Error getting top authors: {e}")
        return jsonify({'error': 'Failed to get top authors'}), 500

# ============================================================================
# AUTHOR MANAGEMENT AND METADATA
# ============================================================================

@authors_bp.route('/api/<author_name>/enhance', methods=['POST'])
def api_enhance_author_metadata(author_name):
    """API endpoint to enhance author metadata using external services."""
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return jsonify({'error': 'Author not found'}), 404
        
        logger.info(f"Enhancing metadata for author: {author_name}")
        
        enhancement_results = {
            'author': author_name,
            'original_book_count': len(books),
            'enhancements': {},
            'errors': []
        }
        
        # Get base author data
        author_data = format_author_for_template(author_name, books)
        
        # Enhance with external discovery
        try:
            enhanced_data = enhance_author_with_external_data(author_name, author_data)
            enhancement_results['enhancements']['external_discovery'] = enhanced_data.get('external_discovery', {})
            enhancement_results['enhancements']['download_availability'] = enhanced_data.get('download_availability', {})
        except Exception as e:
            enhancement_results['errors'].append(f"External discovery failed: {str(e)}")
        
        # Optional: Trigger metadata updates for existing books
        update_existing = request.json.get('update_existing_books', False) if request.json else False
        if update_existing:
            try:
                metadata_service = get_metadata_update_service()
                book_ids = [book.get('ID') for book in books if book.get('ID')]
                
                if book_ids:
                    update_results = metadata_service.update_multiple_books(book_ids[:5])  # Limit to 5 for performance
                    enhancement_results['enhancements']['metadata_updates'] = {
                        'attempted': min(5, len(book_ids)),
                        'successful': update_results.get('successful', 0),
                        'failed': update_results.get('failed', 0)
                    }
            except Exception as e:
                enhancement_results['errors'].append(f"Metadata updates failed: {str(e)}")
        
        return jsonify({
            'success': True,
            'results': enhancement_results,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error enhancing author {author_name}: {e}")
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

@authors_bp.route('/api/<author_name>/missing-books/add', methods=['POST'])
def api_add_missing_books(author_name):
    """API endpoint to add discovered missing books to the library."""
    try:
        db_service = get_database_service()
        
        data = request.json or {}
        book_asins = data.get('asins', [])
        
        if not book_asins:
            return jsonify({'error': 'No book ASINs provided'}), 400
        
        logger.info(f"Adding {len(book_asins)} missing books for author: {author_name}")
        
        # Get book details from hybrid service for each ASIN
        hybrid_service = get_hybrid_audiobook_service()
        results = {
            'author': author_name,
            'requested_asins': book_asins,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'details': []
        }
        
        for asin in book_asins:
            try:
                # Check if book already exists
                if db_service.check_book_exists(asin):
                    results['skipped'] += 1
                    results['details'].append({
                        'asin': asin,
                        'status': 'skipped',
                        'reason': 'Already in library'
                    })
                    continue
                
                # Search for book details using hybrid service
                book_results = hybrid_service.search_books(asin, num_results=1)
                if not book_results:
                    results['failed'] += 1
                    results['details'].append({
                        'asin': asin,
                        'status': 'failed',
                        'reason': 'Book not found on Audible'
                    })
                    continue
                
                book_data = book_results[0]
                
                # Verify author matches
                book_author = book_data.get('Author', '')
                if author_name.lower() not in book_author.lower():
                    results['failed'] += 1
                    results['details'].append({
                        'asin': asin,
                        'status': 'failed',
                        'reason': f'Author mismatch: {book_author}'
                    })
                    continue
                
                # Add to library
                if db_service.add_book(book_data, status="Wanted"):
                    results['successful'] += 1
                    results['details'].append({
                        'asin': asin,
                        'title': book_data.get('Title', ''),
                        'status': 'added',
                        'reason': 'Successfully added to library'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'asin': asin,
                        'status': 'failed',
                        'reason': 'Database error'
                    })
                    
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'asin': asin,
                    'status': 'failed',
                    'reason': str(e)
                })
        
        logger.info(f"Completed adding books for {author_name}: {results['successful']} successful, {results['failed']} failed, {results['skipped']} skipped")
        
        return jsonify({
            'success': True,
            'message': f"Added {results['successful']} books, skipped {results['skipped']}, failed {results['failed']}",
            'results': results
        })
    
    except Exception as e:
        logger.error(f"Error adding missing books for {author_name}: {e}")
        return jsonify({'error': f'Failed to add books: {str(e)}'}), 500

# ============================================================================
# ANALYTICS AND REPORTING
# ============================================================================

@authors_bp.route('/api/analytics')
def api_get_authors_analytics():
    """Comprehensive authors analytics and insights."""
    try:
        db_service = get_database_service()
        all_authors = db_service.get_all_authors()
        
        logger.info(f"Generating analytics for {len(all_authors)} authors")
        
        # Collect comprehensive data
        all_author_data = []
        for author in all_authors:
            books = db_service.get_books_by_author(author)
            author_data = format_author_for_template(author, books)
            all_author_data.append(author_data)
        
        # Calculate analytics
        analytics = {
            'overview': {
                'total_authors': len(all_author_data),
                'total_books': sum(a['book_count'] for a in all_author_data),
                'total_hours': sum(a['total_hours'] for a in all_author_data),
                'avg_books_per_author': round(sum(a['book_count'] for a in all_author_data) / len(all_author_data), 2) if all_author_data else 0
            },
            'distributions': {
                'books_per_author': {},
                'completion_rates': {},
                'publication_decades': {},
                'top_publishers': {},
                'top_narrators': {}
            },
            'top_performers': {
                'most_books': sorted(all_author_data, key=lambda x: x['book_count'], reverse=True)[:5],
                'most_hours': sorted(all_author_data, key=lambda x: x['total_hours'], reverse=True)[:5],
                'best_completion': sorted(all_author_data, key=lambda x: x['completion_rate'], reverse=True)[:5]
            }
        }
        
        # Calculate distributions
        for author_data in all_author_data:
            # Books per author distribution
            book_range = f"{(author_data['book_count'] // 5) * 5}-{(author_data['book_count'] // 5) * 5 + 4}"
            analytics['distributions']['books_per_author'][book_range] = analytics['distributions']['books_per_author'].get(book_range, 0) + 1
            
            # Completion rate distribution
            completion_range = f"{(int(author_data['completion_rate']) // 20) * 20}-{(int(author_data['completion_rate']) // 20) * 20 + 19}%"
            analytics['distributions']['completion_rates'][completion_range] = analytics['distributions']['completion_rates'].get(completion_range, 0) + 1
            
            # Publisher distribution
            publisher = author_data.get('primary_publisher', 'Unknown')
            if publisher != 'Unknown':
                analytics['distributions']['top_publishers'][publisher] = analytics['distributions']['top_publishers'].get(publisher, 0) + 1
            
            # Narrator distribution
            narrator = author_data.get('most_common_narrator', 'Unknown')
            if narrator != 'Unknown':
                analytics['distributions']['top_narrators'][narrator] = analytics['distributions']['top_narrators'].get(narrator, 0) + 1
        
        # Limit top lists to top 10
        analytics['distributions']['top_publishers'] = dict(sorted(analytics['distributions']['top_publishers'].items(), key=lambda x: x[1], reverse=True)[:10])
        analytics['distributions']['top_narrators'] = dict(sorted(analytics['distributions']['top_narrators'].items(), key=lambda x: x[1], reverse=True)[:10])
        
        return jsonify({
            'success': True,
            'analytics': analytics,
            'generated_at': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error generating authors analytics: {e}")
        return jsonify({'error': f'Analytics generation failed: {str(e)}'}), 500

@authors_bp.route('/api/export')
def api_export_authors():
    """Export authors data in various formats."""
    try:
        db_service = get_database_service()
        
        format_type = request.args.get('format', 'json')  # json, csv
        include_books = request.args.get('include_books', 'false').lower() == 'true'
        include_stats = request.args.get('include_stats', 'true').lower() == 'true'
        
        all_authors = db_service.get_all_authors()
        export_data = []
        
        for author in all_authors:
            books = db_service.get_books_by_author(author)
            
            if include_stats:
                author_data = format_author_for_template(author, books)
            else:
                author_data = {
                    'name': author,
                    'book_count': len(books)
                }
            
            if include_books:
                author_data['books'] = books
            
            export_data.append(author_data)
        
        if format_type == 'csv':
            import io
            import csv
            
            output = io.StringIO()
            if export_data and not include_books:
                fieldnames = ['name', 'book_count']
                if include_stats:
                    fieldnames.extend(['series_count', 'total_hours', 'completion_rate'])
                
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                
                for author_data in export_data:
                    row = {field: author_data.get(field, '') for field in fieldnames}
                    writer.writerow(row)
            
            return jsonify({
                'success': True,
                'export_data': output.getvalue(),
                'format': 'csv',
                'filename': f"authors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            })
        
        else:  # JSON format
            export_info = {
                'export_timestamp': datetime.now().isoformat(),
                'total_authors': len(export_data),
                'include_books': include_books,
                'include_stats': include_stats,
                'authors': export_data
            }
            
            return jsonify({
                'success': True,
                'export_data': export_info,
                'format': 'json',
                'filename': f"authors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            })
    
    except Exception as e:
        logger.error(f"Error exporting authors: {e}")
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@authors_bp.route('/api/similar/<author_name>')
def api_get_similar_authors(author_name):
    """Get authors similar to the specified author."""
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return jsonify({'error': 'Author not found'}), 404
        
        target_data = format_author_for_template(author_name, books)
        recommendations = get_author_recommendations(author_name, target_data)
        
        return jsonify({
            'success': True,
            'target_author': author_name,
            'similar_authors': recommendations,
            'count': len(recommendations),
            'algorithm': 'similarity_scoring'
        })
    
    except Exception as e:
        logger.error(f"Error getting similar authors for {author_name}: {e}")
        return jsonify({'error': f'Failed to get similar authors: {str(e)}'}), 500

@authors_bp.route('/api/health')
def api_authors_health():
    """Health check endpoint for authors service integration."""
    try:
        db_service = get_database_service()
        
        # Test basic functionality
        authors = db_service.get_all_authors()
        author_count = len(authors)
        
        # Test service integrations
        service_status = {
            'database': {'status': 'healthy', 'authors': author_count},
            'audible': {'status': 'unknown'},
            'hybrid': {'status': 'unknown'},
            'download': {'status': 'unknown'},
            'metadata': {'status': 'unknown'}
        }
        
        # Test Audible service
        try:
            audible_service = get_audible_service()
            test_results = audible_service.search_books('test', num_results=1)
            service_status['audible'] = {
                'status': 'healthy' if test_results else 'limited',
                'responsive': bool(test_results)
            }
        except Exception as e:
            service_status['audible'] = {'status': 'error', 'error': str(e)}
        
        # Test Hybrid service
        try:
            hybrid_service = get_hybrid_audiobook_service()
            test_results = hybrid_service.search_books('test', num_results=1)
            service_status['hybrid'] = {
                'status': 'healthy' if test_results else 'limited',
                'responsive': bool(test_results),
                'audnexus_available': hasattr(hybrid_service, 'audnexus_service') and hybrid_service.audnexus_service is not None
            }
        except Exception as e:
            service_status['hybrid'] = {'status': 'error', 'error': str(e)}
        
        # Test Download service
        try:
            download_service = get_download_management_service()
            if download_service:
                providers = download_service.get_available_providers()
                service_status['download'] = {
                    'status': 'healthy' if providers else 'limited',
                    'providers': len(providers)
                }
            else:
                service_status['download'] = {
                    'status': 'limited',
                    'providers': 0,
                    'details': 'Download service unavailable'
                }
        except Exception as e:
            service_status['download'] = {'status': 'error', 'error': str(e)}
        
        # Test Metadata service
        try:
            metadata_service = get_metadata_update_service()
            status = metadata_service.get_service_status()
            service_status['metadata'] = {
                'status': 'healthy' if status.get('initialized') else 'limited',
                'initialized': status.get('initialized', False)
            }
        except Exception as e:
            service_status['metadata'] = {'status': 'error', 'error': str(e)}
        
        # Calculate overall health
        healthy_services = sum(1 for s in service_status.values() if s['status'] == 'healthy')
        total_services = len(service_status)
        
        overall_status = 'healthy' if healthy_services == total_services else 'partial' if healthy_services > 0 else 'unhealthy'
        
        return jsonify({
            'success': True,
            'overall_status': overall_status,
            'services': service_status,
            'summary': f'{healthy_services}/{total_services} services healthy',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error in authors health check: {e}")
        return jsonify({
            'success': False,
            'overall_status': 'error',
            'error': str(e)
        }), 500

@authors_bp.route('/api/<author_name>/books')
def api_get_author_books(author_name):
    """Enhanced API endpoint for getting author's books with organization."""
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return jsonify({'error': 'Author not found'}), 404
        
        # Organize books by series
        series_groups = defaultdict(list)
        standalone_books = []
        
        for book in books:
            series = book.get('Series', 'N/A')
            if series == 'N/A':
                standalone_books.append(book)
            else:
                series_groups[series].append(book)
        
        # Sort books within each series by sequence
        for series in series_groups:
            series_groups[series].sort(key=lambda x: float(x.get('Sequence', '0')) if str(x.get('Sequence', '0')).replace('.', '').isdigit() else 999)
        
        return jsonify({
            'success': True,
            'author': author_name,
            'series_groups': dict(series_groups),
            'standalone_books': standalone_books,
            'total_books': len(books),
            'series_count': len(series_groups)
        })
    
    except Exception as e:
        logger.error(f"Error fetching books for author {author_name}: {e}")
        return jsonify({'error': 'Failed to fetch author books'}), 500

@authors_bp.route('/api/<author_name>/stats')
def api_get_author_stats(author_name):
    """Comprehensive API endpoint for author statistics and analytics."""
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return jsonify({'error': 'Author not found'}), 404
        
        # Get enhanced author data
        author_data = format_author_for_template(author_name, books, enhanced=True)
        
        # Optional external enhancement
        enhance = request.args.get('enhance', 'false').lower() == 'true'
        if enhance:
            author_data = enhance_author_with_external_data(author_name, author_data)
        
        return jsonify({
            'success': True,
            'author': author_name,
            'stats': author_data,
            'enhanced': enhance
        })
    
    except Exception as e:
        logger.error(f"Error getting author stats for {author_name}: {e}")
        return jsonify({'error': 'Failed to get author stats'}), 500

@authors_bp.route('/api/<author_name>/recommendations')
def api_get_author_recommendations(author_name):
    """API endpoint for getting author recommendations."""
    try:
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        if not books:
            return jsonify({'error': 'Author not found'}), 404
        
        author_data = format_author_for_template(author_name, books)
        recommendations = get_author_recommendations(author_name, author_data)
        
        return jsonify({
            'success': True,
            'author': author_name,
            'recommendations': recommendations,
            'count': len(recommendations)
        })
    
    except Exception as e:
        logger.error(f"Error getting recommendations for {author_name}: {e}")
        return jsonify({'error': 'Failed to get recommendations'}), 500

@authors_bp.route('/api/<author_name>/discover')
def api_discover_missing_books(author_name):
    """API endpoint for discovering missing books by an author."""
    try:
        db_service = get_database_service()
        hybrid_service = get_hybrid_audiobook_service()
        
        # Get current library books
        library_books = db_service.get_books_by_author(author_name)
        if not library_books:
            return jsonify({'error': 'Author not found in library'}), 404
        
        library_asins = set(book.get('ASIN', '') for book in library_books if book.get('ASIN'))
        
        # Search using hybrid service for all books by this author
        audible_results = hybrid_service.get_author_books_from_audible(author_name)
        
        # Find missing books
        missing_books = []
        for book in audible_results:
            if book.get('ASIN') and book.get('ASIN') not in library_asins:
                missing_books.append({
                    'title': book.get('Title', ''),
                    'asin': book.get('ASIN', ''),
                    'series': book.get('Series', 'N/A'),
                    'sequence': book.get('Sequence', ''),
                    'release_date': book.get('Release Date', ''),
                    'runtime': book.get('Runtime', ''),
                    'rating': book.get('Overall Rating', ''),
                    'summary': book.get('Summary', ''),
                    'cover_image': book.get('Cover Image', ''),
                    'narrator': book.get('Narrator', ''),
                    'publisher': book.get('Publisher', '')
                })
        
        return jsonify({
            'success': True,
            'author': author_name,
            'library_books': len(library_books),
            'audible_total': len(audible_results),
            'missing_books': missing_books,
            'missing_count': len(missing_books),
            'coverage_percentage': round((len(library_asins) / len(audible_results)) * 100, 1) if audible_results else 100
        })
    
    except Exception as e:
        logger.error(f"Error discovering books for {author_name}: {e}")
        return jsonify({'error': f'Discovery failed: {str(e)}'}), 500

# ============================================================================
# SEARCH AND DISCOVERY
# ============================================================================

@authors_bp.route('/api/search')
def api_search_authors():
    """Enhanced API endpoint for searching authors with fuzzy matching."""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'error': 'Search query required'}), 400
        
        include_stats = request.args.get('include_stats', 'false').lower() == 'true'
        limit = request.args.get('limit', 20, type=int)
        
        db_service = get_database_service()
        all_authors = db_service.get_all_authors()
        
        # Enhanced search with scoring
        matching_authors = []
        query_lower = query.lower()
        
        for author in all_authors:
            author_lower = author.lower()
            
            # Calculate relevance score
            score = 0
            if author_lower == query_lower:
                score = 100  # Exact match
            elif author_lower.startswith(query_lower):
                score = 90   # Starts with query
            elif query_lower in author_lower:
                score = 70   # Contains query
            elif any(word in author_lower for word in query_lower.split()):
                score = 50   # Contains any word
            else:
                continue  # No match
            
            books = db_service.get_books_by_author(author)
            if include_stats:
                author_info = format_author_for_template(author, books)
            else:
                author_info = {
                    'name': author,
                    'book_count': len(books)
                }
            
            author_info['relevance_score'] = score
            matching_authors.append(author_info)
        
        # Sort by relevance score, then by book count
        matching_authors.sort(key=lambda x: (x['relevance_score'], x.get('book_count', 0)), reverse=True)
        
        # Apply limit
        matching_authors = matching_authors[:limit]
        
        return jsonify({
            'success': True,
            'query': query,
            'authors': matching_authors,
            'count': len(matching_authors),
            'include_stats': include_stats
        })
    
    except Exception as e:
        logger.error(f"Error searching authors: {e}")
        return jsonify({'error': 'Failed to search authors'}), 500

@authors_bp.route('/api/refresh/<author_name>', methods=['POST'])
def api_refresh_author(author_name):
    """Refresh author data using ASIN-based Audnexus lookup."""
    try:
        logger.info(f"Refreshing author data for: {author_name}")
        
        # First, try to get author ASIN from existing books
        db_service = get_database_service()
        books = db_service.get_books_by_author(author_name)
        
        author_asin = None
        # Look for author ASIN in book contributors data
        for book in books:
            # Check if book has contributors data with author ASIN
            contributors = book.get('Contributors', [])
            if isinstance(contributors, list):
                for contributor in contributors:
                    if (isinstance(contributor, dict) and 
                        contributor.get('Role') == 'Author' and 
                        contributor.get('ASIN')):
                        author_asin = contributor.get('ASIN')
                        break
            if author_asin:
                break
        
        if not author_asin:
            # Fallback: search for author using hybrid service to get ASIN
            hybrid_service = get_hybrid_audiobook_service()
            author_info = hybrid_service.search_author_page(author_name)
            if author_info and author_info.get('audible_author_id'):
                author_asin = author_info.get('audible_author_id')
        
        if not author_asin:
            return jsonify({
                'success': False,
                'error': f'Could not find author ASIN for {author_name}. Try adding books first to populate contributor data.',
                'suggestion': 'Add books by this author to get their ASIN from contributor data'
            }), 404
        
        # Update author using ASIN
        result = update_author_from_asin(author_name, author_asin)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result['error'],
                'asin': author_asin
            }), 500
        
        return jsonify({
            'success': True,
            'author': author_name,
            'author_asin': author_asin,
            'library_books_count': len(books),
            'has_image': result['has_image'],
            'has_bio': result['has_bio'],
            'data_source': 'audnexus_asin',
            'message': f'Successfully updated author data using ASIN: {author_asin}'
        })
    
    except Exception as e:
        logger.error(f"Error refreshing author {author_name}: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to refresh author data: {str(e)}'
        }), 500

@authors_bp.route('/api/download-missing/<author_name>', methods=['POST'])
def api_download_missing_books(author_name):
    """Download missing books for an author."""
    try:
        
        logger.info(f"Starting download of missing books for: {author_name}")
        
        hybrid_service = get_hybrid_audiobook_service()
        db_service = get_database_service()
        
        download_service = get_download_management_service()
        if not download_service:
            return jsonify({
                'success': False,
                'error': 'Download service not available'
            }), 500
        
        # Get books from hybrid service (Audnexus + Audible) and compare with library
        audible_books = hybrid_service.get_author_books_from_audible(author_name)
        library_books = db_service.get_books_by_author(author_name)
        
        # Find missing books
        library_asins = {book.get('ASIN') for book in library_books if book.get('ASIN')}
        missing_books = [book for book in audible_books 
                        if book.get('ASIN') and book.get('ASIN') not in library_asins]
        
        if not missing_books:
            return jsonify({
                'success': True,
                'message': f'No missing books found for {author_name}',
                'count': 0
            })
        
        # Queue downloads for missing books
        download_count = 0
        for book in missing_books:
            try:
                # Add book to library as wishlist item first
                db_service.add_book({
                    'Title': book.get('Title', ''),
                    'Author': author_name,
                    'Series': book.get('Series', 'N/A'),
                    'Sequence': book.get('Sequence', 'N/A'),
                    'ASIN': book.get('ASIN', ''),
                    'Cover Image': book.get('Cover Image', ''),
                    'Runtime': book.get('Runtime', ''),
                    'Overall Rating': book.get('Overall Rating', ''),
                    'Summary': book.get('Summary', ''),
                    'Status': 'Wishlist'
                })
                
                # Queue for download
                download_service.queue_download({
                    'title': book.get('Title', ''),
                    'author': author_name,
                    'asin': book.get('ASIN', ''),
                    'type': 'book'
                })
                
                download_count += 1
                
            except Exception as e:
                logger.error(f"Error queuing download for {book.get('Title', 'Unknown')}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Queued {download_count} books for download',
            'count': download_count,
            'total_missing': len(missing_books)
        })
    
    except Exception as e:
        logger.error(f"Error downloading missing books for {author_name}: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to download missing books: {str(e)}'
        }), 500

@authors_bp.route('/api/author-metadata/<author_name>')
def api_get_author_metadata(author_name):
    """Get author metadata including Audible information."""
    try:
        from services.service_manager import get_database_service
        
        db_service = get_database_service()
        metadata = db_service.authors.get_author_metadata(author_name)
        
        if metadata:
            return jsonify({
                'success': True,
                'author': author_name,
                'metadata': metadata
            })
        else:
            return jsonify({
                'success': False,
                'error': f'No metadata found for author {author_name}'
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting author metadata for {author_name}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500