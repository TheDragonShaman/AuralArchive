"""
Event Emitter
=============

Emits real-time SocketIO events for download lifecycle and feeds the
user-facing status service with curated updates.
"""

import logging
from threading import Lock
from typing import Any, Callable, Optional

logger = logging.getLogger("DownloadManagement.EventEmitter")


class EventEmitter:
    """
    Emits SocketIO events for download events.
    
    Events:
    - download:queued
    - download:started
    - download:progress
    - download:completed
    - download:failed
    - download:cancelled
    - download:paused
    - download:resumed
    - queue:updated
    """
    
    def __init__(self):
        """Initialize event emitter."""
        self.logger = logging.getLogger("DownloadManagement.EventEmitter")
        self._status_service = None
        self._status_lock = Lock()
        self._status_events = {}
        self._download_lookup: Optional[Callable[[int], Optional[dict]]] = None

    # ------------------------------------------------------------------
    # Wiring helpers
    # ------------------------------------------------------------------
    def attach_lookup(self, lookup: Callable[[int], Optional[dict]]):
        """Attach a callable that returns download metadata by ID."""
        self._download_lookup = lookup

    def _get_status_service(self):
        if self._status_service is None:
            try:
                from services.service_manager import get_status_service

                self._status_service = get_status_service()
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.debug(f"Status service unavailable: {exc}")
                self._status_service = None
        return self._status_service

    def _get_download_details(self, download_id: int) -> dict:
        if not self._download_lookup:
            return {}
        try:
            return self._download_lookup(download_id) or {}
        except Exception as exc:
            self.logger.debug(f"Download lookup failed: {exc}")
            return {}

    def _ensure_status_event(self, download_id: int, *, state: str, message: str) -> Optional[int]:
        service = self._get_status_service()
        if not service:
            return None

        with self._status_lock:
            existing = self._status_events.get(download_id)
            if existing:
                return existing

            details = self._get_download_details(download_id)
            title = details.get('book_title') or details.get('book_asin') or f'Download #{download_id}'
            metadata = {
                'asin': details.get('book_asin'),
                'download_id': download_id,
                'priority': details.get('priority'),
                'status': details.get('status'),
            }
            event = service.start_event(
                category='download',
                title=title,
                message=message,
                source='Downloads',
                entity_id=download_id,
                state=state,
                progress=0.0,
                metadata=metadata,
            )
            self._status_events[download_id] = event['id']
            return event['id']

    def _update_status_event(self, download_id: int, **updates):
        service = self._get_status_service()
        if not service:
            return
        with self._status_lock:
            event_id = self._status_events.get(download_id)
        if not event_id:
            event_id = self._ensure_status_event(download_id, state=updates.get('state', 'queued'), message=updates.get('message', 'Download update'))
            if not event_id:
                return
        metadata = updates.pop('metadata', None)
        payload = {k: v for k, v in updates.items() if v is not None}
        if metadata is not None:
            payload['metadata'] = metadata
        service.update_event(event_id, **payload)

    def _complete_status_event(self, download_id: int, *, success: bool, message: Optional[str] = None, error: Optional[str] = None):
        service = self._get_status_service()
        if not service:
            return
        with self._status_lock:
            event_id = self._status_events.get(download_id)
        if not event_id:
            return
        if success:
            service.complete_event(event_id, message=message)
        elif error:
            service.fail_event(event_id, message=message, error=error)
        else:
            service.cancel_event(event_id, message=message)
        with self._status_lock:
            self._status_events.pop(download_id, None)
    
    def _emit(self, event: str, data: dict):
        """
        Emit SocketIO event.
        
        Args:
            event: Event name
            data: Event payload
        """
        try:
            from app import socketio
            socketio.emit(event, data)
            self.logger.debug(f"Emitted event: {event}")
        except Exception as e:
            self.logger.error(f"Error emitting event {event}: {e}")
    
    def emit_queue_added(self, download_id: int, book_asin: str):
        """Emit queue item added event."""
        self._emit('queue:item_added', {
            'download_id': download_id,
            'book_asin': book_asin
        })
        self._ensure_status_event(
            download_id,
            state='queued',
            message=f'Queued download ({book_asin})'
        )
    
    def emit_download_started(self, download_id: int):
        """Emit download started event."""
        self._emit('download:started', {
            'download_id': download_id
        })
        details = self._get_download_details(download_id)
        client = details.get('download_client') or 'client'
        self._update_status_event(
            download_id,
            state='downloading',
            message=f'Started via {client}',
            progress=0.0,
            metadata={'status': 'DOWNLOADING'}
        )

    def emit_progress(self, download_id: int, progress: float, message: Optional[str] = None):
        """Emit download progress event for UI updates."""
        payload = {
            'download_id': download_id,
            'progress': float(progress)
        }
        if message:
            payload['message'] = message
        self._emit('download:progress', payload)
        self._update_status_event(
            download_id,
            state='downloading',
            message=message or 'Downloading…',
            progress=float(progress),
            metadata={'status': 'DOWNLOADING'}
        )
    
    def emit_download_completed(self, download_id: int):
        """Emit download completed event."""
        self._emit('download:completed', {
            'download_id': download_id
        })
        self._complete_status_event(download_id, success=True, message='Download complete')

    def emit_completed(self, download_id: int, *_args, **_kwargs):
        """Legacy alias for emit_download_completed."""
        self.emit_download_completed(download_id)

    def emit_complete(self, download_id: int, *_args, **_kwargs):
        """Legacy alias used by older pipeline code."""
        self.emit_download_completed(download_id)
    
    def emit_download_failed(self, download_id: int, error: str):
        """Emit download failed event."""
        self._emit('download:failed', {
            'download_id': download_id,
            'error': error
        })
        self._complete_status_event(download_id, success=False, message='Download failed', error=error)
    
    def emit_download_cancelled(self, download_id: int):
        """Emit download cancelled event."""
        self._emit('download:cancelled', {
            'download_id': download_id
        })
        self._complete_status_event(download_id, success=False, message='Download cancelled')
    
    def emit_download_paused(self, download_id: int):
        """Emit download paused event."""
        self._emit('download:paused', {
            'download_id': download_id
        })
        self._update_status_event(download_id, state='paused', message='Download paused', metadata={'status': 'PAUSED'})
    
    def emit_download_resumed(self, download_id: int):
        """Emit download resumed event."""
        self._emit('download:resumed', {
            'download_id': download_id
        })
        self._update_status_event(download_id, state='downloading', message='Download resumed', metadata={'status': 'DOWNLOADING'})
    
    def emit_state_changed(self, download_id: int, old_status: str, new_status: str):
        """Emit state transition event."""
        self._emit('download:state_changed', {
            'download_id': download_id,
            'old_status': old_status,
            'new_status': new_status
        })
        self._update_status_event(
            download_id,
            state=new_status.lower(),
            message=f'Status changed to {new_status}',
            metadata={'status': new_status}
        )
    
    def emit_queue_updated(self):
        """Emit queue updated event (triggers frontend refresh)."""
        self._emit('queue:updated', {})
