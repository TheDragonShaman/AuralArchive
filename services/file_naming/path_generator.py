"""
Path Generator - Generates complete file paths from templates and metadata
Combines templates, metadata, and sanitization to create ABS-compatible paths

Location: services/file_naming/path_generator.py
Purpose: Generate complete file paths following ABS conventions
"""

import logging
import os
import re
from typing import Dict, Optional


class PathGenerator:
    """
    Generates complete file paths for audiobooks.
    
    Handles:
    - Template-based path generation
    - Author/Series folder organization
    - ASIN bracket notation
    - Path component sanitization
    """
    
    def __init__(self):
        self.logger = logging.getLogger("FileNamingService.PathGenerator")
        self.asin_pattern = re.compile(r'\[([A-Z0-9]+)\]')
    
    def generate_file_path(self, book_data: Dict, base_path: str, template: str, 
                          file_extension: str, include_asin: bool, sanitizer) -> str:
        """
        Generate a complete file path.
        
        Args:
            book_data: Book metadata dictionary
            base_path: Base directory path
            template: Naming template string
            file_extension: File extension (e.g., 'm4b')
            include_asin: Whether to include ASIN in brackets
            sanitizer: PathSanitizer instance
            
        Returns:
            Complete sanitized file path
        """
        try:
            # Import here to avoid circular dependency
            from .template_parser import TemplateParser
            parser = TemplateParser()
            
            # Parse the template with book data
            parsed_path = parser.parse_template(template, book_data)
            
            # Add ASIN if requested and not already in template
            if include_asin and '{asin}' not in template:
                asin = book_data.get('ASIN', book_data.get('asin'))
                if asin:
                    # Add ASIN before extension
                    parsed_path = f"{parsed_path} [{asin}]"
            
            # Split into path components
            components = parsed_path.split('/')
            
            # Sanitize each component
            sanitized_components = [sanitizer.sanitize_path_component(comp) for comp in components]
            
            # Build the path
            folder_path = os.path.join(base_path, *sanitized_components[:-1]) if len(sanitized_components) > 1 else base_path
            filename = sanitized_components[-1] if sanitized_components else 'unknown'
            
            # Add extension if not already present
            if not filename.lower().endswith(f'.{file_extension.lower()}'):
                filename = f"{filename}.{file_extension}"
            
            # Combine into full path
            full_path = os.path.join(folder_path, filename)
            
            # Final sanitization
            full_path = sanitizer.sanitize_path(full_path)
            
            self.logger.debug(f"Generated path: {full_path}")
            return full_path
            
        except Exception as e:
            self.logger.error(f"Error generating file path: {e}")
            raise
    
    def generate_folder_path(self, book_data: Dict, base_path: str, 
                            create_author_folders: bool, create_series_folders: bool,
                            sanitizer) -> str:
        """
        Generate just the folder path (no filename).
        
        Args:
            book_data: Book metadata
            base_path: Base directory
            create_author_folders: Whether to create author subfolder
            create_series_folders: Whether to create series subfolder
            sanitizer: PathSanitizer instance
            
        Returns:
            Complete folder path
        """
        try:
            path_components = [base_path]
            
            # Add author folder if enabled
            if create_author_folders:
                author = book_data.get('Author', book_data.get('author', 'Unknown Author'))
                if isinstance(author, list):
                    author = author[0]
                path_components.append(sanitizer.sanitize_path_component(str(author)))
            
            # Add series folder if enabled and book is part of a series
            if create_series_folders:
                series = book_data.get('Series', book_data.get('series'))
                if series and series.lower() != 'standalone':
                    path_components.append(sanitizer.sanitize_path_component(str(series)))
            
            folder_path = os.path.join(*path_components)
            return sanitizer.sanitize_path(folder_path)
            
        except Exception as e:
            self.logger.error(f"Error generating folder path: {e}")
            raise
    
    def generate_filename(self, book_data: Dict, template: str, file_extension: str,
                         include_asin: bool, sanitizer) -> str:
        """
        Generate just the filename (no path).
        
        Args:
            book_data: Book metadata
            template: Naming template
            file_extension: File extension
            include_asin: Whether to include ASIN
            sanitizer: PathSanitizer instance
            
        Returns:
            Sanitized filename with extension
        """
        try:
            # Import here to avoid circular dependency
            from .template_parser import TemplateParser
            parser = TemplateParser()
            
            # Parse template
            parsed = parser.parse_template(template, book_data)
            
            # For filename, we only want the last component if template has paths
            if '/' in parsed:
                parsed = parsed.split('/')[-1]
            
            # Add ASIN if requested
            if include_asin and '{asin}' not in template:
                asin = book_data.get('ASIN', book_data.get('asin'))
                if asin:
                    parsed = f"{parsed} [{asin}]"
            
            # Sanitize filename
            filename = sanitizer.sanitize_filename(parsed)
            
            # Add extension
            if not filename.lower().endswith(f'.{file_extension.lower()}'):
                filename = f"{filename}.{file_extension}"
            
            return filename
            
        except Exception as e:
            self.logger.error(f"Error generating filename: {e}")
            raise
    
    def parse_abs_path(self, file_path: str, sanitizer) -> Dict[str, Optional[str]]:
        """
        Parse an existing ABS file path to extract metadata.
        
        Attempts to extract:
        - Author (from folder structure)
        - Series (from folder structure)
        - Title
        - ASIN (from brackets)
        - Year (from parentheses)
        - Series number (from "Book XX" pattern)
        
        Args:
            file_path: Full file path
            sanitizer: PathSanitizer instance
            
        Returns:
            Dictionary with extracted metadata
        """
        try:
            # Normalize the path
            normalized = sanitizer.sanitize_path(file_path)
            
            # Split into components
            components = normalized.split(os.sep)
            
            # Extract filename (last component)
            filename = components[-1] if components else ''
            
            # Remove extension
            name_without_ext = os.path.splitext(filename)[0]
            
            metadata = {
                'author': None,
                'series': None,
                'title': None,
                'asin': None,
                'year': None,
                'series_number': None,
                'narrator': None
            }
            
            # Extract ASIN from brackets
            asin_match = self.asin_pattern.search(name_without_ext)
            if asin_match:
                metadata['asin'] = asin_match.group(1)
                # Remove ASIN from name for further parsing
                name_without_ext = self.asin_pattern.sub('', name_without_ext).strip()
            
            # Extract year from parentheses
            year_match = re.search(r'\((\d{4})\)', name_without_ext)
            if year_match:
                metadata['year'] = year_match.group(1)
                # Remove year from name
                name_without_ext = re.sub(r'\(\d{4}\)', '', name_without_ext).strip()
            
            # Extract series number (e.g., "Book 01", "01 -", etc.)
            series_num_match = re.search(r'(?:Book\s+)?(\d+(?:\.\d+)?)\s*-', name_without_ext)
            if series_num_match:
                metadata['series_number'] = series_num_match.group(1)
            
            # Try to extract author and series from folder structure
            # Common patterns:
            # - /Author/Series/filename
            # - /Author/filename
            if len(components) >= 3:
                # Likely has author and series folders
                metadata['author'] = components[-3]
                metadata['series'] = components[-2]
            elif len(components) >= 2:
                # Likely just author folder
                metadata['author'] = components[-2]
            
            # What's left is probably the title (with narrator if present)
            # Split on " - " to separate title from narrator
            parts = name_without_ext.split(' - ')
            
            # First part is likely title (possibly with series number)
            if parts:
                title_part = parts[0].strip()
                # Remove "Book XX" prefix if present
                title_part = re.sub(r'^(?:Book\s+)?\d+(?:\.\d+)?\s*-?\s*', '', title_part).strip()
                metadata['title'] = title_part
            
            # Last part might be narrator
            if len(parts) > 1:
                metadata['narrator'] = parts[-1].strip()
            
            self.logger.debug(f"Parsed path metadata: {metadata}")
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error parsing ABS path: {e}")
            return {
                'author': None,
                'series': None,
                'title': None,
                'asin': None,
                'year': None,
                'series_number': None,
                'narrator': None
            }
