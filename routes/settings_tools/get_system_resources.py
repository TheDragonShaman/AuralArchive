"""
System Resources Route - AuralArchive

Reports CPU, memory, disk, and runtime metadata to the settings dashboard.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import platform
from datetime import datetime

from flask import jsonify

from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.SystemResources")

def handle_get_system_resources():
    """Get system resource usage information."""
    try:
        import psutil
        
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used = round(memory.used / (1024**3), 2)  # GB
        memory_total = round(memory.total / (1024**3), 2)  # GB
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_percent = round((disk.used / disk.total) * 100, 2)
        disk_used = round(disk.used / (1024**3), 2)  # GB
        disk_total = round(disk.total / (1024**3), 2)  # GB
        
        # Get system info
        system_info = {
            'system': platform.system(),
            'release': platform.release(),
            'processor': platform.processor(),
            'python_version': platform.python_version()
        }
        
        resources = {
            'cpu': {
                'usage_percent': cpu_percent,
                'cores': psutil.cpu_count(),
                'status': 'normal' if cpu_percent < 80 else 'high'
            },
            'memory': {
                'usage_percent': memory_percent,
                'used_gb': memory_used,
                'total_gb': memory_total,
                'status': 'normal' if memory_percent < 80 else 'high'
            },
            'disk': {
                'usage_percent': disk_percent,
                'used_gb': disk_used,
                'total_gb': disk_total,
                'status': 'normal' if disk_percent < 80 else 'high'
            },
            'system': system_info
        }
        
        return jsonify({
            'success': True,
            'resources': resources,
            'timestamp': datetime.now().isoformat()
        })
    
    except ImportError:
        # Fallback if psutil is not available
        return jsonify({
            'success': True,
            'resources': {
                'cpu': {'usage_percent': 0, 'cores': 1, 'status': 'unknown'},
                'memory': {'usage_percent': 0, 'used_gb': 0, 'total_gb': 0, 'status': 'unknown'},
                'disk': {'usage_percent': 0, 'used_gb': 0, 'total_gb': 0, 'status': 'unknown'},
                'system': {'system': 'Unknown', 'release': 'Unknown', 'processor': 'Unknown', 'python_version': platform.python_version()}
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting system resources: {e}")
        return jsonify({
            'success': False, 
            'error': f'Failed to get system resources: {str(e)}'
        }), 500