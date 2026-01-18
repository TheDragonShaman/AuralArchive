"""
Module Name: system_validation_api.py
Author: TheDragonShaman
Created: July 21, 2025
Last Modified: December 23, 2025
Description:
    System validation API for integration checks and status reporting. Provides
    endpoints to run validation suites, fetch system status snapshots, and
    inspect detailed service state.

Location:
    /api/system_validation_api.py

System Validation API
=====================

Endpoints:
- POST /api/system/validate           - Run comprehensive system validation
- GET  /api/system/status             - Get overall system status
- GET  /api/system/services/status    - Detailed service status
- POST /api/system/integration/test   - Run full integration test suite
"""
from flask import Blueprint, jsonify, request
import logging
import asyncio
from functools import wraps
from utils.logger import get_module_logger

# Create blueprint
system_validation_bp = Blueprint('system_validation', __name__)
logger = get_module_logger("API.System.Validation")

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

@system_validation_bp.route('/api/system/validate', methods=['POST'])
@handle_errors
def run_system_validation():
    """Run comprehensive system validation"""
    try:
        # Import the integration test
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests'))
        
        from integration_test_audiobook_system import AudiobookIntegrationTest
        
        # Run validation tests
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        test_suite = AudiobookIntegrationTest()
        
        # Run individual test components for detailed results
        validation_results = {}
        
        try:
            loop.run_until_complete(test_suite.setup_test_environment())
            
            # Test service initialization
            validation_results['service_initialization'] = loop.run_until_complete(
                test_suite.test_service_initialization()
            )
            
            # Test configuration management
            validation_results['configuration_management'] = loop.run_until_complete(
                test_suite.test_configuration_management()
            )
            
            # Test event communication
            validation_results['event_communication'] = loop.run_until_complete(
                test_suite.test_event_communication()
            )
            
            # Test health monitoring
            validation_results['health_monitoring'] = loop.run_until_complete(
                test_suite.test_health_monitoring()
            )
            
        finally:
            loop.run_until_complete(test_suite.teardown_test_environment())
        
        # Calculate overall success
        all_passed = all(validation_results.values())
        passed_count = sum(validation_results.values())
        total_count = len(validation_results)
        
        return jsonify({
            'success': True,
            'validation': {
                'overall_status': 'passed' if all_passed else 'failed',
                'passed_tests': passed_count,
                'total_tests': total_count,
                'results': validation_results
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'System validation failed: {str(e)}'}), 500

@system_validation_bp.route('/api/system/status', methods=['GET'])
@handle_errors
def get_system_status():
    """Get comprehensive system status"""
    try:
        from services.service_manager import service_manager
        
        # Get service status
        service_status = service_manager.get_service_status()
        
        # Get health status
        try:
            overall_health = health_monitor.get_overall_health_status() if health_monitor else None
            system_metrics = health_monitor.get_system_metrics() if health_monitor else None
        except:
            overall_health = None
            system_metrics = None
        
        # Get event bus status
        try:
            event_bus = service_manager.get_event_bus()
            event_stats = event_bus.get_statistics() if event_bus else None
        except:
            event_stats = None
        
        # Get configuration status
        try:
            config_service = service_manager.get_config_service()
            config_validation = config_service.validate_config() if config_service else None
            enabled_services = config_service.get_enabled_services() if config_service else None
        except:
            config_validation = None
            enabled_services = None
        
        return jsonify({
            'success': True,
            'system_status': {
                'services': service_status,
                'health': overall_health,
                'system_metrics': system_metrics,
                'event_system': event_stats,
                'configuration': {
                    'validation': config_validation,
                    'enabled_services': enabled_services
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get system status: {str(e)}'}), 500

@system_validation_bp.route('/api/system/services/status', methods=['GET'])
@handle_errors
def get_detailed_service_status():
    """Get detailed status of all audiobook services"""
    try:
        from services.service_manager import service_manager
        
        # Get all audiobook services
        services_to_check = {
            # Core services
            'database': service_manager.get_database_service(),
            'config': service_manager.get_config_service(),
            
            # Indexer services
            'jackett': service_manager.get_jackett_service(),
            
            # Client services
            # Download, client, coordination, and file processing services removed
            # 'client_manager': None,
            # 'qbittorrent': None,
            # 'download_coordinator': None,
            # 'download_selector': None,
            # 'download_queue_manager': None,
            # 'file_processor': None,
            # 'file_organizer': None,
            
            # Communication
            'event_bus': service_manager.get_event_bus(),
            'service_coordinator': service_manager.get_service_coordinator(),
            
            # Monitoring
        }
        
        # Check each service
        detailed_status = {}
        
        for service_name, service_instance in services_to_check.items():
            if service_instance is None:
                detailed_status[service_name] = {
                    'status': 'not_initialized',
                    'available': False,
                    'type': None
                }
            else:
                # Try to get service type and additional info
                service_type = type(service_instance).__name__
                
                # Check if service has health check method
                has_health_check = hasattr(service_instance, 'health_check') or hasattr(service_instance, 'is_healthy')
                
                # Check if service is running (for async services)
                is_running = None
                if hasattr(service_instance, '_monitoring'):
                    is_running = service_instance._monitoring
                elif hasattr(service_instance, '_processing'):
                    is_running = service_instance._processing
                elif hasattr(service_instance, '_running'):
                    is_running = service_instance._running
                
                detailed_status[service_name] = {
                    'status': 'initialized',
                    'available': True,
                    'type': service_type,
                    'has_health_check': has_health_check,
                    'is_running': is_running
                }
        
        # Calculate summary
        total_services = len(detailed_status)
        initialized_services = sum(1 for s in detailed_status.values() if s['available'])
        running_services = sum(1 for s in detailed_status.values() if s.get('is_running') is True)
        
        return jsonify({
            'success': True,
            'services': detailed_status,
            'summary': {
                'total_services': total_services,
                'initialized_services': initialized_services,
                'running_services': running_services,
                'initialization_rate': f"{initialized_services}/{total_services}",
                'running_rate': f"{running_services}/{total_services}"
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get detailed service status: {str(e)}'}), 500

@system_validation_bp.route('/api/system/integration/test', methods=['POST'])
@handle_errors
def run_integration_test():
    """Run full integration test suite"""
    try:
        # Import and run the integration test
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests'))
        
        from integration_test_audiobook_system import AudiobookIntegrationTest
        
        # Run full integration test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        test_suite = AudiobookIntegrationTest()
        success = loop.run_until_complete(test_suite.run_all_tests())
        
        return jsonify({
            'success': True,
            'integration_test': {
                'completed': True,
                'passed': success,
                'message': 'Integration test completed successfully' if success else 'Some integration tests failed'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'integration_test': {
                'completed': False,
                'passed': False,
                'error': str(e)
            }
        }), 500
