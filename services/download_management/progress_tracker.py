"""
Progress Tracker
================

Tracks download progress and emits real-time SocketIO events.
Calculates ETA, speed, and overall progress metrics.
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("DownloadManagement.ProgressTracker")


class ProgressTracker:
    """
    Tracks and reports download progress.

    Features:
    - Progress percentage tracking
    - Speed / ETA calculation helpers
    - SocketIO emission with backwards-compatible argument handling
    """

    def __init__(self):
        """Initialize the progress tracker logger."""
        self.logger = logging.getLogger("DownloadManagement.ProgressTracker")
    
    def emit_progress(self, download_id: int, *args: Any, **kwargs: Any):
        """
        Emit progress update via SocketIO.
        
        Args:
            download_id: Download queue ID
            *args: Legacy positional values mapped to known fields in order
                (progress_percentage, speed, eta, current_speed,
                 eta_seconds, message, downloaded_bytes, total_bytes).
            **kwargs: Keyword arguments for the same fields or any
                additional metadata to forward to the client.
        """
        try:
            normalized = self._normalize_arguments(args, kwargs)
            socketio = self._resolve_socketio()
            event_data = self._build_payload(
                download_id=download_id,
                progress_percentage=normalized.get('progress_percentage'),
                speed=normalized.get('speed'),
                eta=normalized.get('eta'),
                current_speed=normalized.get('current_speed'),
                eta_seconds=normalized.get('eta_seconds'),
                message=normalized.get('message'),
                downloaded_bytes=normalized.get('downloaded_bytes'),
                total_bytes=normalized.get('total_bytes'),
                extra=normalized.get('extra', {})
            )
            socketio.emit('download:progress', event_data)

        except Exception:
            self.logger.exception("Error emitting progress event")

    def _normalize_arguments(self, args: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Combine positional and keyword arguments into a unified dict."""
        field_order: List[str] = [
            'progress_percentage',
            'speed',
            'eta',
            'current_speed',
            'eta_seconds',
            'message',
            'downloaded_bytes',
            'total_bytes'
        ]

        normalized: Dict[str, Any] = {}
        remaining_kwargs = dict(kwargs) if kwargs else {}

        for name, value in zip(field_order, args):
            if name not in remaining_kwargs and value is not None:
                normalized[name] = value

        for name in field_order:
            if name in remaining_kwargs:
                normalized[name] = remaining_kwargs.pop(name)

        normalized['extra'] = remaining_kwargs
        return normalized

    def _resolve_socketio(self):
        """Import SocketIO lazily to avoid circular imports."""
        from app import socketio  # Local import by design
        return socketio

    def _build_payload(
        self,
        download_id: int,
        progress_percentage: Optional[float],
        speed: Optional[int],
        eta: Optional[int],
        current_speed: Optional[int],
        eta_seconds: Optional[int],
        message: Optional[str],
        downloaded_bytes: Optional[int],
        total_bytes: Optional[int],
        extra: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assemble a sanitized payload for the SocketIO event."""
        event_data: Dict[str, Any] = {'download_id': download_id}

        if progress_percentage is not None:
            try:
                event_data['progress'] = round(float(progress_percentage), 2)
            except (TypeError, ValueError):
                self.logger.debug("Invalid progress percentage '%s'", progress_percentage)

        speed_value = current_speed if current_speed is not None else speed
        speed_int = self._coerce_int(speed_value)
        if speed_int is not None:
            event_data['speed_bytes'] = max(0, speed_int)
            event_data['speed'] = self._format_speed(event_data['speed_bytes'])

        eta_value = eta_seconds if eta_seconds is not None else eta
        eta_int = self._coerce_int(eta_value)
        if eta_int is not None:
            event_data['eta_seconds'] = eta_int
            event_data['eta'] = self._format_eta(eta_int)

        if message:
            event_data['message'] = message

        downloaded_int = self._coerce_int(downloaded_bytes)
        if downloaded_int is not None:
            event_data['downloaded_bytes'] = max(0, downloaded_int)

        total_int = self._coerce_int(total_bytes)
        if total_int is not None:
            event_data['total_bytes'] = max(0, total_int)

        if extra:
            sanitized = {
                key: value for key, value in extra.items()
                if value is not None and key not in event_data
            }
            if sanitized:
                self.logger.debug("Including extra progress fields: %s", list(sanitized.keys()))
                event_data.update(sanitized)

        return event_data

    def _coerce_int(self, value: Optional[Any]) -> Optional[int]:
        """Attempt to coerce a value to an integer, returning None on failure."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            self.logger.debug("Unable to coerce value '%s' to int for ETA", value)
            return None
    
    def _format_speed(self, bytes_per_sec: int) -> str:
        """
        Format speed for display.
        
        Args:
            bytes_per_sec: Speed in bytes/second
        
        Returns:
            Formatted string (e.g., "1.5 MB/s")
        """
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        elif bytes_per_sec < 1024 * 1024 * 1024:
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024 * 1024):.1f} GB/s"
    
    def _format_eta(self, seconds: int) -> str:
        """
        Format ETA for display.
        
        Args:
            seconds: Time remaining in seconds
        
        Returns:
            Formatted string (e.g., "5m 30s")
        """
        if seconds < 0:
            return "Unknown"
        elif seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
