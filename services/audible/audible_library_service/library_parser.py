"""
Module Name: library_parser.py
Author: TheDragonShaman
Created: August 24, 2025
Last Modified: December 23, 2025
Description:
    Parse and analyze Audible library data from API/CLI exports for search and stats.
Location:
    /services/audible/audible_library_service/library_parser.py

"""

import json
import csv
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict, Counter

from utils.logger import get_module_logger


class AudibleLibraryParser:
    """
    Parses and processes Audible library data from various export formats.
    
    This class provides comprehensive parsing capabilities for Audible library
    exports, including metadata extraction, search functionality, and statistics
    generation.
    """
    
    def __init__(self, logger=None):
        """
        Initialize the Library Parser.
        
        Args:
            logger: Logger instance for parser operations
        """
        self.logger = logger or get_module_logger("Service.Audible.Library.Parser")
        
        # Field mappings for different export formats
        self.field_mappings = {
            'json': {
                'title': ['title', 'product_title'],
                'author': ['authors', 'author'],
                'narrator': ['narrators', 'narrator'],
                'asin': ['asin'],
                'series': ['series'],
                'length': ['length', 'runtime_length_min', 'duration'],
                'genre': ['genre', 'genres'],
                'rating': ['rating', 'customer_rating'],
                'purchase_date': ['purchase_date', 'date_added'],
                'release_date': ['release_date', 'publication_date']
            }
        }
        
        self.logger.debug("AudibleLibraryParser initialized")
    
    def parse_library_data(self, raw_data: Any, format_type: str = 'json') -> Dict[str, Any]:
        """
        Parse raw library data into standardized format.
        
        Args:
            raw_data: Raw library data from audible-cli export
            format_type: Format of the raw data ('json', 'csv', 'tsv')
            
        Returns:
            Dict containing parsed and standardized library data
        """
        try:
            if format_type == 'json':
                return self._parse_json_library(raw_data)
            elif format_type in ['csv', 'tsv']:
                return self._parse_csv_library(raw_data, format_type)
            else:
                raise ValueError(f"Unsupported format type: {format_type}")
                
        except Exception as exc:
            self.logger.error(
                "Error parsing library data",
                extra={"format_type": format_type, "exc": exc}
            )
            return {
                'books': [],
                'error': str(exc),
                'format': format_type,
                'parsed_count': 0
            }
    
    def _parse_json_library(self, json_data: Any) -> Dict[str, Any]:
        """
        Parse JSON format library data.
        
        Args:
            json_data: JSON library data from audible-cli
            
        Returns:
            Dict containing parsed book data
        """
        books = []
        
        try:
            # Handle different JSON structures
            if isinstance(json_data, list):
                book_list = json_data
            elif isinstance(json_data, dict):
                # Look for common keys that contain book lists
                book_list = (json_data.get('items') or 
                           json_data.get('books') or 
                           json_data.get('library') or 
                           [json_data])  # Single book case
            else:
                book_list = []
            
            for book_data in book_list:
                parsed_book = self._parse_book_data(book_data)
                if parsed_book:
                    books.append(parsed_book)
            
            self.logger.info(
                "Parsed books from JSON",
                extra={"parsed_count": len(books)}
            )
            
            return {
                'books': books,
                'format': 'json',
                'parsed_count': len(books),
                'parse_date': datetime.now().isoformat()
            }
            
        except Exception as exc:
            self.logger.error(
                "Error parsing JSON library",
                extra={"exc": exc}
            )
            return {
                'books': [],
                'error': str(exc),
                'format': 'json',
                'parsed_count': 0
            }
    
    def _parse_csv_library(self, csv_data: str, format_type: str) -> Dict[str, Any]:
        """
        Parse CSV/TSV format library data.
        
        Args:
            csv_data: CSV/TSV library data string
            format_type: 'csv' or 'tsv'
            
        Returns:
            Dict containing parsed book data
        """
        books = []
        delimiter = '\t' if format_type == 'tsv' else ','
        
        try:
            lines = csv_data.strip().split('\n')
            if not lines:
                return {'books': [], 'format': format_type, 'parsed_count': 0}
            
            # Parse CSV data
            csv_reader = csv.DictReader(lines, delimiter=delimiter)
            
            for row in csv_reader:
                parsed_book = self._parse_book_data(row)
                if parsed_book:
                    books.append(parsed_book)
            
            self.logger.info(
                "Parsed books from delimited export",
                extra={"parsed_count": len(books), "format": format_type}
            )
            
            return {
                'books': books,
                'format': format_type,
                'parsed_count': len(books),
                'parse_date': datetime.now().isoformat()
            }
            
        except Exception as exc:
            self.logger.error(
                "Error parsing delimited library",
                extra={"format": format_type, "exc": exc}
            )
            return {
                'books': [],
                'error': str(exc),
                'format': format_type,
                'parsed_count': 0
            }
    
    def _parse_book_data(self, book_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse individual book data into standardized format.
        
        Args:
            book_data: Raw book data dictionary
            
        Returns:
            Standardized book data dictionary or None if parsing fails
        """
        try:
            parsed_book = {}
            
            # Extract title
            parsed_book['title'] = self._extract_field(book_data, ['title', 'product_title', 'name'])
            
            # Extract author(s)
            authors = self._extract_field(book_data, ['authors', 'author', 'author_name'])
            parsed_book['authors'] = self._normalize_list_field(authors)
            
            # Extract narrator(s)
            narrators = self._extract_field(book_data, ['narrators', 'narrator', 'narrator_name'])
            parsed_book['narrators'] = self._normalize_list_field(narrators)
            
            # Extract ASIN
            parsed_book['asin'] = self._extract_field(book_data, ['asin', 'id', 'product_id'])
            
            # Extract series information
            series = self._extract_field(book_data, ['series', 'series_title'])
            parsed_book['series'] = self._normalize_series_field(series)
            
            # Extract length/duration
            length = self._extract_field(book_data, ['length', 'runtime_length_min', 'duration'])
            parsed_book['length_minutes'] = self._normalize_duration_field(length)
            
            # Extract genre(s)
            genres = self._extract_field(book_data, ['genre', 'genres', 'categories'])
            parsed_book['genres'] = self._normalize_list_field(genres)
            
            # Extract rating
            rating = self._extract_field(book_data, ['rating', 'customer_rating', 'overall_rating'])
            parsed_book['rating'] = self._normalize_rating_field(rating)
            
            # Extract number of ratings
            num_ratings = self._extract_field(book_data, ['num_ratings', 'rating_count', 'total_ratings'])
            parsed_book['num_ratings'] = self._normalize_integer_field(num_ratings)
            
            # Extract dates
            parsed_book['purchase_date'] = self._extract_field(book_data, ['purchase_date', 'date_added'])
            parsed_book['release_date'] = self._extract_field(book_data, ['release_date', 'publication_date'])
            
            # Extract additional metadata
            parsed_book['subtitle'] = self._extract_field(book_data, ['subtitle', 'sub_title'])
            parsed_book['language'] = self._extract_field(book_data, ['language', 'lang'])
            parsed_book['publisher'] = self._extract_field(book_data, ['publisher', 'publisher_name'])
            
            # Only return book if we have at least title and ASIN
            if parsed_book.get('title') and parsed_book.get('asin'):
                return parsed_book
            else:
                self.logger.debug(
                    "Skipping book with insufficient data",
                    extra={"book": parsed_book}
                )
                return None
                
        except Exception as exc:
            self.logger.error(
                "Error parsing individual book data",
                extra={"exc": exc}
            )
            return None
    
    def _extract_field(self, data: Dict[str, Any], field_names: List[str]) -> Any:
        """
        Extract field value from data using multiple possible field names.
        
        Args:
            data: Data dictionary
            field_names: List of possible field names to try
            
        Returns:
            Field value or None if not found
        """
        for field_name in field_names:
            if field_name in data and data[field_name] is not None:
                return data[field_name]
        return None
    
    def _normalize_list_field(self, value: Any) -> List[str]:
        """
        Normalize a field that could be a string, list, or None into a list of strings.
        
        Args:
            value: Field value to normalize
            
        Returns:
            List of strings
        """
        if not value:
            return []
        
        if isinstance(value, list):
            return [str(item).strip() for item in value if item]
        elif isinstance(value, str):
            # Handle comma-separated values
            if ',' in value:
                return [item.strip() for item in value.split(',') if item.strip()]
            else:
                return [value.strip()]
        else:
            return [str(value).strip()]
    
    def _normalize_series_field(self, value: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize series field into standardized format.
        
        Args:
            value: Series field value
            
        Returns:
            Dictionary with series information or None
        """
        if not value:
            return None
        
        if isinstance(value, dict):
            return {
                'title': value.get('title', ''),
                'sequence': value.get('sequence', ''),
                'position': value.get('position', '')
            }
        elif isinstance(value, str):
            # Try to extract series and book number
            series_match = re.match(r'^(.+?)\s*(?:#|Book\s+)(\d+)$', value.strip())
            if series_match:
                return {
                    'title': series_match.group(1).strip(),
                    'sequence': series_match.group(2),
                    'position': series_match.group(2)
                }
            else:
                return {
                    'title': value.strip(),
                    'sequence': '',
                    'position': ''
                }
        
        return None
    
    def _normalize_duration_field(self, value: Any) -> Optional[int]:
        """
        Normalize duration field to minutes.
        
        Args:
            value: Duration value in various formats
            
        Returns:
            Duration in minutes or None
        """
        if not value:
            return None
        
        try:
            # If already a number, assume it's minutes
            if isinstance(value, (int, float)):
                return int(value)
            
            # If string, try to parse different formats
            if isinstance(value, str):
                value = value.strip().lower()
                
                # Format: "5 hrs and 23 mins"
                hrs_mins_match = re.search(r'(\d+)\s*hrs?\s*(?:and\s*)?(\d+)\s*mins?', value)
                if hrs_mins_match:
                    hours = int(hrs_mins_match.group(1))
                    minutes = int(hrs_mins_match.group(2))
                    return hours * 60 + minutes
                
                # Format: "5:23:45" (hours:minutes:seconds)
                time_match = re.search(r'(\d+):(\d+):(\d+)', value)
                if time_match:
                    hours = int(time_match.group(1))
                    minutes = int(time_match.group(2))
                    return hours * 60 + minutes
                
                # Format: "323 mins"
                mins_match = re.search(r'(\d+)\s*mins?', value)
                if mins_match:
                    return int(mins_match.group(1))
                
                # Format: "5 hours"
                hrs_match = re.search(r'(\d+)\s*hrs?', value)
                if hrs_match:
                    return int(hrs_match.group(1)) * 60
                
                # Just a number as string
                if value.isdigit():
                    return int(value)
            
            return None
            
        except Exception:
            return None
    
    def _normalize_rating_field(self, value: Any) -> Optional[float]:
        """
        Normalize rating field to float value.
        
        Args:
            value: Rating value
            
        Returns:
            Rating as float or None
        """
        if not value:
            return None
        
        try:
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                # Extract number from string like "4.5 out of 5 stars"
                rating_match = re.search(r'(\d+\.?\d*)', value.strip())
                if rating_match:
                    return float(rating_match.group(1))
            
            return None
            
        except Exception:
            return None

    def _normalize_integer_field(self, value: Any) -> Optional[int]:
        """Normalize integer-like values into an int."""
        if value in (None, ""):
            return None

        try:
            if isinstance(value, int):
                return value

            if isinstance(value, float):
                return int(value)

            if isinstance(value, str):
                normalized = value.strip().lower()

                if not normalized:
                    return None

                # Handle suffixes like "1.2k"
                if normalized.endswith("k"):
                    number = float(normalized[:-1].replace(",", ""))
                    return int(number * 1000)

                # Remove commas or other separators
                normalized = normalized.replace(",", "")

                if normalized.isdigit():
                    return int(normalized)

                # Extract first integer found
                match = re.search(r"(\d+)", normalized)
                if match:
                    return int(match.group(1))

            # Fallback to int conversion for other types
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def calculate_library_stats(self, books: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate comprehensive statistics for the library.
        
        Args:
            books: List of parsed book data
            
        Returns:
            Dictionary containing library statistics
        """
        try:
            total_books = len(books)
            
            if total_books == 0:
                return {'total_books': 0, 'message': 'No books in library'}
            
            # Basic counts
            stats = {
                'total_books': total_books,
                'total_duration_minutes': 0,
                'average_rating': 0,
                'books_with_ratings': 0
            }
            
            # Collect data for analysis
            authors = []
            narrators = []
            genres = []
            series = []
            ratings = []
            durations = []
            
            for book in books:
                # Authors
                if book.get('authors'):
                    authors.extend(book['authors'])
                
                # Narrators
                if book.get('narrators'):
                    narrators.extend(book['narrators'])
                
                # Genres
                if book.get('genres'):
                    genres.extend(book['genres'])
                
                # Series
                if book.get('series') and book['series'].get('title'):
                    series.append(book['series']['title'])
                
                # Ratings
                if book.get('rating') is not None:
                    ratings.append(book['rating'])
                
                # Duration
                if book.get('length_minutes'):
                    durations.append(book['length_minutes'])
            
            # Calculate statistics
            stats['total_duration_minutes'] = sum(durations)
            stats['total_duration_hours'] = round(stats['total_duration_minutes'] / 60, 1)
            stats['average_duration_minutes'] = round(sum(durations) / len(durations), 0) if durations else 0
            
            if ratings:
                stats['average_rating'] = round(sum(ratings) / len(ratings), 2)
                stats['books_with_ratings'] = len(ratings)
            
            # Top counts
            stats['unique_authors'] = len(set(authors))
            stats['unique_narrators'] = len(set(narrators))
            stats['unique_genres'] = len(set(genres))
            stats['unique_series'] = len(set(series))
            
            # Top lists
            author_counts = Counter(authors)
            narrator_counts = Counter(narrators)
            genre_counts = Counter(genres)
            series_counts = Counter(series)
            
            stats['top_authors'] = author_counts.most_common(10)
            stats['top_narrators'] = narrator_counts.most_common(10)
            stats['top_genres'] = genre_counts.most_common(10)
            stats['top_series'] = series_counts.most_common(10)
            
            # Rating distribution
            if ratings:
                rating_dist = defaultdict(int)
                for rating in ratings:
                    rating_key = f"{int(rating)}-{int(rating)}.9"
                    rating_dist[rating_key] += 1
                stats['rating_distribution'] = dict(rating_dist)
            
            self.logger.info(
                "Calculated library statistics",
                extra={"book_count": total_books}
            )
            return stats
            
        except Exception as exc:
            self.logger.error(
                "Error calculating library stats",
                extra={"exc": exc}
            )
            return {
                'total_books': len(books) if books else 0,
                'error': str(exc)
            }
    
    def search_books(self, books: List[Dict[str, Any]], query: str, 
                    search_fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search books in the library based on query and fields.
        
        Args:
            books: List of book data to search
            query: Search query string
            search_fields: Fields to search in
            
        Returns:
            List of matching books
        """
        try:
            if not query or not books:
                return []
            
            if search_fields is None:
                search_fields = ['title', 'authors', 'narrators', 'series']
            
            query_lower = query.lower()
            matching_books = []
            
            for book in books:
                match_found = False
                
                for field in search_fields:
                    if self._search_in_field(book, field, query_lower):
                        match_found = True
                        break
                
                if match_found:
                    matching_books.append(book)
            
            self.logger.debug(
                "Completed library search",
                extra={"query": query, "matches": len(matching_books), "fields": search_fields}
            )
            return matching_books
            
        except Exception as exc:
            self.logger.error(
                "Error searching books",
                extra={"query": query, "exc": exc}
            )
            return []
    
    def _search_in_field(self, book: Dict[str, Any], field: str, query: str) -> bool:
        """
        Search for query in a specific book field.
        
        Args:
            book: Book data dictionary
            field: Field name to search in
            query: Search query (already lowercased)
            
        Returns:
            True if query found in field, False otherwise
        """
        try:
            field_value = book.get(field)
            
            if not field_value:
                return False
            
            if isinstance(field_value, str):
                return query in field_value.lower()
            elif isinstance(field_value, list):
                return any(query in str(item).lower() for item in field_value)
            elif isinstance(field_value, dict):
                # For series field
                if field == 'series':
                    series_title = field_value.get('title', '')
                    return query in series_title.lower()
                else:
                    return any(query in str(value).lower() for value in field_value.values())
            else:
                return query in str(field_value).lower()
                
        except Exception:
            return False
