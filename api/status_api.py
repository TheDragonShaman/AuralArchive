"""Status Feed API - surfaces user-friendly operations feed."""
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
