"""
Module Name: main.py
Author: TheDragonShaman
Created: July 23, 2025
Last Modified: December 23, 2025
Description:
    Dashboard routes for landing page, library stats API, and download snapshots.
Location:
    /routes/main.py

"""

import os
from typing import Any, Dict, List

from flask import Blueprint, jsonify, render_template, send_file
from flask_login import login_required

from services.service_manager import get_config_service, get_database_service
from utils.logger import get_module_logger

main_bp = Blueprint('main', __name__)
logger = get_module_logger("Routes.Main")

def _get_download_snapshot(limit: int = 3) -> Dict[str, Any]:
    """Fetch a small snapshot of active downloads."""
    snapshot: Dict[str, Any] = {'connected': False, 'downloads': [], 'error': None}
    try:
        from services.download_clients.qbittorrent_client import QBittorrentClient

        config_service = get_config_service()
        qb_section = config_service.get_section('qbittorrent')

        if not qb_section or not config_service.get_config_bool('qbittorrent', 'enabled', False):
            snapshot['error'] = 'Download client not configured'
            return snapshot

        qb_config = {
            'host': qb_section.get('qb_host', 'localhost'),
            'port': int(qb_section.get('qb_port', 8080) or 8080),
            'username': qb_section.get('qb_username', 'admin'),
            'password': (qb_section.get('qb_password', 'adminadmin') or 'adminadmin').strip('"'),
            'use_ssl': False
        }

        qb_client = QBittorrentClient(qb_config)
        if not qb_client.connect():
            snapshot['error'] = qb_client.last_error or 'Unable to connect to download client'
            return snapshot

        snapshot['connected'] = True
        torrents_result = qb_client.get_torrents()
        if torrents_result.get('success'):
            torrents = torrents_result.get('torrents', [])
            filtered = [
                torrent for torrent in torrents
                if (torrent.get('category') or '').lower() == 'auralarchive'
            ]
            filtered.sort(key=lambda item: item.get('added_on', 0) or 0, reverse=True)
            snapshot['downloads'] = filtered[:limit]
        else:
            snapshot['error'] = torrents_result.get('error', 'Unable to fetch downloads')

    except Exception as exc:
        snapshot['error'] = str(exc)
        logger.debug("Download snapshot unavailable: %s", exc)

    return snapshot


@main_bp.route('/')
@login_required
def index():
    """Dashboard landing page."""
    return dashboard()

@main_bp.route('/api/library/stats')
@login_required
def api_library_stats():
    """API endpoint for library statistics used by MediaVault JS."""
    try:
        db_service = get_database_service()
        books = db_service.get_all_books()
        
        # Calculate stats
        authors = set()
        total_hours = 0
        
        for book in books:
            if book.get('Author'):
                authors.add(book['Author'])
            
            # Calculate total hours
            runtime = book.get('Runtime', '0 hrs 0 mins')
            try:
                if 'hrs' in runtime:
                    hours = int(runtime.split(' hrs')[0])
                    minutes = int(runtime.split(' hrs ')[1].split(' mins')[0]) if ' mins' in runtime else 0
                    total_hours += hours + (minutes / 60)
            except:
                pass
        
        return jsonify({
            'totalBooks': len(books),
            'totalAuthors': len(authors),
            'totalHours': int(total_hours)
        })
    
    except Exception as e:
        logger.error(f"Error getting library stats: {e}")
        return jsonify({
            'totalBooks': 0,
            'totalAuthors': 0,
            'totalHours': 0
        })

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard with recent activity."""
    library_stats: Dict[str, Any] = {}
    activity_stats: Dict[str, Any] = {}
    recent_books: List[Dict[str, Any]] = []

    try:
        db_service = get_database_service()
        library_stats = db_service.get_library_stats() or {}
        activity_stats = db_service.get_recent_activity_stats(7) or {}
        recent_books = db_service.get_recent_books(limit=6)
    except Exception as exc:
        logger.error(f"Error loading dashboard data: {exc}")

    download_snapshot = _get_download_snapshot(limit=4)

    return render_template(
        'dashboard.html',
        title='Dashboard - AuralArchive',
        library_stats=library_stats,
        activity_stats=activity_stats,
        recent_books=recent_books,
        download_snapshot=download_snapshot
    )

@main_bp.route('/debug_refresh_test.html')
@login_required
def debug_refresh_test():
    """Serve the debug refresh test page."""
    debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug_refresh_test.html')
    return send_file(debug_file)
