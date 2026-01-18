"""
Module Name: ffmpeg_handler.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Builds and executes FFmpeg commands for audiobook conversion workflows,
    including voucher handling for AAX/AAXC formats.

Location:
    /services/conversion_service/ffmpeg_handler.py

"""

import base64
import json
import os
import re
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import audible
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from utils.logger import get_module_logger


class FFmpegHandler:
    """Universal Handler for FFmpeg operations supporting AAX and AAXC formats"""

    def __init__(self, *, logger=None):
        self.logger = logger or get_module_logger("Service.Conversion.FFmpegHandler")
    
    # ============================================================================
    # FORMAT DETECTION AND KEY EXTRACTION
    # ============================================================================
    
    def detect_audio_format(self, input_file: str) -> str:
        """Detect if file is AAX, AAXC, or other format"""
        try:
            ext = Path(input_file).suffix.lower()
            if ext == '.aax':
                return 'aax'
            elif ext == '.aaxc':
                return 'aaxc'
            else:
                return 'other'
        except Exception as e:
            self.logger.exception("Error detecting format", extra={"input_file": input_file, "error": str(e)})
            return 'unknown'
    
    def find_voucher_file(self, aaxc_file: str) -> Optional[str]:
        """Find matching voucher file using multiple discovery strategies"""
        try:
            directory = os.path.dirname(aaxc_file)
            base_name = Path(aaxc_file).stem  # filename without extension
            
            # Strategy 1: Direct name patterns
            patterns = [
                f"{base_name}.voucher",
                f"{base_name}.json", 
                aaxc_file.replace('.aaxc', '.voucher'),
                aaxc_file.replace('.aaxc', '.json')
            ]
            
            for pattern in patterns:
                if os.path.exists(pattern):
                    if self.is_valid_voucher(pattern):
                        self.logger.info("Found voucher file", extra={"voucher_file": pattern, "aaxc_file": aaxc_file})
                        return pattern
            
            # Strategy 2: Content-based discovery in same directory
            if directory:  # Only if directory exists
                for file in os.listdir(directory):
                    if file.endswith(('.json', '.voucher')):
                        voucher_path = os.path.join(directory, file)
                        if self.is_valid_voucher(voucher_path):
                            # Check if ASIN matches (if available)
                            if self.voucher_matches_file(voucher_path, aaxc_file):
                                self.logger.info("Found matching voucher by content", extra={"voucher_file": voucher_path, "aaxc_file": aaxc_file})
                                return voucher_path

            self.logger.debug("No voucher file discovered automatically", extra={"aaxc_file": aaxc_file})
            return None
            
        except Exception as e:
            self.logger.exception("Error finding voucher file", extra={"aaxc_file": aaxc_file, "error": str(e)})
            return None
    
    def is_valid_voucher(self, file_path: str) -> bool:
        """Check if file contains valid voucher structure"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Check for required voucher structure
            if not isinstance(data, dict):
                return False
                
            content_license = data.get('content_license', {})
            license_response = content_license.get('license_response', {})
            
            # Must have both key and iv
            has_key = 'key' in license_response and license_response['key']
            has_iv = 'iv' in license_response and license_response['iv']
            
            return has_key and has_iv
            
        except Exception as e:
            self.logger.debug("File is not a valid voucher", extra={"voucher_file": file_path, "error": str(e)})
            return False
    
    def voucher_matches_file(self, voucher_path: str, aaxc_file: str) -> bool:
        """Check if voucher ASIN matches the audio file"""
        try:
            with open(voucher_path, 'r', encoding='utf-8') as f:
                voucher_data = json.load(f)
            
            voucher_asin = voucher_data.get('content_license', {}).get('asin')
            
            # If no ASIN in voucher, assume it matches
            if not voucher_asin:
                return True
            
            # Try to extract ASIN from filename (format like: Book_Name-B0CK4ZRWMY-...)
            filename = os.path.basename(aaxc_file)
            asin_match = re.search(r'[Bb]0[A-Z0-9]{8}', filename)
            
            if asin_match:
                file_asin = asin_match.group()
                return file_asin.upper() == voucher_asin.upper()
            
            # If can't extract ASIN from filename, assume it matches
            return True
            
        except Exception as e:
            self.logger.debug("Error checking voucher match", extra={"voucher_file": voucher_path, "aaxc_file": aaxc_file, "error": str(e)})
            return True  # Default to assuming match
    
    def extract_voucher_keys(self, voucher_file: str) -> Tuple[str, str]:
        """Extract audible_key and audible_iv from voucher file"""
        try:
            with open(voucher_file, 'r', encoding='utf-8') as f:
                voucher_data = json.load(f)

            if isinstance(voucher_data, str):
                try:
                    voucher_data = json.loads(voucher_data)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Voucher {voucher_file} contains string payload but cannot be decoded: {exc}"
                    ) from exc

            content_license = voucher_data.get('content_license') or voucher_data.get('contentLicense')
            if content_license is None:
                raise ValueError("Voucher missing content_license section")

            license_response = content_license.get('license_response') or content_license.get('licenseResponse')

            # If the voucher already holds decrypted keys, use them directly
            if isinstance(license_response, dict) and 'key' in license_response and 'iv' in license_response:
                key = license_response['key']
                iv = license_response['iv']
                if not key or not iv:
                    raise ValueError("Key or IV is empty in voucher file")
                self.logger.debug("Extracted keys from voucher JSON", extra={"voucher_file": voucher_file, "key_prefix": key[:8], "iv_prefix": iv[:8]})
                return key, iv

            if not isinstance(license_response, str):
                raise ValueError("Voucher license_response section is not a string or object with keys")

            asin = content_license.get('asin') or content_license.get('ASIN')
            if not asin:
                raise ValueError("Voucher missing ASIN for decryption")

            decrypted = self._decrypt_voucher_payload(asin, license_response)
            key = decrypted.get('key')
            iv = decrypted.get('iv')

            if not key or not iv:
                raise ValueError("Decrypted voucher did not contain key/iv")

            self.logger.debug("Decrypted keys from voucher", extra={"voucher_file": voucher_file, "key_prefix": key[:8], "iv_prefix": iv[:8]})
            return key, iv

        except KeyError as e:
            raise ValueError(f"Invalid voucher structure - missing {e}")
        except Exception as e:
            raise ValueError(f"Error extracting keys from voucher {voucher_file}: {e}")

    def _decrypt_voucher_payload(self, asin: str, encrypted_voucher: str) -> Dict[str, str]:
        """Decrypt the license_response payload to recover audible_key/iv."""
        try:
            auth = audible.Authenticator.from_file('auth/audible_auth.json')
        except Exception as exc:
            raise ValueError(f"Failed to load Audible auth for voucher decryption: {exc}")

        device_info = getattr(auth, 'device_info', None) or {}
        customer_info = getattr(auth, 'customer_info', None) or {}

        device_serial = device_info.get('device_serial_number')
        device_type = device_info.get('device_type')
        customer_id = customer_info.get('user_id')

        if not all([device_serial, device_type, customer_id]):
            raise ValueError("Authenticator missing device/customer metadata for voucher decryption")

        try:
            buffer = (device_type + device_serial + customer_id + asin).encode('ascii')
        except UnicodeEncodeError as exc:
            raise ValueError(f"Failed to encode voucher derivation data: {exc}")

        digest = sha256(buffer).digest()
        aes_key = digest[:16]
        aes_iv = digest[16:]

        try:
            ciphertext = base64.b64decode(encrypted_voucher)
        except Exception as exc:
            raise ValueError(f"Voucher payload is not valid base64: {exc}")

        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        plaintext = plaintext.rstrip(b"\x00")

        try:
            decoded = plaintext.decode('utf-8')
        except UnicodeDecodeError:
            decoded = plaintext.decode('utf-8', errors='ignore')

        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            match = re.match(r'^\{"key":"(?P<key>[^"\\]+)","iv":"(?P<iv>[^"\\]+)"', decoded)
            if match:
                payload = match.groupdict()
            else:
                raise ValueError("Unable to parse decrypted voucher payload")

        if 'key' not in payload or 'iv' not in payload:
            raise ValueError("Decrypted voucher payload missing key/iv fields")

        return payload
    
    def determine_conversion_method(self, input_file: str) -> Tuple[str, Optional[str]]:
        """Determine which decryption method to use and return (method, voucher_file)"""
        format_type = self.detect_audio_format(input_file)
        
        if format_type == 'aax':
            self.logger.info("AAX file detected - using activation bytes", extra={"input_file": input_file})
            return 'activation_bytes', None
        
        elif format_type == 'aaxc':
            voucher_file = self.find_voucher_file(input_file)
            if voucher_file:
                self.logger.debug("AAXC voucher detected during discovery", extra={"input_file": input_file, "voucher_file": voucher_file})
                return 'voucher_keys', voucher_file
            else:
                self.logger.debug("AAXC voucher not discovered; will try activation bytes fallback if provided", extra={"input_file": input_file})
                return 'activation_bytes_fallback', None
        
        elif format_type == 'other':
            self.logger.info("Non-DRM audio file detected - no decryption needed", extra={"input_file": input_file})
            return 'no_drm', None
        
        else:
            self.logger.error("Unknown audio format", extra={"input_file": input_file})
            return 'unknown', None
    
    def validate_installation(self) -> Dict[str, Any]:
        """Validate FFmpeg installation and available codecs"""
        try:
            # Check FFmpeg availability
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': 'FFmpeg not found or not working',
                    'ffmpeg_available': False
                }
            
            # Parse version
            version_match = re.search(r'ffmpeg version ([^\s]+)', result.stdout)
            version = version_match.group(1) if version_match else 'unknown'
            
            # Check available codecs
            codecs_result = subprocess.run(['ffmpeg', '-codecs'], capture_output=True, text=True, timeout=10)
            available_codecs = self._parse_available_codecs(codecs_result.stdout)
            
            # Check for optimal codecs
            has_libfdk_aac = 'libfdk_aac' in available_codecs
            has_aac = 'aac' in available_codecs
            
            return {
                'success': True,
                'ffmpeg_available': True,
                'version': version,
                'available_codecs': available_codecs,
                'has_libfdk_aac': has_libfdk_aac,
                'has_aac': has_aac,
                'recommended_codec': 'libfdk_aac' if has_libfdk_aac else 'aac',
                'quality_note': 'Optimal quality available' if has_libfdk_aac else 'Good quality available'
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'FFmpeg validation timed out',
                'ffmpeg_available': False
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'FFmpeg not found in PATH',
                'ffmpeg_available': False
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'FFmpeg validation failed: {str(e)}',
                'ffmpeg_available': False
            }
    
    def _parse_available_codecs(self, codecs_output: str) -> List[str]:
        """Parse FFmpeg codecs output to get available audio codecs"""
        codecs = []
        for line in codecs_output.split('\n'):
            if 'A' in line[:6]:  # Audio codec indicator
                # Extract codec name (typically after the flags)
                match = re.search(r'\s+(\w+)\s+', line[6:])
                if match:
                    codecs.append(match.group(1))
        return codecs
    
    # ============================================================================
    # UNIVERSAL COMMAND BUILDING
    # ============================================================================
    
    def build_conversion_command(
        self,
        input_file: str,
        output_file: str,
        quality_settings: Dict[str, Any],
        activation_bytes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        voucher_file: Optional[str] = None
    ) -> List[str]:
        """Build FFmpeg command with universal AAX/AAXC support
        
        Automatically detects format and uses appropriate decryption method:
        - AAX files: activation_bytes
        - AAXC files: voucher keys (audible_key/audible_iv)
        - Non-DRM: direct conversion
        """
        
        # Determine conversion method based on file inspection
        method, detected_voucher = self.determine_conversion_method(input_file)

        # When caller provides a voucher, always prefer it over discovery
        voucher_to_use = voucher_file or detected_voucher
        if voucher_file and method != 'voucher_keys':
            if voucher_to_use and os.path.exists(voucher_to_use):
                self.logger.info(
                    "Explicit voucher supplied; forcing voucher-based conversion",
                    extra={"input_file": input_file, "voucher_file": voucher_to_use}
                )
                method = 'voucher_keys'
            else:
                self.logger.warning(
                    "Voucher path provided but not found; keeping detected method",
                    extra={"input_file": input_file, "voucher_file": voucher_file, "method": method}
                )
        
        # Build command with appropriate method
        try:
            return self._build_command_for_method(
                input_file, output_file, quality_settings, 
                method, activation_bytes, voucher_to_use, metadata
            )
        except Exception as e:
            self.logger.exception("Failed to build conversion command", extra={"input_file": input_file, "output_file": output_file, "error": str(e)})
            raise
    
    def _build_command_for_method(
        self,
        input_file: str,
        output_file: str,
        quality_settings: Dict[str, Any],
        method: str,
        activation_bytes: Optional[str] = None,
        voucher_file: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Build FFmpeg command for specific conversion method"""
        
        cmd = ['ffmpeg', '-y']  # -y to overwrite output files
        
        # Add decryption parameters based on method
        if method == 'activation_bytes':
            if not activation_bytes:
                raise ValueError("Activation bytes required for AAX conversion but not provided")
            cmd.extend(['-activation_bytes', activation_bytes])
            self.logger.debug("Using activation bytes for AAX decryption", extra={"input_file": input_file})
            
        elif method == 'voucher_keys':
            if not voucher_file:
                raise ValueError("Voucher file required for AAXC conversion but not found")
            key, iv = self.extract_voucher_keys(voucher_file)
            cmd.extend(['-audible_key', key, '-audible_iv', iv])
            self.logger.debug("Using voucher keys for AAXC decryption", extra={"input_file": input_file, "voucher_file": voucher_file})
            
        elif method == 'activation_bytes_fallback':
            if not activation_bytes:
                raise ValueError("Activation bytes required for AAXC fallback but not provided")
            cmd.extend(['-activation_bytes', activation_bytes])
            self.logger.warning("Using activation bytes fallback for AAXC (voucher missing)", extra={"input_file": input_file})
            
        elif method == 'no_drm':
            self.logger.debug("No DRM decryption needed", extra={"input_file": input_file})
            
        else:
            raise ValueError(f"Unknown conversion method: {method}")
        
        # Input file
        cmd.extend(['-i', input_file])
        
        # Determine output handling based on file extension
        output_ext = Path(output_file).suffix.lower()
        
        # Audio processing strategy
        if output_ext in ['.m4b', '.m4a']:
            # M4B/M4A output - prefer stream copy for speed
            cmd.extend(['-c', 'copy'])  # Copy all compatible streams
            cmd.extend(['-map_metadata', '0'])  # Preserve metadata
            cmd.extend(['-map_chapters', '0'])   # Preserve chapters
            self.logger.debug("Using stream copy for M4B/M4A output (fast conversion)", extra={"output_file": output_file})
            
        else:
            # Other formats - re-encode as needed
            codec = quality_settings.get('codec', 'aac')
            cmd.extend(['-c:a', codec])
            
            # Audio quality settings (only for re-encoding)
            bitrate = quality_settings.get('bitrate', '128k')
            cmd.extend(['-b:a', bitrate])
            
            sample_rate = quality_settings.get('sample_rate', '44100')
            if sample_rate:
                cmd.extend(['-ar', str(sample_rate)])
            
            channels = quality_settings.get('channels', '2')
            if channels:
                cmd.extend(['-ac', str(channels)])
            
            # Metadata and chapters
            if quality_settings.get('preserve_metadata', True):
                cmd.extend(['-map_metadata', '0'])
            
            if quality_settings.get('preserve_chapters', True):
                cmd.extend(['-map_chapters', '0'])
                
            self.logger.debug("Using re-encoding", extra={"codec": codec, "bitrate": bitrate, "output_file": output_file})
        
        # Custom metadata if provided
        if metadata:
            for key, value in metadata.items():
                if value and key in self._get_ffmpeg_metadata_mapping():
                    ffmpeg_key = self._get_ffmpeg_metadata_mapping()[key]
                    # Escape special characters in metadata values
                    escaped_value = str(value).replace('"', '\\"')
                    cmd.extend(['-metadata', f'{ffmpeg_key}={escaped_value}'])
        
        # Output format specification
        if output_ext == '.m4b':
            cmd.extend(['-f', 'mp4'])
        
        # Progress reporting
        cmd.extend(['-progress', 'pipe:2'])
        
        # Output file
        cmd.append(output_file)
        
        return cmd
    
    def convert_with_fallback(
        self,
        input_file: str,
        output_file: str,
        quality_settings: Dict[str, Any],
        activation_bytes: Optional[str] = None,
        voucher_file: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Attempt conversion with multiple fallback methods
        
        Returns: (success, method_used, final_command)
        """
        
        format_type = self.detect_audio_format(input_file)
        methods_to_try = []
        
        # Determine fallback sequence based on format
        if format_type == 'aaxc':
            detected_voucher = voucher_file or self.find_voucher_file(input_file)
            if detected_voucher:
                methods_to_try.append(('voucher_keys', detected_voucher))
            if activation_bytes:
                methods_to_try.append(('activation_bytes_fallback', None))
                
        elif format_type == 'aax':
            if activation_bytes:
                methods_to_try.append(('activation_bytes', None))
                
        elif format_type == 'other':
            methods_to_try.append(('no_drm', None))
        
        if not methods_to_try:
            error_msg = f"No conversion methods available for {input_file}"
            self.logger.error("No conversion methods available", extra={"input_file": input_file})
            return False, 'none', []
        
        # Try each method in sequence
        last_error = ""
        for method, method_voucher in methods_to_try:
            try:
                self.logger.debug("Attempting conversion with method", extra={"input_file": input_file, "method": method, "voucher_file": method_voucher})
                
                cmd = self._build_command_for_method(
                    input_file, output_file, quality_settings,
                    method, activation_bytes, method_voucher, metadata
                )
                
                # Test command (don't actually run here - that's handled by caller)
                self.logger.debug("Built command for method", extra={"method": method, "command_preview": ' '.join(cmd[:8])})
                return True, method, cmd
                
            except Exception as e:
                last_error = str(e)
                self.logger.warning("Method failed during command building", extra={"method": method, "error": str(e)})
                continue
        
        # All methods failed
        error_msg = f"All conversion methods failed. Last error: {last_error}"
        self.logger.error("All conversion methods failed", extra={"input_file": input_file, "last_error": last_error})
        return False, 'failed', []
    
    def _get_ffmpeg_metadata_mapping(self) -> Dict[str, str]:
        """Get mapping of standard metadata keys to FFmpeg metadata keys"""
        return {
            'title': 'title',
            'artist': 'artist',
            'album': 'album',
            'albumartist': 'album_artist',
            'date': 'date',
            'year': 'year',
            'genre': 'genre',
            'comment': 'comment',
            'description': 'description',
            'synopsis': 'synopsis'
        }
    
    def get_audio_duration(self, input_file: str) -> float:
        """Get duration of audio file in seconds"""
        try:
            cmd = [
                'ffprobe', 
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                input_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                return float(duration_str) if duration_str else 0.0
            else:
                self.logger.warning("Could not get duration", extra={"input_file": input_file, "stderr": result.stderr})
                return 0.0
                
        except Exception as e:
            self.logger.exception("Error getting duration", extra={"input_file": input_file, "error": str(e)})
            return 0.0
    
    def parse_progress(self, ffmpeg_line: str, total_duration: float) -> int:
        """Parse FFmpeg progress line and return percentage"""
        try:
            # Look for time=XX:XX:XX.XX pattern in FFmpeg output
            time_match = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', ffmpeg_line)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = int(time_match.group(3))
                centiseconds = int(time_match.group(4))
                
                current_seconds = hours * 3600 + minutes * 60 + seconds + centiseconds / 100
                
                if total_duration > 0:
                    progress = (current_seconds / total_duration) * 100
                    # Keep progress between 20-85% (leaving room for pre/post processing)
                    return max(20, min(85, int(progress * 0.65 + 20)))
            
            return 0
            
        except Exception as e:
            self.logger.debug("Error parsing progress", extra={"error": str(e)})
            return 0
    
    def extract_metadata(self, input_file: str) -> Dict[str, Any]:
        """Extract metadata from input file using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                input_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                probe_data = json.loads(result.stdout)
                
                # Extract format metadata
                format_tags = probe_data.get('format', {}).get('tags', {})
                
                # Normalize tag keys (FFmpeg uses various case formats)
                normalized_tags = {}
                for key, value in format_tags.items():
                    normalized_key = key.lower().replace('-', '_')
                    normalized_tags[normalized_key] = value
                
                return {
                    'duration': float(probe_data.get('format', {}).get('duration', 0)),
                    'bitrate': int(probe_data.get('format', {}).get('bit_rate', 0)),
                    'tags': normalized_tags,
                    'streams': probe_data.get('streams', [])
                }
            else:
                self.logger.warning("Could not extract metadata", extra={"input_file": input_file, "stderr": result.stderr})
                return {}
                
        except Exception as e:
            self.logger.exception("Error extracting metadata", extra={"input_file": input_file, "error": str(e)})
            return {}
    
    def validate_output_file(self, output_file: str) -> Dict[str, Any]:
        """Validate that output file was created successfully"""
        try:
            if not os.path.exists(output_file):
                return {
                    'success': False,
                    'error': 'Output file does not exist'
                }
            
            # Check file size
            file_size = os.path.getsize(output_file)
            if file_size == 0:
                return {
                    'success': False,
                    'error': 'Output file is empty'
                }
            
            # Quick format validation
            metadata = self.extract_metadata(output_file)
            if not metadata:
                return {
                    'success': False,
                    'error': 'Output file appears to be corrupted (no metadata)'
                }
            
            return {
                'success': True,
                'file_size': file_size,
                'duration': metadata.get('duration', 0),
                'format_valid': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Output validation failed: {str(e)}'
            }