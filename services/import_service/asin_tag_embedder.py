"""Utilities for embedding ASIN metadata into audio files.

Audiobookshelf recognizes the custom metadata keys ``ASIN`` and
``audible_asin`` in both ID3 (MP3) tags and MP4/M4B atoms. This helper writes
those tags whenever we import a file so the downstream scanner can link the
file back to the correct Audible book automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - mutagen is optional at runtime
    from mutagen.id3 import ID3, TXXX, ID3NoHeaderError  # type: ignore
    from mutagen.mp4 import MP4, MP4FreeForm  # type: ignore
except ImportError:  # pragma: no cover
    ID3 = None  # type: ignore
    TXXX = None  # type: ignore
    ID3NoHeaderError = None  # type: ignore
    MP4 = None  # type: ignore
    MP4FreeForm = None  # type: ignore


class AsinTagEmbedder:
    """Embed Audible ASIN metadata inside supported audio containers."""

    MP3_EXTENSIONS = {'.mp3'}
    MP4_EXTENSIONS = {'.m4b', '.m4a', '.mp4'}

    def __init__(self) -> None:
        self.logger = logging.getLogger("ImportService.AsinTagEmbedder")

    def embed_asin(self, file_path: str, asin: Optional[str]) -> bool:
        """Write ASIN tags to ``file_path`` if the format supports it."""
        if not asin:
            return False

        extension = Path(file_path).suffix.lower()

        if extension in self.MP3_EXTENSIONS:
            return self._embed_id3_asin(file_path, asin)
        if extension in self.MP4_EXTENSIONS:
            return self._embed_mp4_asin(file_path, asin)

        self.logger.debug("Skipping ASIN embedding for %s (unsupported extension)", file_path)
        return False

    # Internal helpers -----------------------------------------------------

    def _embed_id3_asin(self, file_path: str, asin: str) -> bool:
        if ID3 is None or TXXX is None:
            self.logger.debug("mutagen.id3 not available; cannot embed ASIN")
            return False

        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:  # type: ignore[operator]
                tags = ID3()

            tags.delall('TXXX:ASIN')
            tags.delall('TXXX:audible_asin')
            tags.add(TXXX(encoding=3, desc='ASIN', text=[asin]))
            tags.add(TXXX(encoding=3, desc='audible_asin', text=[asin]))
            tags.save(file_path, v2_version=3)
            self.logger.debug("Embedded ASIN %s via ID3 into %s", asin, file_path)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("Unable to embed ASIN tag via ID3 for %s: %s", file_path, exc)
            return False

    def _embed_mp4_asin(self, file_path: str, asin: str) -> bool:
        if MP4 is None:
            self.logger.debug("mutagen.mp4 not available; cannot embed ASIN")
            return False

        try:
            tags = MP4(file_path)
            value = asin.encode('utf-8')
            tags['----:com.apple.iTunes:ASIN'] = [value]
            tags['----:com.apple.iTunes:audible_asin'] = [value]
            tags.save()
            self.logger.debug("Embedded ASIN %s via MP4 atoms into %s", asin, file_path)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("Unable to embed ASIN tag via MP4 atoms for %s: %s", file_path, exc)
            return False


__all__ = ['AsinTagEmbedder']
