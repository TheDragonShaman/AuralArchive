"""
Repair Database Route - AuralArchive

Runs integrity checks, rebuilds indexes, and vacuums the SQLite database,
providing progress back to the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
import shutil
from datetime import datetime

from flask import jsonify

from services.service_manager import get_database_service
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.RepairDatabase")

def handle_repair_database():
    """Repair database with comprehensive checking."""
    try:
        db_service = get_database_service()
        
        # Check if database file exists
        if not hasattr(db_service, 'db_file') or not os.path.exists(db_service.db_file):
            return jsonify({
                'success': False,
                'error': 'Database file not found'
            }), 404
        
        # Create backup before repair
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'auralarchive_pre_repair_backup_{timestamp}.db'
        backup_path = os.path.join('backups', backup_filename)
        
        # Create backups directory if it doesn't exist
        os.makedirs('backups', exist_ok=True)
        
        # Create backup
        shutil.copy2(db_service.db_file, backup_path)
        
        conn, cursor = db_service.connect_db()
        repair_steps = []
        repair_issues = []
        
        # Step 1: Check database integrity
        try:
            cursor.execute("PRAGMA integrity_check")
            integrity_results = cursor.fetchall()
            
            if len(integrity_results) == 1 and integrity_results[0][0] == 'ok':
                repair_steps.append("Integrity check: Database is healthy")
            else:
                for result in integrity_results:
                    repair_issues.append(f"Integrity issue: {result[0]}")
                repair_steps.append(f"Integrity check: Found {len(integrity_results)} issues")
        except Exception as e:
            repair_issues.append(f"Integrity check failed: {str(e)}")
            repair_steps.append("Integrity check: Failed")
        
        # Step 2: Check foreign key constraints
        try:
            cursor.execute("PRAGMA foreign_key_check")
            fk_results = cursor.fetchall()
            
            if not fk_results:
                repair_steps.append("Foreign key check: All constraints valid")
            else:
                for result in fk_results:
                    repair_issues.append(f"Foreign key violation: {result}")
                repair_steps.append(f"Foreign key check: Found {len(fk_results)} violations")
        except Exception as e:
            repair_issues.append(f"Foreign key check failed: {str(e)}")
            repair_steps.append("Foreign key check: Failed")
        
        # Step 3: Check and fix schema
        try:
            cursor.execute("PRAGMA schema_version")
            schema_version = cursor.fetchone()[0]
            repair_steps.append(f"Schema version: {schema_version}")
        except Exception as e:
            repair_issues.append(f"Schema check failed: {str(e)}")
            repair_steps.append("Schema check: Failed")
        
        # Step 4: Rebuild indexes if issues found
        if repair_issues:
            try:
                cursor.execute("REINDEX")
                repair_steps.append("Indexes rebuilt")
            except Exception as e:
                repair_issues.append(f"Index rebuild failed: {str(e)}")
                repair_steps.append("Index rebuild: Failed")
        
        # Step 5: Vacuum database
        try:
            cursor.execute("VACUUM")
            repair_steps.append("Database vacuumed")
        except Exception as e:
            repair_issues.append(f"Vacuum failed: {str(e)}")
            repair_steps.append("Vacuum: Failed")
        
        # Step 6: Analyze statistics
        try:
            cursor.execute("ANALYZE")
            repair_steps.append("Statistics analyzed")
        except Exception as e:
            repair_issues.append(f"Analyze failed: {str(e)}")
            repair_steps.append("Analyze: Failed")
        
        # Step 7: Final integrity check
        try:
            cursor.execute("PRAGMA integrity_check")
            final_integrity = cursor.fetchall()
            
            if len(final_integrity) == 1 and final_integrity[0][0] == 'ok':
                repair_steps.append("Final integrity check: Database is healthy")
                repair_successful = True
            else:
                repair_steps.append(f"Final integrity check: Still has {len(final_integrity)} issues")
                repair_successful = False
        except Exception as e:
            repair_issues.append(f"Final integrity check failed: {str(e)}")
            repair_steps.append("Final integrity check: Failed")
            repair_successful = False
        
        conn.close()
        
        # Determine overall success
        overall_success = len(repair_issues) == 0 or repair_successful
        
        result = {
            'success': overall_success,
            'message': 'Database repair completed' + (' successfully' if overall_success else ' with issues'),
            'backup_created': backup_filename,
            'repair_steps': repair_steps,
            'repair_issues': repair_issues,
            'issues_found': len(repair_issues),
            'steps_completed': len(repair_steps),
            'repair_successful': repair_successful,
            'timestamp': datetime.now().isoformat()
        }
        
        if overall_success:
            logger.info("Database repair completed successfully")
        else:
            logger.warning(f"Database repair completed with {len(repair_issues)} issues")
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error repairing database: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to repair database: {str(e)}'
        }), 500