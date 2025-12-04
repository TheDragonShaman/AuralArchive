"""
Audible Format Converter - AuralArchive

Handles format conversion utilities for Audible audiobooks, including
AAX/AAXC to open formats like M4B and MP3. Provides conversion progress
tracking and quality management.

Author: AuralArchive Development Team
Created: September 16, 2025
"""

import os
import subprocess
import tempfile
from typing import Dict, List, Any, Optional, Callable
import logging
from pathlib import Path
import re


class AudibleFormatConverter:
    """
    Handles conversion of Audible audiobook formats to open formats.
    
    This class provides methods for converting AAX/AAXC files to M4B, MP3,
    and other open formats while preserving metadata and managing quality
    settings.
    """
    
    def __init__(self, logger=None):
        """
        Initialize the Format Converter.
        
        Args:
            logger: Logger instance for conversion operations
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Supported input and output formats
        self.supported_input_formats = ['.aax', '.aaxc']
        self.supported_output_formats = ['.m4b', '.mp3', '.m4a', '.flac']
        
        # Quality presets
        self.quality_presets = {
            'high': {
                'm4b': ['-c:a', 'aac', '-b:a', '128k'],
                'mp3': ['-c:a', 'libmp3lame', '-b:a', '128k'],
                'm4a': ['-c:a', 'aac', '-b:a', '128k'],
                'flac': ['-c:a', 'flac']
            },
            'medium': {
                'm4b': ['-c:a', 'aac', '-b:a', '96k'],
                'mp3': ['-c:a', 'libmp3lame', '-b:a', '96k'],
                'm4a': ['-c:a', 'aac', '-b:a', '96k'],
                'flac': ['-c:a', 'flac']
            },
            'low': {
                'm4b': ['-c:a', 'aac', '-b:a', '64k'],
                'mp3': ['-c:a', 'libmp3lame', '-b:a', '64k'],
                'm4a': ['-c:a', 'aac', '-b:a', '64k'],
                'flac': ['-c:a', 'flac']
            }
        }
        
        self.logger.debug("AudibleFormatConverter initialized")
    
    def check_conversion_requirements(self) -> Dict[str, Any]:
        """
        Check if all required tools for conversion are available.
        
        Returns:
            Dict containing availability status of conversion tools
        """
        try:
            requirements = {
                'ffmpeg': False,
                'audible_api': False,
                'auth_file': False,
                'conversion_capable': False
            }
            
            # Check FFmpeg availability
            try:
                result = subprocess.run(
                    ['ffmpeg', '-version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    requirements['ffmpeg'] = True
                    self.logger.debug("FFmpeg is available")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.logger.warning("FFmpeg not found or not working")
            
            # Check Python audible package availability
            try:
                import audible
                requirements['audible_api'] = True
                self.logger.debug("Python audible package is available")
            except ImportError:
                self.logger.warning("Python audible package not installed or not available")

            # Check for authentication token file
            auth_file = Path(__file__).resolve().parents[3] / 'auth' / 'audible_auth.json'
            if auth_file.exists():
                requirements['auth_file'] = True
            else:
                self.logger.debug("Audible auth file not found at %s", auth_file)
            
            # Overall conversion capability
            requirements['conversion_capable'] = (
                requirements['ffmpeg'] and requirements['audible_api'] and requirements['auth_file']
            )
            
            return {
                'success': True,
                'requirements': requirements,
                'message': 'Conversion capability check completed'
            }
            
        except Exception as e:
            self.logger.error(f"Error checking conversion requirements: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Error checking conversion requirements: {str(e)}'
            }
    
    def get_supported_formats(self) -> Dict[str, Any]:
        """
        Get information about supported input and output formats.
        
        Returns:
            Dict containing format support information
        """
        return {
            'input_formats': {
                'aax': {
                    'description': 'Audible AAX format (DRM-protected)',
                    'extensions': ['.aax'],
                    'requires_activation_bytes': True
                },
                'aaxc': {
                    'description': 'Audible AAXC format (newer DRM-protected)',
                    'extensions': ['.aaxc'],
                    'requires_voucher': True
                }
            },
            'output_formats': {
                'm4b': {
                    'description': 'M4B audiobook format (chapters preserved)',
                    'extensions': ['.m4b'],
                    'recommended': True,
                    'supports_chapters': True
                },
                'mp3': {
                    'description': 'MP3 audio format (widely compatible)',
                    'extensions': ['.mp3'],
                    'recommended': False,
                    'supports_chapters': False
                },
                'm4a': {
                    'description': 'M4A audio format (Apple audio)',
                    'extensions': ['.m4a'],
                    'recommended': False,
                    'supports_chapters': True
                },
                'flac': {
                    'description': 'FLAC lossless audio format',
                    'extensions': ['.flac'],
                    'recommended': False,
                    'supports_chapters': False
                }
            },
            'quality_presets': list(self.quality_presets.keys())
        }
    
    def validate_conversion_request(self, input_file: str, output_format: str, 
                                  quality: str = 'high') -> Dict[str, Any]:
        """
        Validate a conversion request before processing.
        
        Args:
            input_file: Path to input file
            output_format: Desired output format
            quality: Quality preset to use
            
        Returns:
            Dict containing validation results
        """
        try:
            issues = []
            warnings = []
            
            # Check input file
            if not os.path.exists(input_file):
                issues.append(f"Input file not found: {input_file}")
            else:
                input_ext = Path(input_file).suffix.lower()
                if input_ext not in self.supported_input_formats:
                    issues.append(f"Unsupported input format: {input_ext}")
            
            # Check output format
            if output_format not in [fmt.lstrip('.') for fmt in self.supported_output_formats]:
                issues.append(f"Unsupported output format: {output_format}")
            
            # Check quality preset
            if quality not in self.quality_presets:
                issues.append(f"Unknown quality preset: {quality}")
            
            # Check conversion capabilities
            req_check = self.check_conversion_requirements()
            if not req_check.get('requirements', {}).get('conversion_capable'):
                issues.append("Conversion tools not available (FFmpeg, Python audible package, and auth token required)")
            
            # Warnings for specific combinations
            if output_format == 'mp3' and input_ext in ['.aax', '.aaxc']:
                warnings.append("Converting to MP3 will lose chapter information")
            
            validation_result = {
                'valid': len(issues) == 0,
                'issues': issues,
                'warnings': warnings,
                'input_file': input_file,
                'output_format': output_format,
                'quality': quality
            }
            
            if validation_result['valid']:
                self.logger.debug(f"Conversion request validated: {input_file} -> {output_format}")
            else:
                self.logger.warning(f"Conversion request validation failed: {issues}")
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Error validating conversion request: {str(e)}")
            return {
                'valid': False,
                'issues': [f"Validation error: {str(e)}"],
                'warnings': [],
                'error': str(e)
            }
    
    def prepare_conversion_command(self, input_file: str, output_file: str, 
                                 output_format: str, quality: str = 'high',
                                 additional_options: List[str] = None) -> List[str]:
        """
        Prepare the FFmpeg command for conversion.
        
        Args:
            input_file: Path to input file
            output_file: Path to output file
            output_format: Output format
            quality: Quality preset
            additional_options: Additional FFmpeg options
            
        Returns:
            List of command arguments for FFmpeg
        """
        try:
            cmd = ['ffmpeg', '-i', input_file]
            
            # Add quality settings
            quality_settings = self.quality_presets.get(quality, {})
            format_settings = quality_settings.get(output_format, [])
            cmd.extend(format_settings)
            
            # Add format-specific options
            if output_format == 'm4b':
                # Preserve chapters and metadata for M4B
                cmd.extend(['-map_chapters', '0'])
                cmd.extend(['-map_metadata', '0'])
            elif output_format == 'mp3':
                # Add MP3-specific options
                cmd.extend(['-map_metadata', '0'])
                cmd.extend(['-id3v2_version', '3'])
            
            # Add additional options if provided
            if additional_options:
                cmd.extend(additional_options)
            
            # Add output file and overwrite option
            cmd.extend(['-y', output_file])
            
            self.logger.debug(f"Prepared conversion command: {' '.join(cmd[:5])}...")
            return cmd
            
        except Exception as e:
            self.logger.error(f"Error preparing conversion command: {str(e)}")
            return []
    
    def convert_file(self, input_file: str, output_file: str, output_format: str,
                    quality: str = 'high', progress_callback: Callable = None) -> Dict[str, Any]:
        """
        Convert an audiobook file from one format to another.
        
        Args:
            input_file: Path to input file
            output_file: Path to output file
            output_format: Desired output format
            quality: Quality preset to use
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict containing conversion results
        """
        try:
            # Validate the conversion request
            validation = self.validate_conversion_request(input_file, output_format, quality)
            if not validation['valid']:
                return {
                    'success': False,
                    'errors': validation['issues'],
                    'warnings': validation.get('warnings', [])
                }
            
            # Prepare the conversion command
            cmd = self.prepare_conversion_command(input_file, output_file, output_format, quality)
            if not cmd:
                return {
                    'success': False,
                    'error': 'Failed to prepare conversion command'
                }
            
            self.logger.info(f"Starting conversion: {input_file} -> {output_file}")
            
            # Execute the conversion
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # Monitor progress if callback provided
            if progress_callback:
                self._monitor_conversion_progress(process, progress_callback)
            
            # Wait for completion
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                # Verify output file was created
                if os.path.exists(output_file):
                    output_size = os.path.getsize(output_file)
                    self.logger.info(f"Conversion completed successfully: {output_size} bytes")
                    
                    return {
                        'success': True,
                        'input_file': input_file,
                        'output_file': output_file,
                        'output_size': output_size,
                        'format': output_format,
                        'quality': quality,
                        'warnings': validation.get('warnings', [])
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Output file was not created',
                        'stderr': stderr
                    }
            else:
                self.logger.error(f"Conversion failed with return code {process.returncode}")
                return {
                    'success': False,
                    'error': f'Conversion failed (exit code: {process.returncode})',
                    'stderr': stderr,
                    'stdout': stdout
                }
                
        except subprocess.TimeoutExpired:
            self.logger.error("Conversion timed out")
            return {
                'success': False,
                'error': 'Conversion timed out'
            }
        except Exception as e:
            self.logger.error(f"Error during conversion: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _monitor_conversion_progress(self, process: subprocess.Popen, 
                                   progress_callback: Callable) -> None:
        """
        Monitor FFmpeg conversion progress and call callback with updates.
        
        Args:
            process: FFmpeg subprocess
            progress_callback: Function to call with progress updates
        """
        try:
            for line in iter(process.stderr.readline, ''):
                if line:
                    # Parse FFmpeg progress output
                    progress_info = self._parse_ffmpeg_progress(line)
                    if progress_info:
                        progress_callback(progress_info)
                        
        except Exception as e:
            self.logger.warning(f"Error monitoring conversion progress: {str(e)}")
    
    def _parse_ffmpeg_progress(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse FFmpeg output line for progress information.
        
        Args:
            line: FFmpeg output line
            
        Returns:
            Dict with progress information or None
        """
        try:
            # Look for time progress indicators
            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = float(time_match.group(3))
                
                total_seconds = hours * 3600 + minutes * 60 + seconds
                
                return {
                    'type': 'progress',
                    'time_processed': total_seconds,
                    'time_formatted': f"{hours:02d}:{minutes:02d}:{seconds:06.2f}"
                }
            
            # Look for speed indicators
            speed_match = re.search(r'speed=(\d+\.?\d*)x', line)
            if speed_match:
                return {
                    'type': 'speed',
                    'speed_multiplier': float(speed_match.group(1))
                }
            
            return None
            
        except Exception:
            return None
    
    def get_conversion_estimates(self, input_file: str, output_format: str) -> Dict[str, Any]:
        """
        Estimate conversion time and output file size.
        
        Args:
            input_file: Path to input file
            output_format: Desired output format
            
        Returns:
            Dict containing estimates
        """
        try:
            if not os.path.exists(input_file):
                return {
                    'success': False,
                    'error': 'Input file not found'
                }
            
            input_size = os.path.getsize(input_file)
            
            # Rough estimates based on format and quality
            size_factors = {
                'm4b': 0.8,  # Slightly smaller due to better compression
                'mp3': 0.7,  # Generally smaller
                'm4a': 0.8,  # Similar to M4B
                'flac': 1.5   # Larger due to lossless compression
            }
            
            estimated_size = int(input_size * size_factors.get(output_format, 1.0))
            
            # Very rough time estimate (depends heavily on hardware)
            # Assume ~2-5x real-time for conversion
            estimated_time_minutes = 5  # Placeholder estimate
            
            return {
                'success': True,
                'input_size': input_size,
                'estimated_output_size': estimated_size,
                'estimated_time_minutes': estimated_time_minutes,
                'size_factor': size_factors.get(output_format, 1.0),
                'note': 'Estimates are approximate and depend on hardware performance'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating conversion estimates: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
