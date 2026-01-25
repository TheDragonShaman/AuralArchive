"""
Module Name: sync_task_manager.py
Author: TheDragonShaman
Created: January 24, 2026
Description:
    Manages background sync tasks with progress tracking and SocketIO updates.
Location:
    /services/audiobookshelf/sync_task_manager.py
"""

import threading
import time
from typing import Dict, Optional
from datetime import datetime
from utils.logger import get_module_logger

class SyncTaskManager:
    """Manages background AudioBookShelf sync tasks with progress tracking."""
    
    def __init__(self, socketio=None):
        self.logger = get_module_logger("Service.AudioBookShelf.TaskManager")
        self.socketio = socketio
        self.current_task: Optional[Dict] = None
        self.task_lock = threading.Lock()
        
    def is_sync_running(self) -> bool:
        """Check if a sync is currently running."""
        with self.task_lock:
            return self.current_task is not None and self.current_task.get('status') == 'running'
    
    def get_sync_status(self) -> Optional[Dict]:
        """Get current sync task status."""
        with self.task_lock:
            if self.current_task:
                return self.current_task.copy()
            return None
    
    def start_sync(self, abs_service, db_service, socketio=None) -> Dict:
        """Start a background sync task."""
        # Update socketio instance if provided
        if socketio:
            self.socketio = socketio
            
        if self.is_sync_running():
            return {
                'success': False,
                'message': 'A sync is already in progress'
            }
        
        # Initialize task state
        with self.task_lock:
            self.current_task = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
                'progress': {
                    'current_page': 0,
                    'total_pages': 0,
                    'items_processed': 0,
                    'items_added': 0,
                    'items_skipped': 0,
                    'items_updated': 0
                },
                'message': 'Starting sync...'
            }
        
        # Start sync in background thread
        sync_thread = threading.Thread(
            target=self._run_sync_background,
            args=(abs_service, db_service),
            daemon=True
        )
        sync_thread.start()
        
        return {
            'success': True,
            'message': 'Sync started in background'
        }
    
    def _run_sync_background(self, abs_service, db_service):
        """Run sync in background with progress tracking."""
        try:
            self.logger.info("Background sync started")
            self._emit_progress('started', 'Initializing sync...')
            
            # Run the sync with progress callbacks
            success, synced_count, message = abs_service.sync_from_audiobookshelf_with_progress(
                db_service,
                progress_callback=self._update_progress
            )
            
            # Update final status
            with self.task_lock:
                if self.current_task:
                    self.current_task['status'] = 'completed' if success else 'failed'
                    self.current_task['completed_at'] = datetime.now().isoformat()
                    self.current_task['message'] = message
                    self.current_task['synced_count'] = synced_count
            
            self._emit_progress(
                'completed' if success else 'failed',
                message,
                final_count=synced_count
            )
            
            self.logger.info(
                f"Background sync {'completed' if success else 'failed'}",
                extra={'synced_count': synced_count}
            )
            
        except Exception as exc:
            self.logger.error(f"Background sync error: {exc}")
            with self.task_lock:
                if self.current_task:
                    self.current_task['status'] = 'failed'
                    self.current_task['completed_at'] = datetime.now().isoformat()
                    self.current_task['message'] = f'Error: {str(exc)}'
            
            self._emit_progress('failed', f'Error: {str(exc)}')
    
    def _update_progress(self, progress_data: Dict):
        """Update progress and emit to clients."""
        with self.task_lock:
            if self.current_task:
                self.current_task['progress'].update(progress_data)
                self.current_task['message'] = progress_data.get('message', 'Processing...')
        
        # Emit progress update
        self._emit_progress('progress', progress_data.get('message', 'Processing...'))
    
    def _emit_progress(self, status: str, message: str, final_count: int = None):
        """Emit progress update via SocketIO."""
        if not self.socketio:
            return
        
        try:
            progress_info = self.get_sync_status()
            if progress_info:
                emit_data = {
                    'status': status,
                    'message': message,
                    'progress': progress_info.get('progress', {}),
                    'started_at': progress_info.get('started_at'),
                }
                
                if final_count is not None:
                    emit_data['synced_count'] = final_count
                
                self.socketio.emit('abs_sync_progress', emit_data)
        except Exception as exc:
            self.logger.error(f"Error emitting progress: {exc}")
    
    def cancel_sync(self) -> Dict:
        """Cancel the current sync (if possible)."""
        with self.task_lock:
            if not self.current_task or self.current_task.get('status') != 'running':
                return {'success': False, 'message': 'No sync is running'}
            
            # Note: Actual cancellation would require cooperative cancellation in the sync code
            # For now, just mark as cancelled
            self.current_task['status'] = 'cancelled'
            self.current_task['completed_at'] = datetime.now().isoformat()
            self.current_task['message'] = 'Sync cancelled by user'
        
        self._emit_progress('cancelled', 'Sync cancelled by user')
        return {'success': True, 'message': 'Sync cancelled'}


# Global instance
_sync_task_manager: Optional[SyncTaskManager] = None

def get_sync_task_manager(socketio=None) -> SyncTaskManager:
    """Get or create the sync task manager singleton."""
    global _sync_task_manager
    if _sync_task_manager is None:
        _sync_task_manager = SyncTaskManager(socketio)
    elif socketio and _sync_task_manager.socketio is None:
        _sync_task_manager.socketio = socketio
    return _sync_task_manager
