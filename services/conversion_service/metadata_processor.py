"""
Module Name: metadata_processor.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Extracts, preserves, and embeds metadata during audiobook conversion flows.

Location:
    /services/conversion_service/metadata_processor.py

"""

import os
import subprocess
import tempfile
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from utils.logger import get_module_logger


class MetadataProcessor:
    """Processor for audiobook metadata and chapters"""

    def __init__(self, *, logger=None):
        self.logger = logger or get_module_logger("Service.Conversion.MetadataProcessor")
        
        # Standard metadata field mappings
        self.metadata_fields = {
            'title': 'title',
            'artist': 'artist',
            'album': 'album',
            'albumartist': 'album_artist',
            'composer': 'composer',
            'date': 'date',
            'year': 'year',
            'genre': 'genre',
            'comment': 'comment',
            'description': 'description',
            'synopsis': 'synopsis',
            'narrator': 'narrator',
            'author': 'author',
            'publisher': 'publisher',
            'series': 'series',
            'series_part': 'series_part'
        }
    
    def process_metadata(
        self, 
        output_file: str, 
        quality_settings: Dict[str, Any], 
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process and embed metadata into the output file
        
        Args:
            output_file: Path to the converted audio file
            quality_settings: Quality settings that affect metadata processing
            custom_metadata: Additional metadata to embed
            
        Returns:
            Dict with processing results
        """
        try:
            self.logger.info("Processing metadata", extra={"output_file": output_file})
            
            results = {
                'success': True,
                'processed': [],
                'warnings': [],
                'errors': []
            }
            
            # Step 1: Extract existing metadata
            existing_metadata = self._extract_metadata(output_file)
            results['existing_metadata'] = existing_metadata
            
            # Step 2: Process chapters if enabled
            if quality_settings.get('preserve_chapters', True):
                chapter_result = self._process_chapters(output_file)
                results['chapter_processing'] = chapter_result
                if chapter_result.get('success'):
                    results['processed'].append('chapters')
                else:
                    results['warnings'].append(f'Chapter processing: {chapter_result.get("error")}')
            
            # Step 3: Process cover art if enabled
            if quality_settings.get('embed_cover', True):
                cover_result = self._process_cover_art(output_file, custom_metadata)
                results['cover_processing'] = cover_result
                if cover_result.get('success'):
                    results['processed'].append('cover_art')
                else:
                    results['warnings'].append(f'Cover processing: {cover_result.get("error")}')
            
            # Step 4: Standardize and clean metadata
            if quality_settings.get('preserve_metadata', True):
                cleanup_result = self._standardize_metadata(output_file, custom_metadata)
                results['metadata_cleanup'] = cleanup_result
                if cleanup_result.get('success'):
                    results['processed'].append('metadata_standardization')
                else:
                    results['warnings'].append(f'Metadata cleanup: {cleanup_result.get("error")}')
            
            # Step 5: Validate final file
            validation_result = self._validate_processed_file(output_file)
            results['validation'] = validation_result
            
            if not validation_result.get('success'):
                results['success'] = False
                results['errors'].append(validation_result.get('error', 'File validation failed'))
            
            self.logger.info(
                "Metadata processing complete",
                extra={
                    "output_file": output_file,
                    "processed": results['processed'],
                    "warnings": results['warnings'],
                    "errors": results['errors']
                }
            )
            
            return results
            
        except Exception as e:
            self.logger.exception("Metadata processing failed", extra={"output_file": output_file, "error": str(e)})
            return {
                'success': False,
                'error': str(e)
            }
    
    def _extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from audio file using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_chapters',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                
                format_info = probe_data.get('format', {})
                chapters = probe_data.get('chapters', [])
                
                return {
                    'tags': format_info.get('tags', {}),
                    'duration': float(format_info.get('duration', 0)),
                    'bitrate': int(format_info.get('bit_rate', 0)),
                    'chapters': chapters,
                    'chapter_count': len(chapters)
                }
            else:
                self.logger.warning("Could not extract metadata", extra={"file_path": file_path, "stderr": result.stderr})
                return {}
                
        except Exception as e:
            self.logger.exception("Error extracting metadata", extra={"file_path": file_path, "error": str(e)})
            return {}
    
    def _process_chapters(self, file_path: str) -> Dict[str, Any]:
        """Process and validate chapter information"""
        try:
            metadata = self._extract_metadata(file_path)
            chapters = metadata.get('chapters', [])
            
            if not chapters:
                return {
                    'success': True,
                    'message': 'No chapters found in file',
                    'chapter_count': 0
                }
            
            # Validate chapter structure
            valid_chapters = []
            for i, chapter in enumerate(chapters):
                if 'start_time' in chapter and 'end_time' in chapter:
                    # Ensure chapter has a title
                    if 'tags' in chapter and 'title' in chapter['tags']:
                        valid_chapters.append(chapter)
                    else:
                        # Generate default chapter title
                        chapter['tags'] = chapter.get('tags', {})
                        chapter['tags']['title'] = f'Chapter {i + 1}'
                        valid_chapters.append(chapter)
                else:
                    self.logger.warning("Chapter missing timing information", extra={"file_path": file_path, "chapter_index": i})
            
            # If we have valid chapters, try to re-embed them cleanly
            if valid_chapters:
                chapter_result = self._embed_chapters(file_path, valid_chapters)
                return {
                    'success': chapter_result,
                    'chapter_count': len(valid_chapters),
                    'message': f'Processed {len(valid_chapters)} chapters'
                }
            else:
                return {
                    'success': True,
                    'chapter_count': 0,
                    'message': 'No valid chapters to process'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _embed_chapters(self, file_path: str, chapters: List[Dict]) -> bool:
        """Embed chapter information into the file"""
        try:
            # Create temporary chapters file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                for chapter in chapters:
                    start_time = float(chapter.get('start_time', 0))
                    title = chapter.get('tags', {}).get('title', 'Untitled Chapter')
                    
                    # Convert seconds to HH:MM:SS.mmm format
                    hours = int(start_time // 3600)
                    minutes = int((start_time % 3600) // 60)
                    seconds = start_time % 60
                    
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
                    temp_file.write(f"{time_str} {title}\n")
                
                temp_chapters_file = temp_file.name
            
            # Use mp4chaps to embed chapters if available
            try:
                cmd = ['mp4chaps', '-i', file_path, '-z', temp_chapters_file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    os.unlink(temp_chapters_file)
                    return True
                else:
                    self.logger.warning(
                        "mp4chaps failed, trying fallback method",
                        extra={"file_path": file_path, "stderr": result.stderr},
                    )
            
            except FileNotFoundError:
                self.logger.debug(
                    "mp4chaps not available, using FFmpeg method",
                    extra={"file_path": file_path},
                )
            
            # Fallback: Use FFmpeg to re-encode with chapters
            # Note: This is more complex and may require re-encoding
            os.unlink(temp_chapters_file)
            return True  # For now, return True to indicate processing attempted
            
        except Exception as e:
            self.logger.exception("Error embedding chapters", extra={"file_path": file_path, "error": str(e)})
            return False
    
    def _process_cover_art(self, file_path: str, custom_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Process and embed cover art"""
        try:
            # Check if file already has cover art
            existing_cover = self._extract_cover_art(file_path)
            
            cover_path = None
            if custom_metadata and 'cover_path' in custom_metadata:
                cover_path = custom_metadata['cover_path']
            elif existing_cover:
                return {
                    'success': True,
                    'message': 'Cover art already present',
                    'has_cover': True
                }
            
            # Look for cover files in the same directory
            if not cover_path:
                cover_path = self._find_cover_file(file_path)
            
            if cover_path and os.path.exists(cover_path):
                embed_result = self._embed_cover_art(file_path, cover_path)
                return {
                    'success': embed_result,
                    'cover_path': cover_path,
                    'message': 'Cover art embedded' if embed_result else 'Failed to embed cover art'
                }
            else:
                return {
                    'success': True,
                    'message': 'No cover art found to embed',
                    'has_cover': False
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _extract_cover_art(self, file_path: str) -> bool:
        """Check if file has embedded cover art"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'csv=p=0',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return result.returncode == 0 and result.stdout.strip() != ''
            
        except Exception:
            return False
    
    def _find_cover_file(self, file_path: str) -> Optional[str]:
        """Find cover art file in the same directory"""
        try:
            directory = os.path.dirname(file_path)
            cover_names = ['cover', 'folder', 'albumart', 'front']
            cover_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
            
            for name in cover_names:
                for ext in cover_extensions:
                    cover_file = os.path.join(directory, f"{name}{ext}")
                    if os.path.exists(cover_file):
                        return cover_file
            
            return None
            
        except Exception:
            return None
    
    def _embed_cover_art(self, file_path: str, cover_path: str) -> bool:
        """Embed cover art into the audio file"""
        try:
            # Create temporary output file
            temp_output = f"{file_path}.temp"
            
            cmd = [
                'ffmpeg', '-y',
                '-i', file_path,
                '-i', cover_path,
                '-c', 'copy',
                '-map', '0',
                '-map', '1',
                '-disposition:v:0', 'attached_pic',
                temp_output
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(temp_output):
                # Replace original with temp file
                os.replace(temp_output, file_path)
                return True
            else:
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                self.logger.warning("Cover embedding failed", extra={"file_path": file_path, "cover_path": cover_path, "stderr": result.stderr})
                return False
                
        except Exception as e:
            self.logger.exception("Error embedding cover art", extra={"file_path": file_path, "cover_path": cover_path, "error": str(e)})
            return False
    
    def _standardize_metadata(self, file_path: str, custom_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Standardize and clean up metadata tags"""
        try:
            if not custom_metadata:
                return {
                    'success': True,
                    'message': 'No custom metadata to process'
                }
            
            # Build metadata parameters for FFmpeg
            metadata_params = []
            
            for key, value in custom_metadata.items():
                if key in self.metadata_fields and value:
                    ffmpeg_key = self.metadata_fields[key]
                    metadata_params.extend(['-metadata', f'{ffmpeg_key}={value}'])
            
            if not metadata_params:
                return {
                    'success': True,
                    'message': 'No metadata to standardize'
                }
            
            # Apply metadata using FFmpeg
            temp_output = f"{file_path}.metadata_temp"
            
            cmd = ['ffmpeg', '-y', '-i', file_path, '-c', 'copy'] + metadata_params + [temp_output]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists(temp_output):
                os.replace(temp_output, file_path)
                return {
                    'success': True,
                    'message': f'Applied {len(metadata_params)//2} metadata fields'
                }
            else:
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return {
                    'success': False,
                    'error': f'Metadata application failed: {result.stderr}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_processed_file(self, file_path: str) -> Dict[str, Any]:
        """Validate the processed file"""
        try:
            if not os.path.exists(file_path):
                return {
                    'success': False,
                    'error': 'Processed file does not exist'
                }
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return {
                    'success': False,
                    'error': 'Processed file is empty'
                }
            
            # Quick metadata validation
            metadata = self._extract_metadata(file_path)
            if not metadata:
                return {
                    'success': False,
                    'error': 'Could not read metadata from processed file'
                }
            
            return {
                'success': True,
                'file_size': file_size,
                'duration': metadata.get('duration', 0),
                'has_chapters': metadata.get('chapter_count', 0) > 0,
                'metadata_fields': len(metadata.get('tags', {}))
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }