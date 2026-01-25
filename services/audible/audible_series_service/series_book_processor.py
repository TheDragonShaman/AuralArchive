"""
Module Name: series_book_processor.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Process series book metadata, deduplicate editions, and mark library status before database sync.
Location:
    /services/audible/audible_series_service/series_book_processor.py

"""

from utils.logger import get_module_logger


class SeriesBookProcessor:
    """Processes series book data for storage."""
    
    def __init__(self, db_service, logger=None):
        """
        Initialize with database service
        
        Args:
            db_service: DatabaseService instance
        """
        self.logger = logger or get_module_logger("Service.Audible.Series.BookProcessor")
        self.db = db_service
    
    def process_series_books(self, series_asin, books_data):
        """
        Process series books and determine library status
        
        Args:
            series_asin: The series ASIN
            books_data: List of book dicts from Audible API with full metadata
            
        Returns:
            list: Processed book dicts with library status and complete metadata
        """
        try:
            # Filter unbuyable titles first so at least one purchasable edition stays in each slot
            filtered_books = [book for book in books_data if self._is_buyable(book)]

            if not filtered_books:
                self.logger.info(
                    "All series entries filtered out due to unavailable titles",
                    extra={"series_asin": series_asin, "incoming": len(books_data)},
                )
                return []

            # Deduplicate remaining editions (post-filter) to keep the best candidate per slot
            books_data = self._deduplicate_books(filtered_books)
            
            processed_books = []
            
            for book in books_data:
                if not self._is_buyable(book):
                    self.logger.debug(
                        "Skipping unbuyable series title",
                        extra={"title": book.get('title'), "asin": book.get('asin')},
                    )
                    continue
                
                book_asin = book.get('asin')
                
                # Check if book is in our library
                in_library = self._check_in_library(book_asin)
                in_audiobookshelf = self._check_in_audiobookshelf(book_asin)
                
                processed_book = {
                    'series_asin': series_asin,
                    'book_asin': book_asin,
                    'book_title': book.get('title', 'Unknown'),
                    'sequence': book.get('sequence', ''),
                    'sort_order': book.get('sort_order', 0),
                    'in_library': in_library,
                    'in_audiobookshelf': in_audiobookshelf,
                    # Add all metadata fields
                    'author': book.get('author', 'Unknown Author'),
                    'narrator': book.get('narrator', 'Unknown Narrator'),
                    'publisher': book.get('publisher', 'Unknown Publisher'),
                    'release_date': book.get('release_date', ''),
                    'runtime': book.get('runtime', 0),
                    'rating': book.get('rating', ''),
                    'num_ratings': book.get('num_ratings', 0),
                    'summary': book.get('summary', 'No summary available'),
                    'cover_image': book.get('cover_image', ''),
                    'language': book.get('language', 'en')
                }
                
                processed_books.append(processed_book)
            
            self.logger.info(
                "Processed books for series",
                extra={"series_asin": series_asin, "count": len(processed_books)},
            )
            return processed_books
            
        except Exception as e:
            self.logger.error(
                "Error processing series books",
                extra={"series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return []

    def _is_buyable(self, book):
        """Determine whether a book can still be purchased on Audible."""
        try:
            customer_rights = book.get('customer_rights') or {}
            is_buyable = book.get('is_buyable')
            if is_buyable is None:
                is_buyable = customer_rights.get('is_buyable')

            if is_buyable is False:
                return False

            product_state = book.get('product_state') or customer_rights.get('product_state')
            if product_state:
                normalized = str(product_state).strip().upper()
                unavailable_states = {
                    'NOT_FOR_SALE',
                    'NO_LONGER_AVAILABLE',
                    'UNAVAILABLE',
                    'UNAVAILABLE_FOR_PURCHASE',
                    'REMOVED',
                    'WITHDRAWN',
                    'ARCHIVED'
                }
                if normalized in unavailable_states:
                    return False

            return True

        except Exception as exc:
            self.logger.debug(
                "Failed to evaluate buyable state",
                extra={"asin": book.get('asin'), "error": str(exc)},
            )
            return True
    
    def _deduplicate_books(self, books_data):
        """
        Remove duplicate book entries from series data
        Audible sometimes returns multiple editions (ISBN, ASIN, regional variants)
        
        Strategy:
        1. Group by title + sequence
        2. For each group, prefer Audible ASINs (B0...) over ISBNs (numeric)
        3. If multiple Audible ASINs, prefer the shortest/most recent one
        
        Args:
            books_data: List of book dicts
            
        Returns:
            list: Deduplicated book dicts
        """
        try:
            if not books_data:
                return []
            
            # Group books by normalized title and sequence
            groups = {}
            for book in books_data:
                title = book.get('title', '').strip()
                sequence = str(book.get('sequence', '')).strip()
                
                # Create a key that ignores minor title variations
                # Normalize by removing common subtitle patterns
                normalized_title = self._normalize_title(title)
                key = (normalized_title, sequence)
                
                if key not in groups:
                    groups[key] = []
                groups[key].append(book)
            
            # For each group, select the best book entry
            deduplicated = []
            for key, book_group in groups.items():
                if len(book_group) == 1:
                    deduplicated.append(book_group[0])
                else:
                    # Multiple entries - choose the best one
                    best_book = self._select_best_edition(book_group)
                    deduplicated.append(best_book)
                    
                    # Log duplicates found
                    asins = [b.get('asin') for b in book_group]
                    self.logger.debug(
                        "Deduplicated editions",
                        extra={
                            "normalized_title": key[0],
                            "sequence": key[1],
                            "kept_asin": best_book.get('asin'),
                            "skipped": [a for a in asins if a != best_book.get('asin')],
                        },
                    )
            
            if len(deduplicated) < len(books_data):
                self.logger.debug(
                    "Deduplication reduced book count",
                    extra={
                        "before": len(books_data),
                        "after": len(deduplicated),
                        "removed": len(books_data) - len(deduplicated),
                    },
                )
            
            return deduplicated
            
        except Exception as e:
            self.logger.error("Error deduplicating books", extra={"error": str(e)}, exc_info=True)
            return books_data  # Return original if deduplication fails
    
    def _normalize_title(self, title):
        """
        Normalize book title for comparison
        Removes common subtitle variations and punctuation differences
        """
        import re
        
        # Convert to lowercase
        normalized = title.lower()
        
        # Remove common subtitle patterns after colon, dash, or parentheses
        # e.g., "Title: A Cultivation Novel" → "title"
        normalized = re.split(r'[:\-\(]', normalized)[0]
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        # Remove trailing punctuation
        normalized = normalized.strip(' .,;!?')
        
        return normalized
    
    def _select_best_edition(self, book_group):
        """
        Select the best edition from a group of duplicate books
        
        Preference order:
        1. Most recent release date (newer editions/remasters)
        2. Audible ASIN format (starts with 'B0', 10 chars) over ISBNs (numeric, 10-13 chars)
        3. Book with metadata (title != 'Unknown')
        4. Longest/most complete title
        
        Args:
            book_group: List of duplicate book dicts
            
        Returns:
            dict: The best book entry to keep
        """
        # Prefer buyable entries when possible
        buyable_books = [b for b in book_group if self._is_buyable(b)]
        candidate_pool = buyable_books if buyable_books else book_group

        def score_book(book):
            """Score a book for selection - higher is better"""
            asin = book.get('asin', '')
            title = book.get('title', 'Unknown')
            release_date = book.get('release_date', '')
            
            score = 0

            # Strong preference for buyable editions
            if self._is_buyable(book):
                score += 500
            else:
                score -= 500
            
            # Highest priority: Release date (newer is better)
            # Parse YYYY-MM-DD format and convert to score
            if release_date:
                try:
                    # Extract year from date string (YYYY-MM-DD)
                    year = int(release_date.split('-')[0])
                    # More recent years get higher scores (e.g., 2024 = +2024 points)
                    score += year
                except (ValueError, IndexError):
                    pass
            
            # Prefer Audible ASINs (B0XXXXXXXX format)
            if asin.startswith('B0') and len(asin) == 10:
                score += 100
            elif asin.startswith('B') and len(asin) == 10:
                score += 50
            # Penalize ISBNs (numeric)
            elif asin.isdigit():
                score -= 100
            
            # Prefer books with actual metadata
            if title and title != 'Unknown':
                score += 20
            
            # Prefer longer/more complete titles (likely has subtitle/edition info)
            score += len(title) * 0.1
            
            # Prefer books with metadata fields populated
            if book.get('author') and book.get('author') != 'Unknown Author':
                score += 10
            if book.get('narrator') and book.get('narrator') != 'Unknown Narrator':
                score += 10
            if book.get('cover_image'):
                score += 5
            if book.get('runtime') and book.get('runtime', 0) > 0:
                score += 5
            
            return score
        
        # Sort by score (highest first) and return the best
        sorted_books = sorted(candidate_pool, key=score_book, reverse=True)
        return sorted_books[0]
    
    def _check_in_library(self, book_asin):
        """Check if book exists in our database"""
        try:
            conn, cursor = self.db.connect_db()
            cursor.execute(
                "SELECT file_path FROM books WHERE asin = ? LIMIT 1",
                (book_asin,)
            )
            result = cursor.fetchone()
            conn.close()
            if not result:
                return False
            file_path = result[0]
            if file_path is None:
                return False
            return str(file_path).strip() != ''
        except Exception as e:
            self.logger.error(
                "Error checking library status",
                extra={"book_asin": book_asin, "error": str(e)},
                exc_info=True,
            )
            return False
    
    def _check_in_audiobookshelf(self, book_asin):
        """Check if book exists in AudiobookShelf"""
        try:
            conn, cursor = self.db.connect_db()
            # Check if the column exists first, or just skip this check for now
            # The column might not exist in all database schemas
            cursor.execute(
                "SELECT 1 FROM books WHERE asin = ? LIMIT 1",
                (book_asin,)
            )
            result = cursor.fetchone()
            conn.close()
            # For now, just return False since we don't have this column yet
            # TODO: Add in_audiobookshelf column check when available
            return False
        except Exception as e:
            self.logger.debug(
                "AudiobookShelf status check skipped",
                extra={"book_asin": book_asin, "error": str(e)},
            )
            return False
    
    def calculate_series_stats(self, processed_books):
        """
        Calculate statistics for a series
        
        Args:
            processed_books: List of processed book dicts
            
        Returns:
            dict: Statistics including total, owned, missing counts
        """
        try:
            total = len(processed_books)
            owned = sum(1 for b in processed_books if b.get('in_library'))
            in_abs = sum(1 for b in processed_books if b.get('in_audiobookshelf'))
            missing = total - owned
            
            return {
                'total_books': total,
                'owned_books': owned,
                'books_in_audiobookshelf': in_abs,
                'missing_books': missing,
                'completion_percentage': (owned / total * 100) if total > 0 else 0
            }
        except Exception as e:
            self.logger.error("Error calculating series stats", extra={"error": str(e)}, exc_info=True)
            return {
                'total_books': 0,
                'owned_books': 0,
                'books_in_audiobookshelf': 0,
                'missing_books': 0,
                'completion_percentage': 0
            }
