"""
Format Detector - Conversion Service Helper

Detects audiobook file formats and validates input files for conversion.

Features:
- File extension and magic number detection
- Format validation and compatibility checking
- Support for AAX, AAXC, MP3, M4A, M4B, FLAC, OGG, WAV

Author: AuralArchive Development Team
Created: September 28, 2025
"""

import os
import mimetypes
from typing import Dict, Any, Optional
from pathlib import Path

from utils.logger import get_module_logger


class FormatDetector:
    """Detector for audiobook file formats"""
    
    def __init__(self):
        self.logger = get_module_logger("FormatDetector")
        
        # Supported format mappings
        self.format_extensions = {
            '.aax': 'aax',
            '.aaxc': 'aaxc', 
            '.mp3': 'mp3',
            '.m4a': 'm4a',
            '.m4b': 'm4b',
            '.flac': 'flac',
            '.ogg': 'ogg',
            '.oga': 'ogg',
            '.wav': 'wav',
            '.wave': 'wav'
        }
        
        # MIME type mappings
        self.format_mimes = {
            'audio/mp4': 'm4a',  # Could be m4a or m4b
            'audio/mpeg': 'mp3',
            'audio/flac': 'flac',
            'audio/ogg': 'ogg',
            'audio/wav': 'wav',
            'audio/x-wav': 'wav'
        }
        
        # Magic number signatures for binary detection
        self.magic_signatures = {
            b'ID3': 'mp3',
            b'\xff\xfb': 'mp3',  # MP3 frame header
            b'\xff\xf3': 'mp3',  # MP3 frame header
            b'\xff\xf2': 'mp3',  # MP3 frame header
            b'ftyp': 'm4a',      # MP4 container (at offset 4)
            b'fLaC': 'flac',     # FLAC signature
            b'OggS': 'ogg',      # Ogg container
            b'RIFF': 'wav'       # WAV/RIFF header
        }
    
    def detect_format(self, file_path: str) -> str:
        """
        Detect audio file format using multiple methods
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Detected format string (e.g., 'mp3', 'aax', 'm4b')
        """
        try:
            if not os.path.exists(file_path):
                self.logger.error(f"File does not exist: {file_path}")
                return 'unknown'
            
            file_path = Path(file_path)
            
            # Method 1: Check file extension
            extension_format = self._detect_by_extension(file_path)
            if extension_format != 'unknown':
                self.logger.debug(f"Detected format by extension: {extension_format}")
                
                # For M4A files, check if they're actually M4B
                if extension_format == 'm4a':
                    refined_format = self._refine_m4_format(file_path)
                    if refined_format:
                        return refined_format
                
                return extension_format
            
            # Method 2: Check MIME type
            mime_format = self._detect_by_mime(file_path)
            if mime_format != 'unknown':
                self.logger.debug(f"Detected format by MIME type: {mime_format}")
                return mime_format
            
            # Method 3: Check magic numbers
            magic_format = self._detect_by_magic(file_path)
            if magic_format != 'unknown':
                self.logger.debug(f"Detected format by magic number: {magic_format}")
                return magic_format
            
            self.logger.warning(f"Could not detect format for: {file_path}")
            return 'unknown'
            
        except Exception as e:
            self.logger.error(f"Error detecting format for {file_path}: {e}")
            return 'unknown'
    
    def _detect_by_extension(self, file_path: Path) -> str:
        """Detect format by file extension"""
        extension = file_path.suffix.lower()
        return self.format_extensions.get(extension, 'unknown')
    
    def _detect_by_mime(self, file_path: Path) -> str:
        """Detect format by MIME type"""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            return self.format_mimes.get(mime_type, 'unknown')
        return 'unknown'
    
    def _detect_by_magic(self, file_path: Path) -> str:
        """Detect format by magic number/file signature"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)  # Read first 32 bytes
                
                for signature, format_type in self.magic_signatures.items():
                    if header.startswith(signature):
                        return format_type
                    
                    # Check for MP4/M4A signature at offset 4
                    if signature == b'ftyp' and len(header) > 8 and header[4:8] == signature:
                        return self._determine_mp4_subtype(f)
                
                return 'unknown'
                
        except Exception as e:
            self.logger.error(f"Error reading magic numbers from {file_path}: {e}")
            return 'unknown'
    
    def _determine_mp4_subtype(self, file_handle) -> str:
        """Determine if MP4 file is M4A, M4B, or AAX based on content"""
        try:
            file_handle.seek(0)
            header = file_handle.read(64)
            
            # Look for specific brand indicators
            header_str = header.decode('utf-8', errors='ignore').lower()
            
            if 'audible' in header_str or 'aax' in header_str:
                return 'aax'
            elif 'm4b' in header_str or 'audiobook' in header_str:
                return 'm4b'
            else:
                return 'm4a'  # Default to M4A
                
        except Exception:
            return 'm4a'  # Default fallback
    
    def _refine_m4_format(self, file_path: Path) -> Optional[str]:
        """Refine M4A detection to distinguish M4A from M4B"""
        try:
            # Check for audiobook-specific metadata or structure
            with open(file_path, 'rb') as f:
                # Read more of the file to look for audiobook indicators
                chunk = f.read(1024)
                content = chunk.decode('utf-8', errors='ignore').lower()
                
                # Look for audiobook-specific indicators
                if any(indicator in content for indicator in ['audiobook', 'chapters', 'm4b']):
                    return 'm4b'
                    
            return 'm4a'
            
        except Exception as e:
            self.logger.debug(f"Could not refine M4 format detection: {e}")
            return 'm4a'  # Default to M4A
    
    def validate_input_file(self, file_path: str) -> Dict[str, Any]:
        """
        Validate input file for conversion compatibility
        
        Args:
            file_path: Path to the input file
            
        Returns:
            Dict with validation results
        """
        try:
            if not os.path.exists(file_path):
                return {
                    'valid': False,
                    'error': 'File does not exist'
                }
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return {
                    'valid': False,
                    'error': 'File is empty'
                }
            
            # Detect format
            detected_format = self.detect_format(file_path)
            if detected_format == 'unknown':
                return {
                    'valid': False,
                    'error': 'Unsupported or unrecognized file format'
                }
            
            # Check if format is supported for conversion
            supported_formats = ['aax', 'aaxc', 'mp3', 'm4a', 'm4b', 'flac', 'ogg', 'wav']
            if detected_format not in supported_formats:
                return {
                    'valid': False,
                    'error': f'Format {detected_format} is not supported for conversion'
                }
            
            # Additional format-specific validation
            format_validation = self._validate_format_specific(file_path, detected_format)
            
            return {
                'valid': True,
                'format': detected_format,
                'file_size': file_size,
                'file_size_mb': round(file_size / (1024 * 1024), 2),
                'format_validation': format_validation
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }
    
    def _validate_format_specific(self, file_path: str, format_type: str) -> Dict[str, Any]:
        """Perform format-specific validation"""
        validation = {'checks_passed': [], 'warnings': [], 'errors': []}
        
        try:
            if format_type in ['aax', 'aaxc']:
                validation['checks_passed'].append('DRM-protected audiobook format detected')
                validation['warnings'].append('Requires activation bytes for conversion')
            
            elif format_type == 'mp3':
                # Basic MP3 validation
                with open(file_path, 'rb') as f:
                    header = f.read(10)
                    if header.startswith(b'ID3'):
                        validation['checks_passed'].append('ID3 metadata detected')
                    elif header.startswith((b'\xff\xfb', b'\xff\xf3', b'\xff\xf2')):
                        validation['checks_passed'].append('Valid MP3 frame header detected')
                    else:
                        validation['warnings'].append('No standard MP3 header detected')
            
            elif format_type in ['m4a', 'm4b']:
                # Basic MP4 container validation
                with open(file_path, 'rb') as f:
                    f.seek(4)
                    ftype = f.read(4)
                    if ftype == b'ftyp':
                        validation['checks_passed'].append('Valid MP4 container detected')
                    else:
                        validation['errors'].append('Invalid MP4 container structure')
            
            elif format_type == 'flac':
                # FLAC validation
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if header == b'fLaC':
                        validation['checks_passed'].append('Valid FLAC signature detected')
                    else:
                        validation['errors'].append('Invalid FLAC signature')
            
            # Common size checks
            file_size = os.path.getsize(file_path)
            if file_size < 1024:  # Less than 1KB
                validation['warnings'].append('File is very small, may be corrupted')
            elif file_size > 2 * 1024 * 1024 * 1024:  # Larger than 2GB
                validation['warnings'].append('File is very large, conversion may take significant time')
            
            return validation
            
        except Exception as e:
            validation['errors'].append(f'Format validation error: {str(e)}')
            return validation
    
    def get_supported_formats(self) -> Dict[str, Any]:
        """Get information about supported formats"""
        return {
            'input_formats': {
                'aax': {
                    'description': 'Audible AAX (DRM-protected)',
                    'requires_activation_bytes': True,
                    'common_extensions': ['.aax']
                },
                'aaxc': {
                    'description': 'Audible AAXC (DRM-protected)',
                    'requires_activation_bytes': True,
                    'common_extensions': ['.aaxc']
                },
                'mp3': {
                    'description': 'MP3 Audio',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.mp3']
                },
                'm4a': {
                    'description': 'MPEG-4 Audio',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.m4a']
                },
                'm4b': {
                    'description': 'MPEG-4 Audiobook',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.m4b']
                },
                'flac': {
                    'description': 'FLAC Lossless Audio',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.flac']
                },
                'ogg': {
                    'description': 'Ogg Vorbis Audio',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.ogg', '.oga']
                },
                'wav': {
                    'description': 'WAV Audio',
                    'requires_activation_bytes': False,
                    'common_extensions': ['.wav', '.wave']
                }
            },
            'output_format': {
                'm4b': {
                    'description': 'M4B Audiobook format (optimal for audiobooks)',
                    'supports_chapters': True,
                    'supports_metadata': True,
                    'compatible_players': ['AudiobookShelf', 'Apple Books', 'Smart AudioBook Player']
                }
            }
        }