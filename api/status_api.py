"""
Module Name: status_api.py
Author: TheDragonShaman
Created: June 27, 2025
Last Modified: December 23, 2025
Description:
    Status Feed API that surfaces user-friendly operations/events feed for the
    UI. Provides a lightweight feed endpoint backed by the status service.

Location:
    /api/status_api.py

Status Feed API
===============

Endpoints:
- GET /api/status/feed  - Latest status events for UI consumption
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from services.service_manager import get_status_service

status_api_bp = Blueprint('status_api', __name__, url_prefix='/api/status')


@status_api_bp.route('/feed', methods=['GET'])
def get_status_feed():
    """Return the latest curated status events for the UI."""
    try:
        service = get_status_service()
        if not service:
            return jsonify({'success': False, 'events': [], 'error': 'Status service unavailable'}), 503

        try:
            limit = int(request.args.get('limit', 20))
        except ValueError:
            limit = 20
        limit = max(1, min(limit, 100))

        events = service.get_events(limit=limit)
        return jsonify({
            'success': True,
            'events': events,
            'generated_at': datetime.utcnow().isoformat()
        })
    except Exception as exc:
        return jsonify({'success': False, 'events': [], 'error': str(exc)}), 500
