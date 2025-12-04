"""
Audible Download Helper - AuralArchive

Provides a Python-native implementation for downloading Audible content
with cooperative cancellation and progress reporting.
"""

import asyncio
import json
import logging
import secrets
from pathlib import Path
from threading import Event
from typing import Optional, Dict, Any, Callable
from urllib.parse import urlencode

import audible

from utils.logger import get_module_logger


class AudibleDownloadHelper:
    """
    Helper class for downloading audiobooks from Audible using the Python API.

    Supports both AAX and AAXC formats with real-time progress tracking
    and accepts a cancellation event to stop long-running downloads.
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[Event] = None
    ):
        """
        Initialize the download helper.

        Args:
            progress_callback: Optional callback for progress updates
                (downloaded_bytes, total_bytes, message).
            cancel_event: Optional event used to cooperatively cancel
                in-flight downloads.
        """
        self.logger = get_module_logger("AudibleDownloadHelper")
        self.auth_file = Path("auth/audible_auth.json")
        self.auth = None
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event
        self._load_auth()

    def _load_auth(self):
        """Load authentication from file."""
        if not self.auth_file.exists():
            raise Exception("Authentication file not found. Please authenticate first.")

        try:
            self.auth = audible.Authenticator.from_file(self.auth_file)
            self.logger.debug("Loaded Audible authentication from %s", self.auth_file)
        except Exception as exc:
            raise Exception(f"Failed to load authentication: {exc}") from exc

    def _raise_if_cancelled(self):
        """Raise asyncio.CancelledError if a cancellation request is pending."""
        if self.cancel_event and self.cancel_event.is_set():
            self.logger.info("Audible download cancellation requested; aborting transfer")
            raise asyncio.CancelledError("Audible download cancelled")

    def _get_codec_info(self, available_codecs: list, quality: str) -> tuple:
        """Return the best codec tuple for the requested quality."""
        if not available_codecs:
            return None, None

        codec_high_quality = "AAX_44_128"
        codec_normal_quality = "AAX_22_64"

        if quality == "best":
            best = (None, 0, 0, None)
            for codec in available_codecs:
                name = codec.get("name", "")
                if not name.startswith("aax_"):
                    continue
                try:
                    sample_rate_str, bitrate_str = name[4:].split("_")
                    sample_rate = int(sample_rate_str)
                    bitrate = int(bitrate_str)
                except (ValueError, AttributeError):
                    continue

                if sample_rate > best[1] or (sample_rate == best[1] and bitrate > best[2]):
                    best = (name.upper(), sample_rate, bitrate, codec.get("enhanced_codec"))

            return best[0], best[3] if best[0] else (None, None)

        verify = codec_high_quality if quality == "high" else codec_normal_quality
        for codec in available_codecs:
            if verify == codec.get("name", "").upper():
                return verify, codec.get("enhanced_codec")

        return None, None

    async def download_file(
        self,
        client: audible.AsyncClient,
        url: str,
        output_path: Path,
        expected_content_types: Optional[list] = None
    ) -> bool:
        """
        Download a file from URL with progress tracking using an authenticated client.
        """
        expected = expected_content_types or [
            "audio/aax",
            "audio/vnd.audible.aax",
            "audio/audible",
            "audio/mpeg",
            "audio/x-m4a",
        ]

        self._raise_if_cancelled()
        self.logger.debug("Starting download to %s", output_path)

        async with client.session.stream("GET", url, follow_redirects=True) as response:
            self._raise_if_cancelled()
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if expected and content_type not in expected:
                self.logger.warning("Unexpected content type: %s", content_type)

            try:
                total_size = int(response.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                total_size = 0

            self.logger.debug(
                "Download size: %s bytes (%.2f MB)",
                total_size,
                total_size / 1024 / 1024 if total_size else 0.0,
            )

            downloaded = 0
            chunk_size = 65536  # Larger chunks reduce per-iteration overhead
            last_progress_reported = -1
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as target:
                async for chunk in response.aiter_bytes(chunk_size):
                    self._raise_if_cancelled()
                    target.write(chunk)
                    downloaded += len(chunk)

                    if self.progress_callback:
                        if total_size > 0:
                            progress_pct = int((downloaded / total_size) * 100)
                            if progress_pct > last_progress_reported:
                                last_progress_reported = progress_pct
                                self.progress_callback(downloaded, total_size, f"{progress_pct}% complete")
                        else:
                            # If size unknown, emit periodic updates every ~5 MB
                            if downloaded - max(last_progress_reported, 0) >= 5 * 1024 * 1024:
                                last_progress_reported = downloaded
                                self.progress_callback(downloaded, total_size, "downloading...")

            self._raise_if_cancelled()
            if self.progress_callback and total_size > 0 and last_progress_reported < 100:
                self.progress_callback(total_size, total_size, "100% complete")
            self.logger.debug("Download complete: %s", output_path)

        return True

    async def download_aax(
        self,
        client: audible.AsyncClient,
        asin: str,
        output_dir: Path,
        filename: str,
        quality: str = "best"
    ) -> Path:
        """Download a book in AAX format using an authenticated client."""
        self._raise_if_cancelled()

        library_response = await client.get(
            "library",
            asin=asin,
            response_groups="media, product_attrs"
        )
        self._raise_if_cancelled()

        if not library_response.get("items"):
            raise Exception(f"Book {asin} not found in library")

        item = library_response["items"][0]
        codec_name, _ = self._get_codec_info(item.get("available_codecs", []), quality)
        if not codec_name:
            raise Exception(f"No AAX codec available for quality '{quality}'")

        domain = self.auth.locale.domain
        params = urlencode({"asin": asin, "codec": codec_name})
        url = f"https://www.audible.{domain}/library/download?{params}"

        output_path = output_dir / f"{filename}-{codec_name}.aax"
        await self.download_file(
            client,
            url,
            output_path,
            expected_content_types=["audio/aax", "audio/vnd.audible.aax", "audio/audible"],
        )
        self._raise_if_cancelled()
        return output_path

    async def download_aaxc(
        self,
        client: audible.AsyncClient,
        asin: str,
        output_dir: Path,
        filename: str,
        quality: str = "best",
        save_voucher: bool = True
    ) -> tuple:
        """Download a book in AAXC format (with voucher) using an authenticated client."""
        self._raise_if_cancelled()

        quality_setting = "High" if quality in ("best", "high") else "Normal"
        body = {
            "supported_drm_types": ["Mpeg", "Adrm"],
            "quality": quality_setting,
            "consumption_type": "Download",
            "response_groups": "last_position_heard, pdf_url, content_reference",
        }
        headers = {
            "X-Amzn-RequestId": secrets.token_hex(20).upper(),
            "X-ADP-SW": "37801821",
            "X-ADP-Transport": "WIFI",
            "X-ADP-LTO": "120",
            "X-Device-Type-Id": "A2CZJZGLK2JJVM",
            "device_idiom": "phone",
        }

        license_response = await client.post(
            f"content/{asin}/licenserequest",
            body=body,
            headers=headers,
        )
        self._raise_if_cancelled()
        self.logger.info("AAXC license obtained for %s", asin)

        content_metadata = license_response["content_license"]["content_metadata"]
        url = content_metadata["content_url"]["offline_url"]
        codec = content_metadata["content_reference"]["content_format"]
        extension = "mp3" if codec.lower() == "mpeg" else "aaxc"

        audio_path = output_dir / f"{filename}-{codec}.{extension}"
        await self.download_file(client, url, audio_path)
        self._raise_if_cancelled()

        voucher_path = None
        if save_voucher:
            voucher_path = audio_path.with_suffix(".voucher")
            license_payload = license_response
            if isinstance(license_payload, str):
                try:
                    license_payload = json.loads(license_payload)
                except json.JSONDecodeError:
                    self.logger.warning(
                        "Voucher payload for %s returned as string but could not be parsed; saving raw text",
                        asin
                    )
            voucher_path.write_text(json.dumps(license_payload, indent=4))
            self.logger.info("Voucher saved to %s", voucher_path)

        return audio_path, voucher_path

    async def download_book(
        self,
        asin: str,
        output_dir: Path,
        filename: str,
        format_preference: str = "aaxc",
        quality: str = "best",
        aax_fallback: bool = True
    ) -> Dict[str, Any]:
        """Download a book with format fallback and cooperative cancellation."""
        self._raise_if_cancelled()

        headers = {"User-Agent": "Audible/671 CFNetwork/1240.0.4 Darwin/20.6.0"}
        async with audible.AsyncClient(auth=self.auth, headers=headers) as client:
            try:
                self._raise_if_cancelled()

                if format_preference in ("aax", "aax-fallback"):
                    try:
                        audio_path = await self.download_aax(client, asin, output_dir, filename, quality)
                        return {
                            "success": True,
                            "format": "aax",
                            "audio_file": str(audio_path),
                            "voucher_file": None,
                        }
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if aax_fallback or format_preference == "aax-fallback":
                            self.logger.info("AAX download failed, falling back to AAXC: %s", exc)
                        else:
                            raise

                audio_path, voucher_path = await self.download_aaxc(
                    client,
                    asin,
                    output_dir,
                    filename,
                    quality,
                    save_voucher=True,
                )
                return {
                    "success": True,
                    "format": "aaxc",
                    "audio_file": str(audio_path),
                    "voucher_file": str(voucher_path) if voucher_path else None,
                }

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("Download failed for %s: %s", asin, exc)
                return {
                    "success": False,
                    "error": str(exc),
                }
