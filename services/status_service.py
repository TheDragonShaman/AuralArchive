"""
Status Service
==============

Provides an in-memory activity feed describing user-facing operations such as
searches, downloads, conversions, and imports. Designed for lightweight,
short-lived status updates that can be surfaced in the UI.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Deque, Dict, List, Optional


@dataclass
class StatusEvent:
    """Structured status event stored in the feed."""

    id: int
    category: str
    title: str
    message: Optional[str] = None
    level: str = "info"  # info | success | warning | error
    state: str = "queued"  # queued | running | completed | failed | cancelled
    progress: Optional[float] = None  # 0-100
    source: Optional[str] = None
    entity_id: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=15))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        # Convert expires_at datetime to iso string for JSON serialization
        payload["expires_at"] = self.expires_at.isoformat()
        return payload


class StatusService:
    """Singleton-like status feed repository with thread-safe helpers."""

    _instance: Optional["StatusService"] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._events: Deque[StatusEvent] = deque(maxlen=200)
        self._index: Dict[int, StatusEvent] = {}
        self._events_lock = Lock()
        self._counter = 0
        self._retention = timedelta(minutes=20)
        self._initialized = True

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def _next_id(self) -> int:
        with self._events_lock:
            self._counter += 1
            return self._counter

    def _prune(self):
        now = datetime.utcnow()
        with self._events_lock:
            while self._events and self._events[0].expires_at < now:
                expired = self._events.popleft()
                self._index.pop(expired.id, None)

    def _touch_event(self, event: StatusEvent):
        now = datetime.utcnow()
        event.updated_at = now.isoformat()
        event.expires_at = now + self._retention

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start_event(
        self,
        *,
        category: str,
        title: str,
        message: Optional[str] = None,
        level: str = "info",
        state: str = "running",
        progress: Optional[float] = None,
        source: Optional[str] = None,
        entity_id: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an event that can later be updated or completed."""

        event_id = self._next_id()
        event = StatusEvent(
            id=event_id,
            category=category,
            title=title,
            message=message,
            level=level,
            state=state,
            progress=progress,
            source=source,
            entity_id=entity_id,
            metadata=metadata or {},
        )

        with self._events_lock:
            self._events.append(event)
            self._index[event_id] = event

        return event.to_dict()

    def update_event(self, event_id: int, **updates) -> Optional[Dict[str, Any]]:
        """Update an existing event with new metadata."""

        self._prune()
        with self._events_lock:
            event = self._index.get(event_id)
            if not event:
                return None

            for key, value in updates.items():
                if key == 'metadata' and isinstance(value, dict):
                    event.metadata.update(value)
                elif hasattr(event, key):
                    setattr(event, key, value)
                else:
                    event.metadata[key] = value

            self._touch_event(event)
            return event.to_dict()

    def complete_event(
        self,
        event_id: int,
        *,
        message: Optional[str] = None,
        level: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark an event as completed."""

        updates = {
            "state": "completed",
            "level": level or "success",
            "progress": 100.0,
        }
        if message:
            updates["message"] = message
        if metadata:
            updates.setdefault("metadata", {}).update(metadata)
        return self.update_event(event_id, **updates)

    def fail_event(
        self,
        event_id: int,
        *,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark an event as failed/cancelled."""

        updates = {
            "state": "failed",
            "level": "error",
        }
        if message:
            updates["message"] = message
        if error:
            updates.setdefault("metadata", {}).update({"error": error})
        return self.update_event(event_id, **updates)

    def cancel_event(self, event_id: int, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
        updates = {
            "state": "cancelled",
            "level": "warning",
        }
        if message:
            updates["message"] = message
        return self.update_event(event_id, **updates)

    def record_snapshot(
        self,
        *,
        category: str,
        title: str,
        message: Optional[str] = None,
        level: str = "info",
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a simple informational event that does not require updates."""

        return self.start_event(
            category=category,
            title=title,
            message=message,
            level=level,
            state="completed",
            progress=100.0,
            source=source,
            metadata=metadata,
        )

    def get_events(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Return the most recent events (newest first)."""

        self._prune()
        with self._events_lock:
            items = list(self._events)[-limit:]
        return [event.to_dict() for event in reversed(items)]

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        self._prune()
        with self._events_lock:
            event = self._index.get(event_id)
            return event.to_dict() if event else None


def get_status_service() -> StatusService:
    """Convenience helper for direct imports."""
    return StatusService()
