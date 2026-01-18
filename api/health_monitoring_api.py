"""
Module Name: health_monitoring_api.py
Author: TheDragonShaman
Created: July 2, 2025
Last Modified: December 23, 2025
Description:
    REST endpoints for service health monitoring and system metrics. Interfaces
    with the health monitor to fetch status, histories, alerts, and to start or
    stop monitoring routines.

Location:
    /api/health_monitoring_api.py

Health Monitoring API
=====================

Endpoints:
- GET    /api/health/status                 - Overall health status
- GET    /api/health/services               - Health of all services
- GET    /api/health/services/<name>        - Health history for a service
- GET    /api/health/system                 - System performance metrics
- POST   /api/health/monitoring/start       - Start monitoring
- POST   /api/health/monitoring/stop        - Stop monitoring
- GET    /api/health/monitoring/status      - Monitoring status
- POST   /api/health/check/<name>           - Trigger immediate health check
- GET    /api/health/alerts                 - Recent health alerts
"""
from flask import Blueprint, jsonify, request
import logging
from functools import wraps
from datetime import datetime
from utils.logger import get_module_logger

# Create blueprint
health_monitoring_bp = Blueprint('health_monitoring', __name__)
logger = get_module_logger("API.Health.Monitoring")

def handle_errors(f):
    """Decorator to handle API errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {f.__name__}: {e}")
            return jsonify({'error': str(e), 'success': False}), 500
    return decorated_function

@health_monitoring_bp.route('/api/health/status', methods=['GET'])
@handle_errors
def get_health_status():
    """Get overall system health status"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        overall_status = health_monitor.get_overall_health_status()
        system_metrics = health_monitor.get_system_metrics()
        
        return jsonify({
            'success': True,
            'health': overall_status,
            'system': system_metrics,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get health status: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/services', methods=['GET'])
@handle_errors
def get_all_services_health():
    """Get health status for all services"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Get immediate health check results
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        health_results = loop.run_until_complete(health_monitor.check_all_services())
        
        # Convert to serializable format
        services_health = {}
        for service_name, result in health_results.items():
            services_health[service_name] = {
                'service_name': result.service_name,
                'service_type': result.service_type.value,
                'status': result.status.value,
                'message': result.message,
                'response_time_ms': result.response_time_ms,
                'timestamp': result.timestamp.isoformat(),
                'details': result.details,
                'error': result.error
            }
        
        return jsonify({
            'success': True,
            'services': services_health,
            'count': len(services_health)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get services health: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/services/<service_name>', methods=['GET'])
@handle_errors
def get_service_health(service_name):
    """Get health status and history for specific service"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Get query parameters
        limit = int(request.args.get('limit', 50))
        
        # Get service history
        history = health_monitor.get_service_health_history(service_name, limit)
        
        if not history:
            return jsonify({'error': f'No health data found for service: {service_name}'}), 404
        
        # Convert to serializable format
        history_data = []
        for result in history:
            history_data.append({
                'status': result.status.value,
                'message': result.message,
                'response_time_ms': result.response_time_ms,
                'timestamp': result.timestamp.isoformat(),
                'details': result.details,
                'error': result.error
            })
        
        # Get current status (latest result)
        current_status = history[-1]
        
        return jsonify({
            'success': True,
            'service_name': service_name,
            'current_status': {
                'status': current_status.status.value,
                'message': current_status.message,
                'timestamp': current_status.timestamp.isoformat()
            },
            'history': history_data,
            'history_count': len(history_data)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get service health: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/system', methods=['GET'])
@handle_errors
def get_system_metrics():
    """Get system performance metrics"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        metrics = health_monitor.get_system_metrics()
        
        return jsonify({
            'success': True,
            'metrics': metrics
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get system metrics: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/monitoring/start', methods=['POST'])
@handle_errors
def start_health_monitoring():
    """Start health monitoring if not already running"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Start monitoring (async, so we need event loop)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(health_monitor.start_monitoring())
        
        return jsonify({
            'success': True,
            'message': 'Health monitoring started'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start health monitoring: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/monitoring/stop', methods=['POST'])
@handle_errors
def stop_health_monitoring():
    """Stop health monitoring"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Stop monitoring (async, so we need event loop)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(health_monitor.stop_monitoring())
        
        return jsonify({
            'success': True,
            'message': 'Health monitoring stopped'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to stop health monitoring: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/monitoring/status', methods=['GET'])
@handle_errors
def get_monitoring_status():
    """Get health monitoring system status"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        return jsonify({
            'success': True,
            'monitoring': {
                'active': health_monitor._monitoring,
                'check_interval': health_monitor.check_interval,
                'alert_threshold': health_monitor.alert_threshold,
                'registered_services': len(health_monitor._checkers),
                'alert_callbacks': len(health_monitor._alert_callbacks),
                'recovery_callbacks': len(health_monitor._recovery_callbacks)
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get monitoring status: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/check/<service_name>', methods=['POST'])
@handle_errors
def trigger_service_health_check(service_name):
    """Trigger immediate health check for specific service"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Check if service is registered
        if service_name not in health_monitor._checkers:
            return jsonify({'error': f'Service {service_name} not registered for health monitoring'}), 404
        
        # Perform immediate health check
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        checker = health_monitor._checkers[service_name]
        result = loop.run_until_complete(checker.check_health())
        
        return jsonify({
            'success': True,
            'service_name': service_name,
            'health_check': {
                'status': result.status.value,
                'message': result.message,
                'response_time_ms': result.response_time_ms,
                'timestamp': result.timestamp.isoformat(),
                'details': result.details,
                'error': result.error
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to check service health: {str(e)}'}), 500

@health_monitoring_bp.route('/api/health/alerts', methods=['GET'])
@handle_errors
def get_health_alerts():
    """Get recent health alerts and issues"""
    try:
        
        if not health_monitor:
            return jsonify({'error': 'Health monitor not available'}), 500
        
        # Get services with recent issues
        alerts = []
        
        for service_name in health_monitor._checkers.keys():
            history = health_monitor.get_service_health_history(service_name, 10)
            
            if history:
                # Check for recent failures
                recent_failures = [h for h in history[-5:] if h.status.value in ['critical', 'warning']]
                
                if recent_failures:
                    alerts.append({
                        'service_name': service_name,
                        'issue_count': len(recent_failures),
                        'latest_status': history[-1].status.value,
                        'latest_message': history[-1].message,
                        'latest_timestamp': history[-1].timestamp.isoformat()
                    })
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'alert_count': len(alerts)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get health alerts: {str(e)}'}), 500
