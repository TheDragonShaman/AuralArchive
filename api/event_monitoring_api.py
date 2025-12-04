"""
Event Monitoring API - AuralArchive

Captures legacy endpoints that once surfaced event-bus metrics so the UI can
gracefully report that the system has been retired.

Author: AuralArchive Development Team
Updated: December 4, 2025
"""

from functools import wraps

from flask import Blueprint, jsonify, request

from utils.logger import get_module_logger

# Create blueprint
event_monitoring_bp = Blueprint('event_monitoring', __name__)
logger = get_module_logger("API.EventMonitoring")

def handle_errors(f):
    """Decorator to handle API errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
                logger.error("Event monitoring API error in %s: %s", f.__name__, e)
            return jsonify({'error': str(e), 'success': False}), 500
    return decorated_function

@event_monitoring_bp.route('/api/events/status', methods=['GET'])
@handle_errors
def get_event_system_status():
    """Get event system status and statistics"""
    try:
        # Event bus system removed
        return jsonify({
            'success': True,
            'event_bus': {
                'active': False,
                'statistics': {
                    'total_events': 0,
                    'event_counts': {},
                    'active_subscribers': 0,
                    'subscribed_services': 0,
                    'processing': False
                }
            },
            'coordinator': {
                'active_workflows': 0,
                'workflows': {}
            },
            'message': 'Event bus system removed'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get event system status: {str(e)}'}), 500

@event_monitoring_bp.route('/api/events/history', methods=['GET'])
@handle_errors
def get_event_history():
    """Get recent event history"""
    try:
        # Event bus removed - return empty history
        return jsonify({
            'success': True,
            'events': [],
            'count': 0,
            'filters': {
                'event_type': request.args.get('event_type'),
                'service': request.args.get('service'),
                'limit': int(request.args.get('limit', 50)),
                'hours': int(request.args.get('hours', 24))
            },
            'message': 'Event bus system removed'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get event history: {str(e)}'}), 500

@event_monitoring_bp.route('/api/events/subscriptions', methods=['GET'])
@handle_errors
def get_service_subscriptions():
    """Get service event subscriptions"""
    try:
        # Event bus system removed
        return jsonify({
            'success': True,
            'subscriptions': {},
            'total_services': 0,
            'message': 'Event bus system removed'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get subscriptions: {str(e)}'}), 500

@event_monitoring_bp.route('/api/events/workflows/<workflow_id>', methods=['GET'])
@handle_errors
def get_workflow_status(workflow_id):
    """Get status of specific workflow"""
    try:
        # Service coordinator removed
        return jsonify({
            'success': False,
            'workflow_id': workflow_id,
            'message': 'Service coordinator system removed'
        }), 404
        
    except Exception as e:
        return jsonify({'error': f'Failed to get workflow status: {str(e)}'}), 500

@event_monitoring_bp.route('/api/events/workflows', methods=['GET'])
@handle_errors
def get_all_workflows():
    """Get all active workflows"""
    try:
        # Service coordinator removed
        return jsonify({
            'success': True,
            'workflows': {},
            'count': 0,
            'message': 'Service coordinator system removed'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get workflows: {str(e)}'}), 500

@event_monitoring_bp.route('/api/events/publish', methods=['POST'])
@handle_errors
def publish_test_event():
    """Publish a test event (for debugging)"""
    try:
        # Event bus system removed
        return jsonify({
            'success': False,
            'message': 'Event bus system removed - cannot publish events',
            'event_id': None
        })

    except Exception as e:
        logger.error("Failed to publish test event: %s", e)
        return jsonify({'error': f'Failed to publish event: {str(e)}'}), 500
