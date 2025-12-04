"""
Audiobook Conversion Service - AuralArchive

Provides FFmpeg-based conversion from various audiobook formats (AAX, AAXC, MP3) to M4B format.
Supports configurable quality settings managed through the config service.

Features:
- Sequential processing (one book at a time)
- Metadata preservation and chapter support
- Activation bytes integration for DRM removal
- Quality settings configurable via settings menu
- Shared temp folder management
- Progress tracking with SocketIO

Author: AuralArchive Development Team
Created: September 28, 2025
"""

import os
import subprocess
import tempfile
import shutil
import logging
import threading
import time
from typing import Dict, List, Optional, Any, Tuple, Callable
from datetime import datetime
from pathlib import Path

from services.service_manager import service_manager
from utils.logger import get_module_logger

class ConversionService:
    """Main service for audiobook format conversion using FFmpeg"""
    
    _instance: Optional['ConversionService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.logger = get_module_logger("ConversionService")
                    self.config_service = None
                    self.audible_library_service = None
                    self.helpers = None
                    
                    # Initialize helper modules
                    self._initialize_helpers()
                    
                    self.logger.info("ConversionService initialized successfully")
                    ConversionService._initialized = True
    
    def _initialize_helpers(self):
        """Initialize helper modules"""
        try:
            from .ffmpeg_handler import FFmpegHandler
            from .format_detector import FormatDetector
            from .metadata_processor import MetadataProcessor
            from .quality_manager import QualityManager
            
            self.helpers = {
                'ffmpeg': FFmpegHandler(),
                'format_detector': FormatDetector(),
                'metadata_processor': MetadataProcessor(),
                'quality_manager': QualityManager()
            }
            
            self.logger.debug("Helper modules initialized")
            
        except ImportError as e:
            self.logger.error(f"Failed to initialize helper modules: {e}")
            self.helpers = {}
    
    def _get_config_service(self):
        """Get config service instance"""
        if self.config_service is None:
            self.config_service = service_manager.get_config_service()
        return self.config_service
    
    def _get_audible_library_service(self):
        """Get audible library service instance"""
        if self.audible_library_service is None:
            try:
                from services.audible.audible_library_service.audible_library_service import AudibleLibraryService
                self.audible_library_service = AudibleLibraryService()
            except ImportError as e:
                self.logger.error(f"Failed to import audible library service: {e}")
        return self.audible_library_service
    
    def _get_shared_temp_dir(self) -> str:
        """Get shared temporary directory from config"""
        try:
            config = self._get_config_service()
            temp_dir = config.get('conversion.shared_temp_dir', '/tmp/aural_archive_conversion')
            
            # Ensure directory exists
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            
            return temp_dir
            
        except Exception as e:
            self.logger.error(f"Failed to get shared temp dir: {e}")
            # Fallback to system temp
            return tempfile.gettempdir()
    
    def get_quality_settings(self) -> Dict[str, Any]:
        """Get current quality settings from config"""
        try:
            config = self._get_config_service()
            
            # Default quality settings based on m4b-tool best practices
            default_settings = {
                'codec': 'aac',  # or 'libfdk_aac' if available for higher quality
                'bitrate': '64k',  # Good quality for audiobooks (32k-128k range)
                'sample_rate': '22050',  # Standard for audiobooks (22050 or 44100)
                'channels': '1',  # Mono for most audiobooks (1 or 2)
                'profile': '',  # aac_he for very low bitrates (<=32k)
                'format': 'm4b',  # Target format
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True
            }
            
            # Get user-configured settings
            user_settings = {
                'codec': config.get('conversion.quality.codec', default_settings['codec']),
                'bitrate': config.get('conversion.quality.bitrate', default_settings['bitrate']),
                'sample_rate': config.get('conversion.quality.sample_rate', default_settings['sample_rate']),
                'channels': config.get('conversion.quality.channels', default_settings['channels']),
                'profile': config.get('conversion.quality.profile', default_settings['profile']),
                'format': config.get('conversion.quality.format', default_settings['format']),
                'preserve_chapters': config.get_config_bool('conversion.quality', 'preserve_chapters', default_settings['preserve_chapters']),
                'embed_cover': config.get_config_bool('conversion.quality', 'embed_cover', default_settings['embed_cover']),
                'preserve_metadata': config.get_config_bool('conversion.quality', 'preserve_metadata', default_settings['preserve_metadata'])
            }
            
            return user_settings
            
        except Exception as e:
            self.logger.error(f"Failed to get quality settings: {e}")
            return default_settings
    
    def update_quality_settings(self, settings: Dict[str, Any]) -> bool:
        """Update quality settings in config"""
        try:
            config = self._get_config_service()
            
            for key, value in settings.items():
                config_key = f'conversion.quality.{key}'
                if isinstance(value, bool):
                    config.set(config_key, str(value).lower())
                else:
                    config.set(config_key, str(value))
            
            self.logger.info(f"Updated quality settings: {settings}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update quality settings: {e}")
            return False
    
    def convert_audiobook(
        self, 
        input_file: str, 
        output_file: str = None,
        progress_callback: Callable[[str, int], None] = None,
        metadata: Dict[str, Any] = None,
        voucher_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert audiobook file to M4B format
        
        Args:
            input_file: Path to input audiobook file
            output_file: Optional output file path (auto-generated if not provided)
            progress_callback: Optional callback for progress updates
            metadata: Optional metadata to embed
            voucher_file: Optional path to AAXC voucher JSON (required for new Audible downloads)
            
        Returns:
            Dict with conversion results and output file path
        """
        try:
            self.logger.info("Conversion started", extra={'input_file': input_file})
            
            if not os.path.exists(input_file):
                return {
                    'success': False,
                    'error': 'Input file does not exist',
                    'input_file': input_file
                }

            voucher_path = os.path.abspath(voucher_file) if voucher_file else None
            if voucher_path and not os.path.exists(voucher_path):
                return {
                    'success': False,
                    'error': f'Voucher file not found: {voucher_path}',
                    'input_file': input_file
                }
            
            # Step 1: Detect input format
            if progress_callback:
                progress_callback("Detecting input format...", 5)
            
            input_format = self.helpers['format_detector'].detect_format(input_file)
            self.logger.debug(f"Detected format: {input_format}")
            
            # Step 2: Get quality settings
            quality_settings = self.get_quality_settings()
            
            # Step 3: Get activation bytes if needed for AAX/AAXC files
            activation_bytes = None
            if input_format.lower() in ['aax', 'aaxc']:
                if progress_callback:
                    progress_callback("Getting activation bytes...", 10)
                
                activation_result = self._get_activation_bytes()
                if activation_result['success']:
                    activation_bytes = activation_result.get('activation_bytes')
                else:
                    return {
                        'success': False,
                        'error': f'Failed to get activation bytes: {activation_result.get("error")}',
                        'input_file': input_file
                    }
            
            # Step 4: Setup temp and output paths
            if output_file is None:
                output_file = self._generate_output_filename(input_file)
            
            temp_dir = self._get_shared_temp_dir()
            temp_output = os.path.join(temp_dir, f"temp_{int(time.time())}_{os.path.basename(output_file)}")
            
            # Step 5: Build FFmpeg command
            if progress_callback:
                progress_callback("Preparing conversion...", 15)
            
            ffmpeg_cmd = self.helpers['ffmpeg'].build_conversion_command(
                input_file=input_file,
                output_file=temp_output,
                quality_settings=quality_settings,
                activation_bytes=activation_bytes,
                metadata=metadata,
                voucher_file=voucher_path
            )
            
            # Step 6: Execute conversion
            if progress_callback:
                progress_callback("Converting audiobook...", 20)
            
            conversion_result = self._execute_conversion(
                ffmpeg_cmd, 
                input_file, 
                temp_output,
                progress_callback
            )
            
            if not conversion_result['success']:
                return conversion_result
            
            # Step 7: Post-process metadata and chapters
            if progress_callback:
                progress_callback("Processing metadata...", 90)
            
            metadata_result = self.helpers['metadata_processor'].process_metadata(
                temp_output,
                quality_settings,
                metadata
            )
            
            # Step 8: Move to final destination
            if progress_callback:
                progress_callback("Finalizing...", 95)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Move temp file to final location
            shutil.move(temp_output, output_file)
            
            if progress_callback:
                progress_callback("Conversion complete!", 100)
            
            self.logger.info("Conversion finished", extra={'input_file': input_file, 'output_file': output_file})
            
            return {
                'success': True,
                'input_file': input_file,
                'output_file': output_file,
                'format': input_format,
                'quality_settings': quality_settings,
                'metadata_processed': metadata_result.get('success', False),
                'file_size': os.path.getsize(output_file)
            }
            
        except Exception as e:
            self.logger.error(f"Conversion failed for {input_file}: {e}")
            
            # Clean up temp file if it exists
            if 'temp_output' in locals() and os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except:
                    pass
            
            return {
                'success': False,
                'error': str(e),
                'input_file': input_file
            }
    
    def _get_activation_bytes(self) -> Dict[str, Any]:
        """Get activation bytes from audible library service"""
        try:
            audible_service = self._get_audible_library_service()
            if audible_service:
                return audible_service.get_activation_bytes()
            else:
                return {
                    'success': False,
                    'error': 'Audible library service not available'
                }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to get activation bytes: {str(e)}'
            }
    
    def _generate_output_filename(self, input_file: str) -> str:
        """Generate output filename based on input file"""
        input_path = Path(input_file)
        output_name = input_path.stem + '.m4b'
        return os.path.join(input_path.parent, output_name)
    
    def _execute_conversion(
        self, 
        ffmpeg_cmd: List[str], 
        input_file: str, 
        output_file: str,
        progress_callback: Callable[[str, int], None] = None
    ) -> Dict[str, Any]:
        """Execute FFmpeg conversion command with progress tracking"""
        try:
            self.logger.debug(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")
            
            # Get input duration for progress calculation
            duration = self.helpers['ffmpeg'].get_audio_duration(input_file)
            
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Track progress by monitoring FFmpeg stderr output
            last_progress = 20
            while process.poll() is None:
                if process.stderr:
                    line = process.stderr.readline()
                    if line and duration > 0:
                        # Parse FFmpeg progress (time=XX:XX:XX.XX format)
                        progress = self.helpers['ffmpeg'].parse_progress(line, duration)
                        if progress > last_progress and progress <= 85:
                            last_progress = progress
                            if progress_callback:
                                progress_callback(f"Converting... {progress}%", progress)
                
                time.sleep(0.5)
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                if os.path.exists(output_file):
                    return {
                        'success': True,
                        'output_file': output_file
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Conversion completed but output file not found'
                    }
            else:
                return {
                    'success': False,
                    'error': f'FFmpeg conversion failed: {stderr}',
                    'stdout': stdout,
                    'stderr': stderr
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': f'Conversion execution failed: {str(e)}'
            }
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported input formats"""
        return ['aax', 'aaxc', 'mp3', 'm4a', 'm4b', 'flac', 'ogg', 'wav']
    
    def validate_ffmpeg_installation(self) -> Dict[str, Any]:
        """Validate FFmpeg installation and available codecs"""
        try:
            return self.helpers['ffmpeg'].validate_installation()
        except Exception as e:
            return {
                'success': False,
                'error': f'FFmpeg validation failed: {str(e)}'
            }
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        try:
            ffmpeg_status = self.validate_ffmpeg_installation()
            temp_dir = self._get_shared_temp_dir()
            quality_settings = self.get_quality_settings()
            
            return {
                'service_name': 'ConversionService',
                'initialized': self._initialized,
                'ffmpeg_available': ffmpeg_status.get('success', False),
                'ffmpeg_details': ffmpeg_status,
                'shared_temp_dir': temp_dir,
                'temp_dir_writable': os.access(temp_dir, os.W_OK),
                'supported_formats': self.get_supported_formats(),
                'quality_settings': quality_settings,
                'helpers_loaded': len(self.helpers) > 0,
                'activation_bytes_available': self._check_activation_bytes_availability()
            }
            
        except Exception as e:
            return {
                'service_name': 'ConversionService',
                'error': str(e)
            }
    
    def _check_activation_bytes_availability(self) -> bool:
        """Check if activation bytes are available"""
        try:
            result = self._get_activation_bytes()
            return result.get('success', False)
        except:
            return False
    
    def clean_temp_directory(self) -> Dict[str, Any]:
        """Clean temporary files from shared temp directory"""
        try:
            temp_dir = self._get_shared_temp_dir()
            cleaned_files = []
            
            for file_name in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file_name)
                if os.path.isfile(file_path) and file_name.startswith('temp_'):
                    try:
                        os.remove(file_path)
                        cleaned_files.append(file_name)
                    except Exception as e:
                        self.logger.warning(f"Could not remove temp file {file_name}: {e}")
            
            return {
                'success': True,
                'cleaned_files': cleaned_files,
                'count': len(cleaned_files)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# Convenience function for service manager
def get_conversion_service() -> ConversionService:
    """Get or create ConversionService instance"""
    return ConversionService()