"""
Module Name: status_service.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    In-memory activity feed for user-facing operations (search, downloads,
    conversion, imports). Provides start/update/complete semantics for UI
    surfaced events with short retention.

Location:
    /services/status_service.py

"""

# Bottleneck: pruning occurs on update; consider scheduled cleanup if events grow.
# Upgrade: add capped retention metrics and async pruning.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Any, Deque, Dict, List, Optional

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.StatusService")


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

    def __init__(self, *, logger=None):
        if getattr(self, "_initialized", False):
            return

        self.logger = logger or _LOGGER

        self._events: Deque[StatusEvent] = deque(maxlen=200)
        self._index: Dict[int, StatusEvent] = {}
        self._events_lock = Lock()
        self._counter = 0
        self._retention = timedelta(minutes=20)
        # Debounce tracking for _push_event (no lock needed — CPython GIL + acceptable
        # worst-case of one extra emit are both fine here)
        self._push_state: Dict[int, str]   = {}  # event_id → last pushed state
        self._push_time:  Dict[int, float] = {}  # event_id → monotonic timestamp of last push
        self._initialized = True

        self.logger.success(
            "Status service started successfully",
            extra={"retention_minutes": self._retention.total_seconds() / 60},
        )

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def _next_id(self) -> int:
        with self._events_lock:
            self._counter += 1
            return self._counter

    def _prune(self):
        now = datetime.utcnow()
        pruned: List[int] = []
        with self._events_lock:
            while self._events and self._events[0].expires_at < now:
                expired = self._events.popleft()
                self._index.pop(expired.id, None)
                pruned.append(expired.id)
        for eid in pruned:
            self._push_state.pop(eid, None)
            self._push_time.pop(eid, None)

    def _touch_event(self, event: StatusEvent):
        now = datetime.utcnow()
        event.updated_at = now.isoformat()
        event.expires_at = now + self._retention

    # ------------------------------------------------------------------
    # SocketIO push helper
    # ------------------------------------------------------------------
    def _push_event(self, event_dict: Dict[str, Any]):
        """Push a SocketIO notification with debouncing.

        State changes always emit immediately. Same-state updates (e.g. download
        progress ticks) are throttled to at most one push per 2 seconds per event
        to avoid flooding the socket with high-frequency progress callbacks.
        The full event dict is sent so the frontend can patch in-place without
        making a follow-up HTTP request.
        """
        event_id  = event_dict.get('id')
        new_state = event_dict.get('state', '')

        if event_id is not None:
            prev_state = self._push_state.get(event_id)
            prev_time  = self._push_time.get(event_id, 0.0)
            now_mono   = monotonic()
            if prev_state == new_state and (now_mono - prev_time) < 2.0:
                self.logger.debug(
                    "Status push throttled (same state)",
                    extra={"event_id": event_id, "state": new_state},
                )
                return
            self._push_state[event_id] = new_state
            self._push_time[event_id]  = now_mono

        try:
            from app import app, socketio  # lazy import to avoid circular dependency
            with app.app_context():
                socketio.emit('status:updated', event_dict)
            self.logger.debug(
                "Status push: status:updated emitted",
                extra={
                    "event_id": event_id,
                    "state": new_state,
                    "title": event_dict.get('title'),
                },
            )
        except Exception as exc:
            self.logger.error(
                "Status push failed",
                extra={"event_id": event_id, "state": new_state, "error": str(exc)},
            )

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

        self.logger.debug(
            "Started status event",
            extra={
                "event_id": event_id,
                "category": category,
                "title": title,
                "state": state,
                "level": level,
                "source": source,
            },
        )

        self._push_event(event.to_dict())
        return event.to_dict()

    def update_event(self, event_id: int, **updates) -> Optional[Dict[str, Any]]:
        """Update an existing event with new metadata."""

        self._prune()
        with self._events_lock:
            event = self._index.get(event_id)
            if not event:
                self.logger.warning(
                    "Status event not found for update",
                    extra={"event_id": event_id, "keys": list(updates.keys())},
                )
                return None

            for key, value in updates.items():
                if key == 'metadata' and isinstance(value, dict):
                    event.metadata.update(value)
                elif hasattr(event, key):
                    setattr(event, key, value)
                else:
                    event.metadata[key] = value

            self._touch_event(event)

            self.logger.debug(
                "Updated status event",
                extra={
                    "event_id": event_id,
                    "state": event.state,
                    "level": event.level,
                    "keys": list(updates.keys()),
                },
            )
            result = event.to_dict()

        self._push_event(result)
        return result

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
        result = self.update_event(event_id, **updates)
        if result:
            self.logger.success(
                "Status event completed successfully",
                extra={
                    "event_id": event_id,
                    "event_message": message,
                    "event_level": updates["level"],
                },
            )
        return result

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
        result = self.update_event(event_id, **updates)
        if result:
            self.logger.error(
                "Failed status event",
                extra={"event_id": event_id, "event_message": message, "error": error},
            )
        return result

    def cancel_event(self, event_id: int, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
        updates = {
            "state": "cancelled",
            "level": "warning",
        }
        if message:
            updates["message"] = message
        result = self.update_event(event_id, **updates)
        if result:
            self.logger.info(
                "Cancelled status event",
                extra={"event_id": event_id, "event_message": message},
            )
        return result

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
