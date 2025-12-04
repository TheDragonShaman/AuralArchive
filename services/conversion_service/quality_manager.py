"""
Quality Manager - Conversion Service Helper

Manages audiobook conversion quality settings with configurable presets.
Settings can be configured via the settings menu and saved to config.

Features:
- Predefined quality presets based on audiobook best practices
- User-configurable settings
- Quality validation and recommendations
- Integration with config service

Author: AuralArchive Development Team
Created: September 28, 2025
"""

from typing import Dict, Any, List, Optional
from utils.logger import get_module_logger


class QualityManager:
    """Manager for conversion quality settings and presets"""
    
    def __init__(self):
        self.logger = get_module_logger("QualityManager")
        
        # Quality presets based on research and m4b-tool best practices
        self.quality_presets = self._initialize_quality_presets()
        
        # Codec preferences based on availability and quality
        self.codec_preferences = [
            'libfdk_aac',  # Best quality (requires compilation)
            'aac',         # Good quality (built-in)
            'libmp3lame'   # Fallback for MP3 output
        ]
    
    def _initialize_quality_presets(self) -> Dict[str, Dict[str, Any]]:
        """Initialize predefined quality presets"""
        return {
            'high_quality': {
                'name': 'High Quality',
                'description': 'Best quality for archival and high-end playback (128k)',
                'codec': 'aac',  # Will upgrade to libfdk_aac if available
                'bitrate': '128k',
                'sample_rate': '44100',
                'channels': '2',  # Stereo for high quality
                'profile': '',
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'Archival, high-end audio systems',
                'estimated_size_per_hour': '58 MB'
            },
            
            'standard_quality': {
                'name': 'Standard Quality', 
                'description': 'Good balance of quality and file size (64k)',
                'codec': 'aac',
                'bitrate': '64k',
                'sample_rate': '22050',
                'channels': '1',  # Mono for smaller size
                'profile': '',
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'General audiobook listening',
                'estimated_size_per_hour': '29 MB'
            },
            
            'mobile_optimized': {
                'name': 'Mobile Optimized',
                'description': 'Optimized for mobile devices and limited storage (48k)',
                'codec': 'aac',
                'bitrate': '48k',
                'sample_rate': '22050',
                'channels': '1',
                'profile': '',
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'Mobile devices, limited storage',
                'estimated_size_per_hour': '22 MB'
            },
            
            'low_bandwidth': {
                'name': 'Low Bandwidth',
                'description': 'Minimal file size with acceptable quality (32k)',
                'codec': 'aac',
                'bitrate': '32k',
                'sample_rate': '22050',
                'channels': '1',
                'profile': 'aac_he',  # High Efficiency for low bitrates
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'Very limited storage, slow connections',
                'estimated_size_per_hour': '14 MB'
            },
            
            'voice_optimized': {
                'name': 'Voice Optimized',
                'description': 'Optimized specifically for human speech (56k)',
                'codec': 'aac',
                'bitrate': '56k',
                'sample_rate': '22050',
                'channels': '1',
                'profile': '',
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'Speech-heavy content, podcasts',
                'estimated_size_per_hour': '25 MB'
            },
            
            'custom': {
                'name': 'Custom',
                'description': 'User-defined quality settings',
                'codec': 'aac',
                'bitrate': '64k',
                'sample_rate': '22050',
                'channels': '1',
                'profile': '',
                'format': 'm4b',
                'preserve_chapters': True,
                'embed_cover': True,
                'preserve_metadata': True,
                'use_case': 'Custom user preferences',
                'estimated_size_per_hour': 'Variable'
            }
        }
    
    def get_available_presets(self) -> Dict[str, Dict[str, Any]]:
        """Get all available quality presets"""
        return self.quality_presets.copy()
    
    def get_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Get specific quality preset"""
        return self.quality_presets.get(preset_name)
    
    def get_recommended_preset(self, use_case: str = None) -> str:
        """Get recommended preset based on use case"""
        recommendations = {
            'general': 'standard_quality',
            'mobile': 'mobile_optimized',
            'archival': 'high_quality',
            'limited_storage': 'low_bandwidth',
            'speech': 'voice_optimized'
        }
        
        if use_case and use_case in recommendations:
            return recommendations[use_case]
        
        # Default recommendation
        return 'standard_quality'
    
    def validate_quality_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate quality settings and provide recommendations"""
        validation = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'recommendations': []
        }
        
        try:
            # Validate codec
            codec = settings.get('codec', 'aac')
            if codec not in ['aac', 'libfdk_aac', 'libmp3lame']:
                validation['warnings'].append(f'Unusual codec "{codec}" - standard options are aac, libfdk_aac, libmp3lame')
            
            # Validate bitrate
            bitrate = settings.get('bitrate', '64k')
            if isinstance(bitrate, str) and bitrate.endswith('k'):
                try:
                    bitrate_num = int(bitrate[:-1])
                    if bitrate_num < 16:
                        validation['warnings'].append('Very low bitrate may result in poor quality')
                    elif bitrate_num > 256:
                        validation['warnings'].append('Very high bitrate may result in large files without quality benefit')
                    elif bitrate_num <= 32 and not settings.get('profile'):
                        validation['recommendations'].append('Consider using aac_he profile for bitrates ≤32k')
                except ValueError:
                    validation['errors'].append(f'Invalid bitrate format: {bitrate}')
            
            # Validate sample rate
            sample_rate = settings.get('sample_rate', '22050')
            try:
                sr_num = int(sample_rate)
                if sr_num not in [8000, 11025, 16000, 22050, 44100, 48000]:
                    validation['warnings'].append(f'Unusual sample rate {sr_num}Hz - standard rates are 22050Hz or 44100Hz for audiobooks')
                elif sr_num > 44100:
                    validation['recommendations'].append('Sample rates >44100Hz may not provide benefits for audiobooks')
            except ValueError:
                validation['errors'].append(f'Invalid sample rate: {sample_rate}')
            
            # Validate channels
            channels = settings.get('channels', '1')
            try:
                ch_num = int(channels)
                if ch_num not in [1, 2]:
                    validation['errors'].append(f'Invalid channel count: {channels} (must be 1 or 2)')
                elif ch_num == 2:
                    validation['recommendations'].append('Stereo (2 channels) increases file size - mono (1 channel) is often sufficient for audiobooks')
            except ValueError:
                validation['errors'].append(f'Invalid channel count: {channels}')
            
            # Validate profile
            profile = settings.get('profile', '')
            if profile and profile not in ['aac_he', 'aac_he_v2']:
                validation['warnings'].append(f'Unusual AAC profile: {profile}')
            
            # Quality recommendations based on settings combination
            if settings.get('codec') == 'aac' and 'libfdk_aac' in self.codec_preferences:
                validation['recommendations'].append('Consider upgrading to libfdk_aac codec for better quality (requires FFmpeg compilation)')
            
            # File size estimation
            try:
                bitrate_num = int(settings.get('bitrate', '64k')[:-1])
                estimated_mb_per_hour = (bitrate_num * 3600) / (8 * 1024)  # Convert kbps to MB/hour
                validation['estimated_size_per_hour'] = f'{estimated_mb_per_hour:.0f} MB'
            except:
                validation['estimated_size_per_hour'] = 'Unknown'
            
            if validation['errors']:
                validation['valid'] = False
            
            return validation
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f'Validation error: {str(e)}'],
                'warnings': [],
                'recommendations': []
            }
    
    def optimize_settings_for_source(self, source_info: Dict[str, Any], target_preset: str = None) -> Dict[str, Any]:
        """Optimize quality settings based on source file characteristics"""
        try:
            # Get base preset
            if target_preset and target_preset in self.quality_presets:
                base_settings = self.quality_presets[target_preset].copy()
            else:
                base_settings = self.quality_presets['standard_quality'].copy()
            
            # Analyze source characteristics
            source_bitrate = source_info.get('bitrate', 0)
            source_sample_rate = source_info.get('sample_rate', 0)
            source_channels = source_info.get('channels', 1)
            source_duration = source_info.get('duration', 0)
            
            optimizations = []
            
            # Don't upsample if source has lower sample rate
            if source_sample_rate > 0:
                target_sr = int(base_settings.get('sample_rate', '22050'))
                if source_sample_rate < target_sr:
                    base_settings['sample_rate'] = str(source_sample_rate)
                    optimizations.append(f'Matched source sample rate: {source_sample_rate}Hz')
            
            # Don't exceed source channels
            if source_channels > 0:
                target_channels = int(base_settings.get('channels', '1'))
                if source_channels < target_channels:
                    base_settings['channels'] = str(source_channels)
                    optimizations.append(f'Matched source channels: {source_channels}')
            
            # Bitrate optimization based on source
            if source_bitrate > 0:
                target_bitrate_str = base_settings.get('bitrate', '64k')
                target_bitrate = int(target_bitrate_str[:-1]) if target_bitrate_str.endswith('k') else 64
                
                # Don't significantly exceed source bitrate unless upgrading quality
                source_bitrate_k = source_bitrate // 1000
                if source_bitrate_k < target_bitrate and target_preset not in ['high_quality', 'custom']:
                    # Suggest a reasonable bitrate based on source
                    optimized_bitrate = min(target_bitrate, max(48, source_bitrate_k))
                    base_settings['bitrate'] = f'{optimized_bitrate}k'
                    optimizations.append(f'Optimized bitrate for source: {optimized_bitrate}k (source: {source_bitrate_k}k)')
            
            # Long duration considerations
            if source_duration > 50000:  # ~14 hours
                hours = source_duration / 3600
                optimizations.append(f'Long audiobook detected ({hours:.1f} hours) - current settings will produce large file')
                
                if target_preset not in ['low_bandwidth', 'mobile_optimized']:
                    optimizations.append('Consider "Mobile Optimized" or "Low Bandwidth" preset for very long audiobooks')
            
            return {
                'optimized_settings': base_settings,
                'optimizations_applied': optimizations,
                'source_analysis': {
                    'bitrate': f'{source_bitrate // 1000}k' if source_bitrate > 0 else 'Unknown',
                    'sample_rate': f'{source_sample_rate}Hz' if source_sample_rate > 0 else 'Unknown',
                    'channels': source_channels,
                    'duration_hours': round(source_duration / 3600, 1) if source_duration > 0 else 0
                }
            }
            
        except Exception as e:
            self.logger.error(f'Error optimizing settings: {e}')
            return {
                'optimized_settings': self.quality_presets['standard_quality'].copy(),
                'optimizations_applied': [],
                'error': str(e)
            }
    
    def get_codec_recommendations(self, available_codecs: List[str]) -> Dict[str, Any]:
        """Get codec recommendations based on availability"""
        recommendations = {
            'recommended_codec': 'aac',  # Default fallback
            'available_codecs': available_codecs,
            'codec_quality_ranking': [],
            'notes': []
        }
        
        # Find best available codec
        for preferred_codec in self.codec_preferences:
            if preferred_codec in available_codecs:
                recommendations['recommended_codec'] = preferred_codec
                break
        
        # Provide quality ranking
        for codec in self.codec_preferences:
            if codec in available_codecs:
                quality_info = {
                    'codec': codec,
                    'quality': 'Excellent' if codec == 'libfdk_aac' else 'Good' if codec == 'aac' else 'Fair',
                    'notes': self._get_codec_notes(codec)
                }
                recommendations['codec_quality_ranking'].append(quality_info)
        
        # Add general notes
        if 'libfdk_aac' not in available_codecs:
            recommendations['notes'].append('libfdk_aac codec not available - install for best quality')
        
        if recommendations['recommended_codec'] == 'aac':
            recommendations['notes'].append('Using built-in AAC codec - good quality for most audiobooks')
        
        return recommendations
    
    def _get_codec_notes(self, codec: str) -> str:
        """Get notes for specific codec"""
        codec_notes = {
            'libfdk_aac': 'Best quality AAC encoder, especially for low bitrates',
            'aac': 'Built-in AAC encoder, good quality and widely compatible',
            'libmp3lame': 'MP3 encoder, compatible but less efficient than AAC'
        }
        return codec_notes.get(codec, 'Standard codec')
    
    def get_settings_for_use_case(self, use_case: str) -> Dict[str, Any]:
        """Get recommended settings for specific use case"""
        use_case_mapping = {
            'audiobook_general': 'standard_quality',
            'audiobook_mobile': 'mobile_optimized', 
            'audiobook_archival': 'high_quality',
            'podcast': 'voice_optimized',
            'limited_storage': 'low_bandwidth',
            'high_quality': 'high_quality'
        }
        
        preset_name = use_case_mapping.get(use_case, 'standard_quality')
        return self.get_preset(preset_name)
    
    def calculate_estimated_output_size(self, settings: Dict[str, Any], duration_seconds: float) -> Dict[str, Any]:
        """Calculate estimated output file size"""
        try:
            bitrate_str = settings.get('bitrate', '64k')
            if not bitrate_str.endswith('k'):
                return {'error': 'Invalid bitrate format'}
            
            bitrate_kbps = int(bitrate_str[:-1])
            
            # Calculate size in bytes
            size_bytes = (bitrate_kbps * 1000 * duration_seconds) / 8
            
            # Convert to readable units
            size_mb = size_bytes / (1024 * 1024)
            size_gb = size_mb / 1024
            
            hours = duration_seconds / 3600
            mb_per_hour = size_mb / hours if hours > 0 else 0
            
            return {
                'estimated_size_bytes': int(size_bytes),
                'estimated_size_mb': round(size_mb, 2),
                'estimated_size_gb': round(size_gb, 3) if size_gb >= 0.1 else None,
                'mb_per_hour': round(mb_per_hour, 1),
                'duration_hours': round(hours, 2),
                'bitrate_kbps': bitrate_kbps
            }
            
        except Exception as e:
            return {'error': str(e)}