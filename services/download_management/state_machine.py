"""
State Machine
=============

Manages download state transitions and validation.

Valid state flow:
QUEUED → SEARCHING → FOUND → DOWNLOADING → PAUSED → DOWNLOADING
                                        ↓
                                    COMPLETE → CONVERTING → CONVERTED → IMPORTING → IMPORTED
                                        ↓ (torrents/NZBs skip conversion)
                                    COMPLETE → IMPORTING → IMPORTED
                                                              ↓
                                                  (if seeding enabled) SEEDING → SEEDING_COMPLETE
                                        ↓
                                    (error states: SEARCH_FAILED, DOWNLOAD_FAILED, etc.)

Audible-specific branch:
QUEUED → AUDIBLE_DOWNLOADING → COMPLETE → CONVERTING → …
                      ↓
               AUDIBLE_DOWNLOAD_FAILED (retryable)
"""

import logging
from typing import Dict, Set
from datetime import datetime

logger = logging.getLogger("DownloadManagement.StateMachine")


class StateMachine:
    """
    Enforces valid state transitions for download lifecycle.
    
    Prevents invalid state changes and maintains data consistency.
    """
    
    # Valid state transitions
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
	'QUEUED': {'SEARCHING', 'FOUND', 'CANCELLED', 'AUDIBLE_DOWNLOADING'},
    'SEARCHING': {'FOUND', 'SEARCH_FAILED', 'CANCELLED'},
    'FOUND': {'DOWNLOADING', 'CANCELLED'},
	'DOWNLOADING': {'COMPLETE', 'DOWNLOAD_COMPLETE', 'DOWNLOAD_FAILED', 'PAUSED', 'CANCELLED'},
	'AUDIBLE_DOWNLOADING': {'COMPLETE', 'DOWNLOAD_COMPLETE', 'AUDIBLE_DOWNLOAD_FAILED', 'CANCELLED'},
    'PAUSED': {'DOWNLOADING', 'CANCELLED'},
    'DOWNLOAD_COMPLETE': {'CONVERTING', 'IMPORTING', 'CANCELLED'},
    'COMPLETE': {'CONVERTING', 'IMPORTING', 'CANCELLED'},  # Can skip conversion for torrents
    'CONVERTING': {'CONVERTED', 'CONVERSION_FAILED', 'CANCELLED'},
    'CONVERTED': {'PROCESSING', 'IMPORTING', 'CANCELLED'},
    'PROCESSING': {'PROCESSED', 'IMPORTING', 'CANCELLED'},
    'PROCESSED': {'IMPORTING', 'CANCELLED'},
    'IMPORTING': {'IMPORTED', 'IMPORT_FAILED', 'CANCELLED'},
    'IMPORTED': {'SEEDING'},  # Can transition to seeding if enabled
    'SEEDING': {'SEEDING_COMPLETE', 'CANCELLED'},  # Seeding → Complete or Cancelled
    'SEEDING_COMPLETE': set(),  # Terminal state (seeding finished)
    'SEARCH_FAILED': {'SEARCHING', 'CANCELLED'},  # Can retry
	'DOWNLOAD_FAILED': {'FOUND', 'CANCELLED'},	# Can retry with different source
	'AUDIBLE_DOWNLOAD_FAILED': {'QUEUED', 'AUDIBLE_DOWNLOADING', 'CANCELLED'},  # Retried through Audible pipeline
    'CONVERSION_FAILED': {'CONVERTING', 'CANCELLED'},  # Can retry
    'IMPORT_FAILED': {'IMPORTING', 'CANCELLED'},   # Can retry
    'CANCELLED': set()  # Terminal state
    }
    
    def __init__(self):
        """Initialize state machine."""
        self.logger = logging.getLogger("DownloadManagement.StateMachine")
        self._queue_manager = None
    
    def _get_queue_manager(self):
        """Lazy load QueueManager."""
        if self._queue_manager is None:
            from .queue_manager import QueueManager
            self._queue_manager = QueueManager()
        return self._queue_manager
    
    def transition(self, download_id: int, new_status: str) -> bool:
        """
        Transition download to new status if valid.
        
        Args:
            download_id: Download queue ID
            new_status: Target status
        
        Returns:
            True if transition successful, False otherwise
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            self.logger.error(f"Download {download_id} not found")
            return False
        
        current_status = download['status']
        
        # Validate transition
        if not self.is_valid_transition(current_status, new_status):
            self.logger.error(
                f"Invalid state transition for download {download_id}: "
                f"{current_status} → {new_status}"
            )
            return False
        
        # Perform transition
        updates = {'status': new_status}
        
        # Add timestamp for specific transitions
        if new_status in {'DOWNLOADING', 'AUDIBLE_DOWNLOADING'} and current_status in ('QUEUED', 'FOUND', 'PAUSED', 'AUDIBLE_DOWNLOAD_FAILED'):
            updates['started_at'] = datetime.now().isoformat()
        elif new_status == 'COMPLETE':
            updates['completed_at'] = datetime.now().isoformat()
        elif new_status == 'IMPORTED':
            updates['completed_at'] = datetime.now().isoformat()
        
        queue_manager.update_download(download_id, updates)
        
        self.logger.debug(f"Download {download_id}: {current_status} → {new_status}")
        return True
    
    def is_valid_transition(self, current_status: str, new_status: str) -> bool:
        """
        Check if state transition is valid.
        
        Args:
            current_status: Current download status
            new_status: Target status
        
        Returns:
            True if transition is allowed
        """
        if current_status not in self.ALLOWED_TRANSITIONS:
            self.logger.warning(f"Unknown current status: {current_status}")
            return False
        
        allowed = self.ALLOWED_TRANSITIONS[current_status]
        return new_status in allowed
    
    def can_pause(self, current_status: str) -> bool:
        """Check if download can be paused in current state."""
        return current_status in {'DOWNLOADING', 'AUDIBLE_DOWNLOADING'}
    
    def can_resume(self, current_status: str) -> bool:
        """Check if download can be resumed in current state."""
        return current_status == 'PAUSED'
    
    def can_cancel(self, current_status: str) -> bool:
        """Check if download can be cancelled in current state."""
        # Can cancel from any state except terminal states
        return current_status not in ('IMPORTED', 'CANCELLED')
    
    def can_retry(self, current_status: str) -> bool:
        """Check if download can be retried in current state."""
        return current_status in (
            'SEARCH_FAILED',
            'DOWNLOAD_FAILED',
            'AUDIBLE_DOWNLOAD_FAILED',
            'CONVERSION_FAILED',
            'IMPORT_FAILED'
        )
    
    def get_allowed_transitions(self, current_status: str) -> Set[str]:
        """
        Get all allowed transitions from current status.
        
        Args:
            current_status: Current download status
        
        Returns:
            Set of allowed target statuses
        """
        return self.ALLOWED_TRANSITIONS.get(current_status, set())
