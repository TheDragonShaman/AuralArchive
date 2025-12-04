"""
Retry Handler
=============

Manages retry logic for failed downloads:
- Search: 3 attempts with different indexers
- Download: 2 attempts with different sources
- Conversion: 1 attempt (errors usually not transient)
- Import: 2 attempts (may be connectivity issue)
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from utils.logger import get_module_logger


class RetryHandler:
    """
    Handles retry logic for failed operations.
    
    Retry limits by stage:
    - SEARCH_FAILED: 3 attempts
    - DOWNLOAD_FAILED: 2 attempts
    - CONVERSION_FAILED: 1 attempt
    - IMPORT_FAILED: 2 attempts
    """
    
    # Max retries per failure type
    MAX_RETRIES = {
        'SEARCH_FAILED': 3,
        'DOWNLOAD_FAILED': 2,
        'AUDIBLE_DOWNLOAD_FAILED': 2,
        'CONVERSION_FAILED': 1,
        'IMPORT_FAILED': 2
    }
    
    def __init__(self):
        """Initialize retry handler."""
        self.logger = get_module_logger("RetryHandler")
        self._queue_manager = None
        self._state_machine = None
        self.retry_backoff_seconds = 10
    
    def _get_queue_manager(self):
        """Lazy load QueueManager."""
        if self._queue_manager is None:
            from .queue_manager import QueueManager
            self._queue_manager = QueueManager()
        return self._queue_manager
    
    def _get_state_machine(self):
        """Lazy load StateMachine."""
        if self._state_machine is None:
            from .state_machine import StateMachine
            self._state_machine = StateMachine()
        return self._state_machine

    def set_retry_backoff(self, seconds: int):
        """Configure retry backoff delay in seconds."""
        minimum = max(10, int(seconds) if seconds else 10)
        self.retry_backoff_seconds = minimum
        self.logger.debug(
            "Retry backoff configured to %s seconds",
            self.retry_backoff_seconds
        )
    
    def should_retry(self, download_id: int, failure_status: str) -> bool:
        """
        Check if download should be retried.
        
        Args:
            download_id: Download queue ID
            failure_status: Failure state (SEARCH_FAILED, etc.)
        
        Returns:
            True if should retry, False otherwise
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            self.logger.warning(
                "Retry evaluation aborted - download %s not found in queue",
                download_id
            )
            return False
        
        retry_count = download.get('retry_count', 0)
        max_retries = self.MAX_RETRIES.get(failure_status, 0)
        
        can_retry = retry_count < max_retries
        
        if can_retry:
            self.logger.debug(
                "Download %s can retry (%s/%s)",
                download_id,
                retry_count + 1,
                max_retries
            )
        else:
            self.logger.warning(
                "Download %s exceeded max retries (%s/%s)",
                download_id,
                retry_count,
                max_retries
            )
        
        return can_retry
    
    def handle_failure(self, download_id: int, failure_status: str, 
                       error_message: str) -> bool:
        """
        Handle download failure - retry or mark as failed.
        
        Args:
            download_id: Download queue ID
            failure_status: Failure state
            error_message: Error description
        
        Returns:
            True if retrying, False if permanently failed
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            self.logger.error(
                "Retry handling aborted - download %s not found in queue",
                download_id
            )
            return False
        
        # Check if we should retry
        if self.should_retry(download_id, failure_status):
            # Increment retry count
            retry_count = download.get('retry_count', 0) + 1
            
            # Determine retry target state
            retry_state = self._get_retry_state(failure_status)
            
            # Update download
            updates: Dict[str, Any] = {
                'status': retry_state,
                'retry_count': retry_count,
                'error_message': None,
                'last_error': error_message
            }

            if failure_status == 'DOWNLOAD_FAILED':
                retry_at = datetime.utcnow() + timedelta(seconds=self.retry_backoff_seconds)
                updates['next_retry_at'] = retry_at.isoformat()
            else:
                updates['next_retry_at'] = None

            queue_manager.update_download(download_id, updates)
            
            self.logger.debug(
                "Retrying download %s: %s -> %s",
                download_id,
                failure_status,
                retry_state
            )
            return True
        else:
            # Max retries exceeded - mark as permanently failed
            queue_manager.update_download(download_id, {
                'status': failure_status,
                'error_message': error_message,
                'next_retry_at': None,
                'last_error': error_message
            })
            
            self.logger.error(
                "Download %s permanently failed: %s",
                download_id,
                error_message
            )
            return False
    
    def _get_retry_state(self, failure_status: str) -> str:
        """
        Get target state for retry based on failure type.
        
        Args:
            failure_status: Current failure state
        
        Returns:
            Target state for retry
        """
        retry_map = {
            'SEARCH_FAILED': 'SEARCHING',
            'DOWNLOAD_FAILED': 'FOUND',  # Try different source
            'AUDIBLE_DOWNLOAD_FAILED': 'QUEUED',
            'CONVERSION_FAILED': 'CONVERTING',
            'IMPORT_FAILED': 'IMPORTING'
        }
        
        return retry_map.get(failure_status, 'QUEUED')
