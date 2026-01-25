"""
Module Name: syncfromabs.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Sync books from AudioBookShelf into the AuralArchive database with caching and duplicate handling.
Location:
    /services/audiobookshelf/syncfromabs.py

"""
import re
from typing import Dict, List, Optional, Tuple
from utils.logger import get_module_logger

ASIN_PATTERN = re.compile(r"(B[0-9A-Z]{9})", re.IGNORECASE)

class AudioBookShelfSync:
    """Handles syncing books from AudioBookShelf to AuralArchive."""

    def __init__(self, connection, libraries, config_service, logger=None):
        self.connection = connection
        self.libraries = libraries
        self.config_service = config_service
        self.logger = logger or get_module_logger("Service.AudioBookShelf.Sync")
    
    def sync_from_audiobookshelf(self, database_service) -> Tuple[bool, int, str]:
        """Sync books FROM AudioBookShelf TO AuralArchive database."""
        try:
            if not self.config_service.is_audiobookshelf_enabled():
                return False, 0, "AudioBookShelf integration is disabled"
            
            config = self.connection.get_config()
            library_id = config.get('abs_library_id', '')
            
            if not library_id:
                return False, 0, "No AudioBookShelf library selected in configuration"
            
            self.logger.info(
                "Starting sync from AudioBookShelf library",
                extra={"library_id": library_id},
            )
            
            # Get ALL items using pagination
            all_abs_items = self._fetch_all_library_items(library_id)
            if not all_abs_items:
                return False, 0, "No items found in AudioBookShelf library"
            
            # Pre-load existing books for comparison
            existing_books = self._load_existing_books(database_service)
            
            # Process items with reduced logging
            return self._process_sync_items(all_abs_items, existing_books, database_service)
        
        except Exception as exc:
            self.logger.error(
                "Error during AudioBookShelf sync",
                extra={"error": str(exc)},
            )
            return False, 0, f"Sync error: {str(exc)}"
    
    def _fetch_all_library_items(self, library_id: str) -> List[Dict]:
        """Fetch all items from library using limit=0 (no limit)."""
        try:
            # Get all items at once using limit=0 (most efficient for full sync)
            success, all_items, message = self.libraries.get_library_items(library_id, limit=0, page=0)
            
            if success:
                self.logger.info(
                    "Retrieved items from AudioBookShelf",
                    extra={"count": len(all_items)},
                )
                return all_items
            else:
                self.logger.error(
                    "Failed to fetch library items",
                    extra={"message": message},
                )
                return []

        except Exception as exc:
            self.logger.error(
                "Error fetching library items",
                extra={"error": str(exc)},
            )
            return []
    
    def _load_existing_books(self, database_service) -> Dict:
        """Load existing books for efficient comparison."""
        existing_books = database_service.get_all_books()
        
        # Create lookup dictionaries for fast comparison
        existing_asins = {book.get('ASIN'): book for book in existing_books if book.get('ASIN')}
        existing_titles = {(book.get('Title', '').lower(), book.get('Author', '').lower()): book 
                          for book in existing_books}
        
        self.logger.info(
            "Loaded existing books for comparison",
            extra={"count": len(existing_books)},
        )
        
        return {
            'asins': existing_asins,
            'titles': existing_titles
        }
    
    def _process_sync_items(self, all_abs_items: List[Dict], existing_books: Dict, database_service) -> Tuple[bool, int, str]:
        """Process all sync items with reduced logging."""
        added_count = 0
        updated_count = 0
        skipped_count = 0
        duplicate_count = 0
        errors = []
        
        # Progress logging every 25 items instead of 10
        for i, abs_item in enumerate(all_abs_items):
            try:
                if (i + 1) % 25 == 0:
                    self.logger.info(
                        "Processing AudioBookShelf item",
                        extra={"index": i + 1, "total": len(all_abs_items)},
                    )
                
                # Convert AudioBookShelf item to AuralArchive format
                book_data = self._convert_abs_item_to_auralarchive(abs_item)
                if not book_data:
                    skipped_count += 1
                    continue
                
                # Check if book already exists
                existing_book = self._find_existing_book(book_data, existing_books)
                
                if existing_book:
                    # Update existing book status to "Owned"
                    if existing_book.get('Status') != 'Owned':
                        if database_service.update_book_status(existing_book['ID'], 'Owned'):
                            updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    # Add new book with retry logic
                    if self._add_book_with_retry(book_data, database_service, existing_books):
                        added_count += 1
                    else:
                        duplicate_count += 1
                
            except Exception as exc:
                errors.append(f"{abs_item.get('title', 'Unknown')}: {str(exc)}")
        
        # Create summary message
        total_processed = added_count + updated_count
        message_parts = []
        
        if added_count > 0:
            message_parts.append(f"Added {added_count} new books")
        if updated_count > 0:
            message_parts.append(f"updated {updated_count} existing books")
        if skipped_count > 0:
            message_parts.append(f"skipped {skipped_count} items")
        if duplicate_count > 0:
            message_parts.append(f"found {duplicate_count} duplicates")
        
        main_message = ", ".join(message_parts) if message_parts else "No changes made"
        error_summary = f" ({len(errors)} errors)" if errors else ""
        
        full_message = f"Processed {len(all_abs_items)} items: {main_message}{error_summary}"
        self.logger.info(
            "AudioBookShelf sync completed",
            extra={
                "processed": len(all_abs_items),
                "added": added_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "duplicates": duplicate_count,
                "errors": len(errors),
            },
        )
        
        return True, total_processed, full_message
    
    def _find_existing_book(self, book_data: Dict, existing_books: Dict) -> Optional[Dict]:
        """Find if book already exists in database."""
        asin = book_data.get('ASIN', '')
        title = book_data.get('Title', '').lower()
        author = book_data.get('Author', '').lower()
        
        # Check by ASIN first
        if asin and asin in existing_books['asins']:
            return existing_books['asins'][asin]
        
        # Check by title + author
        if (title, author) in existing_books['titles']:
            return existing_books['titles'][(title, author)]
        
        return None
    
    def _add_book_with_retry(self, book_data: Dict, database_service, existing_books: Dict) -> bool:
        """Add book with retry logic for database locks."""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                if database_service.add_book(book_data, status="Owned"):
                    # Update local cache
                    asin = book_data.get('ASIN', '')
                    title = book_data.get('Title', '').lower()
                    author = book_data.get('Author', '').lower()
                    
                    if asin:
                        existing_books['asins'][asin] = book_data
                    existing_books['titles'][(title, author)] = book_data
                    
                    return True
                return False
                
            except Exception as db_error:
                error_msg = str(db_error).lower()
                
                if "unique constraint failed" in error_msg:
                    return False  # Duplicate
                elif "database is locked" in error_msg and attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    return False
        
        return False
    
    def _convert_abs_item_to_auralarchive(self, abs_item: Dict) -> Optional[Dict]:
        """Convert AudioBookShelf library item to AuralArchive book format."""
        try:
            # The item is already formatted by _format_library_item, so we can access fields directly
            title = abs_item.get('title', '').strip()
            if not title:
                self.logger.warning(
                    "AudioBookShelf item has no title",
                    extra={
                        "id": abs_item.get('id', 'Unknown'),
                        "path": abs_item.get('path', 'Unknown'),
                    },
                )
                return None
            
            # Handle authors
            authors = self._extract_authors(abs_item.get('author', ''))
            author_str = ', '.join(authors) if authors else 'Unknown Author'
            
            # Handle narrators
            narrators = self._extract_narrators(abs_item.get('narrator', ''))
            narrator_str = ', '.join(narrators) if narrators else 'Unknown Narrator'
            
            # Handle series
            series_name, series_sequence = self._extract_series_info(abs_item.get('series', ''))
            
            # Calculate runtime
            runtime = self._format_runtime(abs_item.get('duration', 0))
            
            # Format publication date
            release_date = self._format_release_date(
                abs_item.get('publishedDate', '') or abs_item.get('publishedYear', '')
            )
            
            # Handle fields that might be None
            language = abs_item.get('language', '') or 'English'
            publisher = abs_item.get('publisher', '') or 'Unknown Publisher'
            description = abs_item.get('description', '') or 'No summary available.'
            asin = self._normalize_asin_value(abs_item.get('asin'))
            if not asin:
                self.logger.debug(
                    "AudioBookShelf item missing ASIN after extraction",
                    extra={"title": title, "path": abs_item.get('path', 'Unknown')},
                )
            abs_path = abs_item.get('path', '')
            
            return {
                'Title': title,
                'Author': author_str,
                'Series': series_name,
                'Sequence': series_sequence,
                'Narrator': narrator_str,
                'Runtime': runtime,
                'Release Date': release_date,
                'Language': language.strip().capitalize(),
                'Publisher': publisher,
                'Overall Rating': 'N/A',
                'ASIN': asin,
                'Summary': description,
                'Cover Image': abs_item.get('coverPath', '') or self._generate_cover_url(abs_item),
                'Region': 'us',
                'file_path': abs_path,
                'source': 'audiobookshelf',
                'ownership_status': 'owned',
                'Status': 'Owned'
            }
        
        except Exception as exc:
            self.logger.error(
                "Error converting AudioBookShelf item",
                extra={"error": str(exc)},
            )
            return None

    @staticmethod
    def _normalize_asin_value(raw_value: Optional[str]) -> Optional[str]:
        if raw_value is None:
            return None
        candidate = str(raw_value).strip()
        if not candidate:
            return None
        match = ASIN_PATTERN.search(candidate.upper())
        if match:
            return match.group(1).upper()
        if len(candidate) == 10 and candidate.isalnum():
            return candidate.upper()
        return None
    
    def _extract_authors(self, author_data) -> List[str]:
        """Extract author names from various formats."""
        if isinstance(author_data, list):
            return [auth.get('name', '') if isinstance(auth, dict) else str(auth) for auth in author_data]
        elif isinstance(author_data, str):
            return [author_data] if author_data else []
        return []
    
    def _extract_narrators(self, narrator_data) -> List[str]:
        """Extract narrator names from various formats."""
        if isinstance(narrator_data, list):
            return [narr.get('name', '') if isinstance(narr, dict) else str(narr) for narr in narrator_data]
        elif isinstance(narrator_data, str):
            return [narrator_data] if narrator_data else []
        return []
    
    def _extract_series_info(self, series_data) -> Tuple[str, str]:
        """Extract series name and sequence."""
        series_name = 'N/A'
        series_sequence = 'N/A'
        
        if isinstance(series_data, list) and series_data:
            series_info = series_data[0]
            if isinstance(series_info, dict):
                series_name = series_info.get('name', 'N/A')
                series_sequence = str(series_info.get('sequence', 'N/A'))
        elif isinstance(series_data, str) and series_data:
            series_name = series_data
        
        return series_name, series_sequence
    
    def _format_runtime(self, duration_seconds: int) -> str:
        """Format duration in seconds to readable runtime."""
        if duration_seconds:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            return f"{hours} hrs {minutes} mins"
        return "Unknown Runtime"
    
    def _format_release_date(self, published_date) -> str:
        """Format publication date."""
        if published_date:
            if len(str(published_date)) == 4:
                return str(published_date)
            else:
                return str(published_date)[:10]
        return 'Unknown'
    
    def _generate_cover_url(self, abs_item: Dict) -> str:
        """Generate cover URL for AudioBookShelf item."""
        try:
            base_url = self.connection.get_base_url().replace('/api', '')
            item_id = abs_item.get('id', '')
            if item_id and base_url:
                return f"{base_url}/api/items/{item_id}/cover"
        except:
            pass
        return "https://via.placeholder.com/300x400/cccccc/666666?text=No+Cover"