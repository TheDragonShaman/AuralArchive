"""
Optimize Database Route - AuralArchive

Runs VACUUM/ANALYZE/REINDEX cycles and reports metadata back to the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
from datetime import datetime

from flask import jsonify

from services.service_manager import get_database_service
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.OptimizeDatabase")

def get_database_size():
    """Get database file size in human readable format."""
    try:
        db_service = get_database_service()
        if hasattr(db_service, 'db_file') and os.path.exists(db_service.db_file):
            size_bytes = os.path.getsize(db_service.db_file)
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{round(size_bytes / 1024, 2)} KB"
            else:
                return f"{round(size_bytes / (1024 * 1024), 2)} MB"
        else:
            return "Unknown"
    except Exception as e:
        logger.error(f"Error getting database size: {e}")
        return "Unknown"

def handle_optimize_database():
    """Optimize database with comprehensive operations."""
    try:
        db_service = get_database_service()
        conn, cursor = db_service.connect_db()
        
        # Get database size before optimization
        old_size = get_database_size()
        
        # Run comprehensive optimization
        optimization_steps = []
        
        # VACUUM to reclaim space
        cursor.execute("VACUUM")
        optimization_steps.append("VACUUM completed")
        
        # ANALYZE for query optimization
        cursor.execute("ANALYZE")
        optimization_steps.append("ANALYZE completed")
        
        # REINDEX for index optimization
        cursor.execute("REINDEX")
        optimization_steps.append("REINDEX completed")
        
        # Additional optimization: Update statistics
        try:
            cursor.execute("PRAGMA optimize")
            optimization_steps.append("PRAGMA optimize completed")
        except Exception as e:
            logger.warning(f"PRAGMA optimize failed: {e}")
        
        # Check database integrity
        try:
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()
            if integrity_result and integrity_result[0] == 'ok':
                optimization_steps.append("Integrity check passed")
            else:
                optimization_steps.append(f"Integrity check: {integrity_result}")
        except Exception as e:
            logger.warning(f"Integrity check failed: {e}")
        
        conn.close()
        
        # Get new size
        new_size = get_database_size()
        
        logger.info("Database optimization completed successfully")
        return jsonify({
            'success': True, 
            'message': 'Database optimized successfully',
            'old_size': old_size,
            'new_size': new_size,
            'steps_completed': optimization_steps,
            'steps_count': len(optimization_steps),
            'optimization_time': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to optimize database: {str(e)}'
        }), 500