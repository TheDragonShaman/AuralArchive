"""
Discover Routes - AuralArchive

Generates the discovery dashboard plus supporting APIs that summarize library
activity, highlight trends, and surface recommendation data.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import math
import re
from collections import Counter
from typing import List, Dict, Any

from flask import Blueprint, render_template, request, jsonify, url_for

from services.image_cache import get_cached_book_cover_url
from services.service_manager import get_database_service, get_config_service
from services.audible.audible_recommendations_service.audible_recommendations_service import (
    get_audible_recommendations_service,
)

from utils.logger import get_module_logger

discover_bp = Blueprint('discover', __name__)
logger = get_module_logger("Route.Discover")

_AUTHOR_SPLIT_PATTERN = re.compile(r"\s*(?:,|&|;|\band\b|\bwith\b)\s*", re.IGNORECASE)


def _split_author_field(author_value: str) -> List[str]:
    if not author_value:
        return []
    parts = _AUTHOR_SPLIT_PATTERN.split(str(author_value))
    return [" ".join(part.strip().split()) for part in parts if part and part.strip()]


def _format_recent_books(books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for book in books:
        cover_url = get_cached_book_cover_url(book) or book.get('Cover Image') or url_for(
            'static', filename='images/auralarchive_logo.png'
        )
        summary = book.get('Summary') or ''
        summary_snippet = summary[:180].rstrip() + ('...' if len(summary) > 180 else '') if summary else 'No summary available yet.'

        status_value = book.get('ownership_status') or book.get('Status') or 'unknown'

        formatted.append({
            'title': book.get('Title', 'Unknown Title'),
            'author': book.get('Author', 'Unknown Author'),
            'cover_url': cover_url,
            'status': status_value.lower(),
            'asin': book.get('ASIN', ''),
            'summary': summary_snippet,
            'language': book.get('Language', 'Unknown'),
            'runtime': book.get('Runtime', 'Unknown'),
            'series': book.get('Series', 'N/A'),
        })

    return formatted


@discover_bp.route('/discover')
def discover_page():
    """Render the discover dashboard with library insights and discovery tools."""
    try:
        db_service = get_database_service()

        # Library snapshot
        books = db_service.get_all_books()
        all_authors = db_service.get_all_authors()

        total_books = len(books)
        total_authors = len(all_authors)

        total_hours = 0.0
        downloading_count = 0
        series_counter: Counter = Counter()
        language_counter: Counter = Counter()
        author_counter: Counter = Counter()

        for book in books:
            runtime = (book.get('Runtime') or '').strip()
            if 'hrs' in runtime:
                try:
                    hours_part, _, minutes_part = runtime.partition(' hrs ')
                    hours = int(hours_part)
                    minutes = 0
                    if minutes_part and 'mins' in minutes_part:
                        minutes = int(minutes_part.split(' mins')[0])
                    total_hours += hours + minutes / 60
                except Exception:
                    pass

            status_value = (book.get('ownership_status') or book.get('Status') or '').lower()
            if status_value == 'downloading':
                downloading_count += 1

            series_value = book.get('Series') or ''
            if series_value and series_value not in {'N/A', 'Unknown', ''}:
                series_counter[series_value.strip()] += 1

            language_value = (book.get('Language') or '').strip()
            if language_value:
                language_counter[language_value] += 1

            for author_name in _split_author_field(book.get('Author')):
                if author_name != 'Unknown Author':
                    author_counter[author_name] += 1

        recent_books = sorted(books, key=lambda item: item.get('Created At', ''), reverse=True)[:6]
        formatted_recent = _format_recent_books(recent_books)

        top_authors = [
            {'name': name, 'count': count}
            for name, count in author_counter.most_common(6)
        ]

        trending_series = [
            {'name': name, 'count': count}
            for name, count in series_counter.most_common(6)
        ]

        top_languages = [
            {'name': name, 'count': count}
            for name, count in language_counter.most_common(6)
        ]

        avg_listen_length = 0
        if total_books:
            avg_listen_length = math.ceil((total_hours * 60) / total_books)

        recommendations_configured = False
        try:
            config_service = get_config_service()
            recommendations_service = get_audible_recommendations_service(config_service)
            recommendations_configured = recommendations_service.is_configured()
        except Exception as config_error:
            logger.debug(f"Recommendation service status unavailable: {config_error}")

        return render_template(
            'discover.html',
            title='Discover - AuralArchive',
            total_books=total_books,
            total_authors=total_authors,
            total_hours=int(total_hours),
            avg_listen_length=avg_listen_length,
            downloading_count=downloading_count,
            recent_books=formatted_recent,
            top_authors=top_authors,
            trending_series=trending_series,
            top_languages=top_languages,
            recommendations_configured=recommendations_configured,
        )

    except Exception as exc:
        logger.error(f"Error loading discover page: {exc}")
        return render_template(
            'discover.html',
            title='Discover - AuralArchive',
            total_books=0,
            total_authors=0,
            total_hours=0,
            avg_listen_length=0,
            downloading_count=0,
            recent_books=[],
            top_authors=[],
            trending_series=[],
            top_languages=[],
            recommendations_configured=False,
        )


@discover_bp.route('/discover/api/recommendations')
def get_recommendations():
    """API endpoint to fetch library-based recommendations."""
    try:
        num_results = request.args.get('num_results', 20, type=int)
        recommendations = _get_library_based_recommendations(num_results)

        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'count': len(recommendations),
            'configured': True,
        })

    except Exception as e:
        logger.error(f"Error getting library-based recommendations: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'recommendations': [],
        }), 500

def _get_library_based_recommendations(num_results: int = 20) -> List[Dict[str, Any]]:
    """Get recommendations based on library analysis only."""
    try:
        config_service = get_config_service()
        recommendations_service = get_audible_recommendations_service(config_service)
        
        # Only use library-based recommendations, skip broken Audible API
        if recommendations_service.is_configured():
            return recommendations_service._get_catalog_fallback(num_results)
        else:
            logger.info("Audible not configured, returning empty recommendations")
            return []
            
    except Exception as e:
        logger.error(f"Library-based recommendations failed: {e}")
        return []
