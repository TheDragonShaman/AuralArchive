"""
Module Name: validation.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Validation logic for import operations, including filesystem checks,
    supported format validation, and audio quality detection via ffprobe
    when available.

Location:
    /services/import_service/validation.py

"""

import os
from typing import Dict, Tuple
from pathlib import Path
import subprocess

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Import.Validator")


class ImportValidator:
    """
    Validates import operations and file integrity.
    
    Features:
    - Import request validation
    - File existence and accessibility checks
    - Audio file quality detection
    - Metadata validation
    """
    
    # Supported audio formats
    SUPPORTED_FORMATS = {
        'm4b', 'm4a', 'mp3', 'mp4', 'flac', 'ogg', 'opus', 'aac'
    }
    
    def __init__(self, *, logger=None):
        self.logger = logger or _LOGGER
    
    def validate_import_request(self, source_file_path: str, book_data: Dict) -> Tuple[bool, str]:
        """
        Validate an import request.
        
        Args:
            source_file_path: Path to source file
            book_data: Book metadata dictionary
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        try:
            # Check source file exists
            if not os.path.exists(source_file_path):
                return False, f"Source file does not exist: {source_file_path}"
            
            # Check it's a file (not directory)
            if not os.path.isfile(source_file_path):
                return False, f"Source is not a file: {source_file_path}"
            
            # Check file is readable
            if not os.access(source_file_path, os.R_OK):
                return False, f"Source file is not readable: {source_file_path}"
            
            # Check file extension is supported
            file_ext = Path(source_file_path).suffix.lstrip('.').lower()
            if file_ext not in self.SUPPORTED_FORMATS:
                return False, f"Unsupported file format: {file_ext}"
            
            # Check file size (must be > 0)
            file_size = os.path.getsize(source_file_path)
            if file_size == 0:
                return False, "Source file is empty (0 bytes)"
            
            # Validate book_data has minimum required fields
            if not book_data:
                return False, "Book metadata is required"
            
            # Check for required fields (with flexible field name matching)
            # Title is required
            if not (book_data.get('Title') or book_data.get('title')):
                return False, "Book metadata missing: Title"
            
            # Author is recommended but not strictly required (can be "Unknown Author")
            if not (book_data.get('AuthorName') or book_data.get('Author') or book_data.get('author')):
                self.logger.warning("Book metadata missing Author - will use 'Unknown Author'")
            
            # Check ASIN is present (recommended but not strictly required)
            if not (book_data.get('ASIN') or book_data.get('asin')):
                self.logger.warning("Book metadata missing ASIN - import tracking may be limited")
            
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Error validating import request: {e}")
            return False, f"Validation error: {str(e)}"
    
    def verify_file_exists(self, file_path: str) -> Tuple[bool, str]:
        """
        Verify that a file exists and is accessible.
        
        Args:
            file_path: Path to file
            
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            if not os.path.isfile(file_path):
                return False, "Path is not a file"
            
            if not os.access(file_path, os.R_OK):
                return False, "File is not readable"
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return False, "File is empty (0 bytes)"
            
            return True, "File is valid"
            
        except Exception as e:
            return False, f"Verification error: {str(e)}"
    
    def detect_file_quality(self, file_path: str) -> str:
        """
        Detect audio file quality (bitrate, sample rate, etc.).
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Quality descriptor string (e.g., "M4B 128kbps Stereo")
        """
        try:
            # Try using ffprobe to get audio info
            file_ext = Path(file_path).suffix.lstrip('.').upper()
            
            try:
                # Run ffprobe to get audio stream info
                result = subprocess.run(
                    [
                        'ffprobe',
                        '-v', 'quiet',
                        '-select_streams', 'a:0',
                        '-show_entries', 'stream=codec_name,bit_rate,sample_rate,channels',
                        '-of', 'default=noprint_wrappers=1',
                        file_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    # Parse ffprobe output
                    output = result.stdout
                    codec = self._extract_value(output, 'codec_name')
                    bitrate = self._extract_value(output, 'bit_rate')
                    channels = self._extract_value(output, 'channels')
                    
                    # Build quality string
                    quality_parts = [file_ext]
                    
                    # Add bitrate in kbps
                    if bitrate:
                        try:
                            bitrate_kbps = int(bitrate) // 1000
                            quality_parts.append(f"{bitrate_kbps}kbps")
                        except:
                            pass
                    
                    # Add channel info
                    if channels:
                        try:
                            ch = int(channels)
                            quality_parts.append('Stereo' if ch == 2 else f'{ch}ch')
                        except:
                            pass
                    
                    return ' '.join(quality_parts)
                
            except FileNotFoundError:
                self.logger.debug("ffprobe not found, using basic quality detection")
            except subprocess.TimeoutExpired:
                self.logger.warning(f"ffprobe timeout for {file_path}")
            except Exception as e:
                self.logger.debug(f"ffprobe failed: {e}")
            
            # Fallback: just use file extension and size
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
            
            return f"{file_ext} ({size_mb:.1f} MB)"
            
        except Exception as e:
            self.logger.error(f"Error detecting file quality: {e}")
            return "Unknown Quality"
    
    def _extract_value(self, text: str, key: str) -> str:
        """
        Extract a value from ffprobe output.
        
        Args:
            text: ffprobe output text
            key: Key to extract (e.g., 'bit_rate')
            
        Returns:
            Value string or empty string if not found
        """
        for line in text.split('\n'):
            if line.startswith(f"{key}="):
                return line.split('=', 1)[1].strip()
        return ""
    
    def validate_audiobook_metadata(self, book_data: Dict) -> Tuple[bool, list]:
        """
        Validate audiobook metadata completeness.
        
        Args:
            book_data: Book metadata dictionary
            
        Returns:
            Tuple of (is_valid: bool, missing_fields: list)
        """
        recommended_fields = [
            'Title', 'Author', 'ASIN', 'Series', 'Narrator',
            'Release Date', 'Runtime', 'Publisher'
        ]
        
        missing = []
        for field in recommended_fields:
            value = book_data.get(field) or book_data.get(field.lower().replace(' ', '_'))
            if not value or value == 'N/A' or value == 'Unknown':
                missing.append(field)
        
        # At minimum, must have Title and Author
        critical_missing = [f for f in missing if f in ['Title', 'Author']]
        is_valid = len(critical_missing) == 0
        
        return is_valid, missing
