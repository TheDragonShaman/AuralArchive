"""
Module Name: filename_matcher.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Extracts ASIN identifiers from filenames and provides lightweight
    search helpers to locate matching books in the database. Serves as the
    first-pass matcher before deeper metadata inspection.

Location:
    /services/import_service/filename_matcher.py

"""

import os
import re
from typing import Dict, List, Optional, Tuple

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Import.FilenameMatcher")


class FilenameMatcher:
    """
    Matches audiobook filenames to database entries.
    
    Primary: ASIN extraction from filename
    Fallback: Search functionality for manual selection
    """
    
    def __init__(self, *, logger=None):
        self.logger = logger or _LOGGER
        
        # ASIN pattern - matches [B0XXXXXXXXX] format
        self.asin_pattern = re.compile(r'\[([B][A-Z0-9]{9})\]')
    
    def extract_asin_from_filename(self, filename: str) -> Optional[str]:
        """
        Extract ASIN from filename if present.
        
        Args:
            filename: Name of the file
            
        Returns:
            ASIN string or None
        """
        match = self.asin_pattern.search(filename)
        if match:
            asin = match.group(1)
            self.logger.info(f"Extracted ASIN from filename: {asin}")
            return asin
        
        self.logger.warning(f"No ASIN found in filename: {filename}")
        return None
    
    def clean_title_for_search(self, filename: str) -> str:
        """
        Clean a filename to extract searchable title.
        
        Args:
            filename: File to clean
            
        Returns:
            Clean title for searching
        """
        # Remove file extension
        title = os.path.splitext(filename)[0]
        
        # Remove ASIN if present
        title = self.asin_pattern.sub('', title)
        
        # Remove other bracketed/parenthesized content
        title = re.sub(r'\[.*?\]', '', title)
        title = re.sub(r'\(.*?\)', '', title)
        
        # Replace underscores and multiple dashes with spaces
        title = title.replace('_', ' ')
        title = re.sub(r'-+', ' ', title)
        
        # Normalize whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        
        return title
    
    def search_books_by_title(self, search_term: str, database_service, limit: int = 10) -> List[Dict]:
        """
        Search for books matching a title.
        
        Args:
            search_term: Title to search for
            database_service: Database service instance
            limit: Maximum results to return
            
        Returns:
            List of matching books
        """
        try:
            search_lower = search_term.lower()
            all_books = database_service.get_all_books()
            
            matches = []
            for book in all_books:
                title = book.get('Title', '')
                if search_lower in title.lower():
                    matches.append(book)
                    if len(matches) >= limit:
                        break
            
            self.logger.info(f"Found {len(matches)} books matching '{search_term}'")
            return matches
            
        except Exception as e:
            self.logger.error(f"Error searching books: {e}")
            return []
    
    def get_book_by_asin(self, asin: str, database_service) -> Optional[Dict]:
        """
        Get book from database by ASIN.
        
        Args:
            asin: Book ASIN
            database_service: Database service instance
            
        Returns:
            Book dict or None
        """
        try:
            book = database_service.get_book_by_asin(asin)
            
            if book:
                self.logger.info(f"Found book: {book.get('Title')} by {book.get('AuthorName')}")
                return book
            else:
                self.logger.warning(f"No book found with ASIN: {asin}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting book by ASIN: {e}")
            return None
