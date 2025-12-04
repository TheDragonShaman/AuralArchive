"""
Backup Database Route - AuralArchive

Creates database backups with metadata so admins can download the SQLite store
from the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import os
import shutil
from datetime import datetime

from flask import jsonify

from services.service_manager import get_database_service
from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.BackupDatabase")

def handle_backup_database():
    """Create database backup with enhanced metadata."""
    try:
        db_service = get_database_service()
        
        # Get database file path
        if not hasattr(db_service, 'db_file') or not os.path.exists(db_service.db_file):
            return jsonify({
                'success': False,
                'error': 'Database file not found'
            }), 404
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'auralarchive_backup_{timestamp}.db'
        backup_path = os.path.join('backups', backup_filename)
        
        # Create backups directory if it doesn't exist
        os.makedirs('backups', exist_ok=True)
        
        # Get original database size
        original_size = os.path.getsize(db_service.db_file)
        
        # Create backup
        shutil.copy2(db_service.db_file, backup_path)
        
        # Verify backup was created
        if not os.path.exists(backup_path):
            raise Exception("Backup file was not created")
        
        # Get backup size
        backup_size = os.path.getsize(backup_path)
        
        # Verify backup integrity (basic check)
        if backup_size != original_size:
            logger.warning(f"Backup size ({backup_size}) differs from original ({original_size})")
        
        # Get backup metadata
        backup_info = {
            'filename': backup_filename,
            'path': backup_path,
            'size': backup_size,
            'size_mb': round(backup_size / (1024 * 1024), 2),
            'created': datetime.now().isoformat(),
            'original_size': original_size,
            'integrity_check': backup_size == original_size
        }
        
        # Get current books count for metadata
        try:
            books = db_service.get_all_books()
            backup_info['books_count'] = len(books)
        except Exception as e:
            logger.warning(f"Could not get books count for backup metadata: {e}")
            backup_info['books_count'] = 'Unknown'
        
        logger.info(f"Database backup created: {backup_filename}")
        return jsonify({
            'success': True,
            'message': 'Database backup created successfully',
            'backup_info': backup_info,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to create database backup: {str(e)}'
        }), 500