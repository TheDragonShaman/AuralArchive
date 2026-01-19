"""
Module Name: template_parser.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Parses and validates naming templates, handling variable substitution and
    validation for AudioBookShelf-friendly paths.

Location:
    /services/file_naming/template_parser.py

"""

import re
from typing import Dict, List, Optional, Tuple
from utils.logger import get_module_logger

_LOGGER = get_module_logger("Service.FileNaming.TemplateParser")


class TemplateParser:
    """
    Parses naming templates with variable substitution.
    
    Supported variables:
    - {author} - Primary author name
    - {title} - Book title
    - {series} - Series name
    - {series_number} - Book number in series (e.g., "Book 01")
    - {year} - Publication year
    - {narrator} - Primary narrator name
    - {asin} - Audible ASIN
    - {publisher} - Publisher name
    - {runtime} - Runtime in format "Xh Ym"
    """
    
    VALID_VARIABLES = {
        'author', 'title', 'series', 'series_number', 'year',
        'narrator', 'asin', 'publisher', 'runtime'
    }
    
    def __init__(self, *, logger=None):
        self.logger = logger or _LOGGER
        self.variable_pattern = re.compile(r'\{(\w+)\}')
    
    def get_template(self, template_name: str, templates: Dict[str, str]) -> str:
        """Get a template by name, falling back to 'simple' if not found."""
        template = templates.get(template_name)
        if not template:
            self.logger.warning(f"Template '{template_name}' not found, using 'simple'")
            return templates.get('simple', '{author}/{series}/{title}/{title}')
        return template
    
    def add_custom_template(self, name: str, template: str, templates: Dict[str, str]) -> bool:
        """
        Add or update a custom template after validation.
        
        Args:
            name: Template name
            template: Template string
            templates: Templates dictionary to update
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            is_valid, error = self.validate_template(template)
            if not is_valid:
                self.logger.error(f"Invalid template '{name}': {error}")
                return False
            
            templates[name] = template
            self.logger.info(f"Added custom template '{name}': {template}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding template '{name}': {e}")
            return False
    
    def validate_template(self, template: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a template string.
        
        Args:
            template: Template string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check for empty template
            if not template or not template.strip():
                return False, "Template cannot be empty"
            
            # Find all variables in template
            variables = self.variable_pattern.findall(template)
            
            # Check for invalid variables
            invalid_vars = [var for var in variables if var not in self.VALID_VARIABLES]
            if invalid_vars:
                return False, f"Invalid variables: {', '.join(invalid_vars)}"
            
            # Check for path traversal attempts
            if '..' in template:
                return False, "Template cannot contain path traversal sequences (..)"
            
            # Check for absolute paths
            if template.startswith('/') or template.startswith('\\'):
                return False, "Template cannot start with absolute path separator"
            
            # Check for drive letters (Windows)
            if re.match(r'^[a-zA-Z]:', template):
                return False, "Template cannot contain Windows drive letters"
            
            return True, None
        except Exception as e:
            return False, f"Template validation error: {str(e)}"
    
    def parse_template(self, template: str, book_data: Dict) -> str:
        """
        Parse a template by substituting variables with book data.
        
        Args:
            template: Template string with {variables}
            book_data: Dictionary containing book metadata
            
        Returns:
            Parsed string with variables replaced
        """
        try:
            result = template
            
            # Replace each variable with corresponding data
            for var in self.VALID_VARIABLES:
                placeholder = '{' + var + '}'
                if placeholder in result:
                    value = self._get_variable_value(var, book_data)
                    if value is None:
                        value_str = ''
                    elif isinstance(value, str):
                        value_str = value
                    else:
                        value_str = str(value)
                    result = result.replace(placeholder, value_str)
            
            # Remove leftover double slashes from empty segments
            while '//' in result:
                result = result.replace('//', '/')

            # Remove placeholder folder names like "N/A" that slipped through
            result = result.replace('/N/A/', '/').replace('N/A/', '').replace('/N/A', '')

            return result.strip('/')
        except Exception as e:
            self.logger.error(f"Error parsing template: {e}")
            raise
    
    def _get_variable_value(self, variable: str, book_data: Dict) -> str:
        """
        Get the value for a template variable from book data.
        
        Args:
            variable: Variable name (e.g., 'author', 'title')
            book_data: Book metadata dictionary
            
        Returns:
            String value for the variable
        """
        # Map of variable names to book_data keys
        # Some variables need special handling
        
        if variable == 'author':
            authors = (
                book_data.get('AuthorName')
                or book_data.get('author')
                or book_data.get('Author')
                or book_data.get('authors')
            )

            if isinstance(authors, list):
                author_name = authors[0] if authors else 'Unknown Author'
            else:
                author_name = authors or 'Unknown Author'
            return author_name
        elif variable == 'title':
            value = book_data.get('Title', book_data.get('title'))
            return str(value) if value else 'Unknown Title'
        elif variable == 'series':
            return self._get_series_name(book_data)
        elif variable == 'series_number':
            return self._get_series_number(book_data)
        elif variable == 'year':
            return self._get_year(book_data)
        elif variable == 'narrator':
            return self._get_narrator_name(book_data)
        elif variable == 'asin':
            value = book_data.get('ASIN', book_data.get('asin'))
            return str(value) if value else ''
        elif variable == 'publisher':
            value = book_data.get('Publisher', book_data.get('publisher'))
            return str(value) if value else 'Unknown Publisher'
        elif variable == 'runtime':
            return self._get_runtime(book_data)
        else:
            return ''
    
    def _get_author_name(self, book_data: Dict) -> str:
        """Extract primary author name from book data."""
        # Try different author field names
        author = (book_data.get('AuthorName') or 
                 book_data.get('Author') or 
                 book_data.get('author'))
        
        if not author:
            # Try authors list
            authors = book_data.get('Authors', book_data.get('authors', []))
            if authors:
                author = authors[0] if isinstance(authors, list) else authors
        
        return str(author) if author else 'Unknown Author'
    
    def _get_series_name(self, book_data: Dict) -> str:
        """Extract series name from book data."""
        series = (book_data.get('SeriesName') or 
                 book_data.get('Series') or 
                 book_data.get('series'))
        return str(series) if series else ''
    
    def _get_series_number(self, book_data: Dict) -> str:
        """
        Extract and format series number.
        
        Returns a numeric string for use in templates (e.g., "1", "1.5").
        """
        book_number = (book_data.get('book_number') or 
                      book_data.get('BookNumber'))
        
        if not book_number:
            return ''
        
        try:
            number = float(book_number)
            if number == int(number):
                return str(int(number))
            return f"{number:g}"
        except (ValueError, TypeError):
            # If it's already a string like "Book 1", return it
            return str(book_number)
    
    def _get_year(self, book_data: Dict) -> str:
        """Extract publication year."""
        # Try different year field names
        year = (book_data.get('release_date') or 
               book_data.get('ReleaseDate') or 
               book_data.get('year'))
        
        if year:
            # Extract year from date string if needed (e.g., "2023-01-15" -> "2023")
            year_str = str(year)
            if '-' in year_str:
                year_str = year_str.split('-')[0]
            return year_str
        
        return ''
    
    def _get_narrator_name(self, book_data: Dict) -> str:
        """Extract primary narrator name."""
        narrator = (book_data.get('narrator_name') or 
                   book_data.get('Narrator') or 
                   book_data.get('narrator'))
        
        if not narrator:
            # Try narrators list
            narrators = book_data.get('Narrators', book_data.get('narrators', []))
            if narrators:
                narrator = narrators[0] if isinstance(narrators, list) else narrators
        
        return str(narrator) if narrator else ''
    
    def _get_runtime(self, book_data: Dict) -> str:
        """
        Extract and format runtime.
        
        Returns formatted string like "12h 34m" or empty string if not available.
        """
        runtime = book_data.get('RuntimeLengthMin', book_data.get('runtime_minutes'))
        
        if not runtime:
            return ''
        
        try:
            minutes = int(runtime)
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h {mins:02d}m"
        except (ValueError, TypeError):
            return ''
    
    def get_template_variables(self, template: str) -> List[str]:
        """
        Extract all variable names from a template.
        
        Args:
            template: Template string
            
        Returns:
            List of variable names found in template
        """
        return self.variable_pattern.findall(template)
