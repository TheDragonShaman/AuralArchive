"""
Clear Cache Route - AuralArchive

Removes cached data, __pycache__ directories, and temporary files so admins can
reset the runtime environment from the settings UI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import glob
import os
import shutil
import sys
from datetime import datetime

from flask import jsonify

from utils.logger import get_module_logger

logger = get_module_logger("Route.Settings.ClearCache")

def handle_clear_cache():
    """Clear application cache."""
    try:
        cache_cleared = False
        cleared_items = []
        
        # Clear any cache directories
        cache_dirs = ['cache', 'tmp', '__pycache__']
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                try:
                    shutil.rmtree(cache_dir)
                    cache_cleared = True
                    cleared_items.append(f"Directory: {cache_dir}")
                except Exception as e:
                    logger.warning(f"Could not clear cache directory {cache_dir}: {e}")
        
        # Clear Python bytecode cache recursively
        try:
            for root, dirs, files in os.walk('.'):
                for dir_name in dirs:
                    if dir_name == '__pycache__':
                        pycache_path = os.path.join(root, dir_name)
                        try:
                            shutil.rmtree(pycache_path)
                            cache_cleared = True
                            cleared_items.append(f"Python cache: {pycache_path}")
                        except Exception as e:
                            logger.warning(f"Could not clear Python cache {pycache_path}: {e}")
        except Exception as e:
            logger.warning(f"Error clearing Python bytecode cache: {e}")
        
        # Clear .pyc files
        try:
            for root, dirs, files in os.walk('.'):
                for file in files:
                    if file.endswith('.pyc'):
                        pyc_path = os.path.join(root, file)
                        try:
                            os.remove(pyc_path)
                            cache_cleared = True
                            cleared_items.append(f"Bytecode file: {pyc_path}")
                        except Exception as e:
                            logger.warning(f"Could not remove .pyc file {pyc_path}: {e}")
        except Exception as e:
            logger.warning(f"Error clearing .pyc files: {e}")
        
        # Set flag to not write bytecode in future
        try:
            sys.dont_write_bytecode = True
            cleared_items.append("Disabled future bytecode generation")
        except Exception as e:
            logger.warning(f"Could not disable bytecode generation: {e}")
        
        # Clear any temporary files
        temp_patterns = ['*.tmp', '*.temp', '*.log.old', '*.bak']
        for pattern in temp_patterns:
            try:
                for temp_file in glob.glob(pattern):
                    try:
                        os.remove(temp_file)
                        cache_cleared = True
                        cleared_items.append(f"Temp file: {temp_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove temp file {temp_file}: {e}")
            except Exception as e:
                logger.warning(f"Error clearing temp files with pattern {pattern}: {e}")
        
        message = 'Cache cleared successfully' if cache_cleared else 'No cache to clear'
        
        return jsonify({
            'success': True,
            'message': message,
            'cleared': cache_cleared,
            'cleared_items': cleared_items,
            'items_count': len(cleared_items),
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({
            'success': False, 
            'error': f'Failed to clear cache: {str(e)}'
        }), 500