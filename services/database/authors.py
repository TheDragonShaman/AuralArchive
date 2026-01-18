"""
Module Name: authors.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Database operations for authors, including overrides and statistics.

Location:
    /services/database/authors.py

"""

import re
from collections import defaultdict
from typing import List, Dict, TYPE_CHECKING, Set, DefaultDict
from .error_handling import error_handler
from utils.logger import get_module_logger

if TYPE_CHECKING:
    from .connection import DatabaseConnection


_AUTHOR_DELIMITER_PATTERN = re.compile(r"\s*(?:,|&|;|\band\b|\bwith\b)\s*", re.IGNORECASE)

BOOK_COLUMN_ORDER = [
    "ID", "Title", "Author", "Series", "Sequence", "Narrator",
    "Runtime", "Release Date", "Language", "Publisher",
    "Overall Rating", "Rating", "num_ratings", "Status", "ASIN",
    "Summary", "Cover Image", "source", "ownership_status", "file_path",
    "Created At", "Updated At", "series_asin", "file_size", "file_format",
    "file_quality", "imported_to_library", "import_date", "naming_template"
]

class AuthorOperations:
    """Handles all author-related database operations"""

    def __init__(self, connection_manager, author_override_operations=None, *, logger=None):
        self.connection_manager = connection_manager
        self.logger = logger or get_module_logger("Service.Database.Authors")
        self.author_override_operations = author_override_operations

    def _normalize_author_name(self, name: str) -> str:
        """Trim whitespace and collapse repeated spacing for consistent comparisons."""
        if not name:
            return ""

        cleaned = str(name).replace("\u00a0", " ")
        normalized = " ".join(cleaned.strip().split())
        return normalized

    def _apply_override_to_name(self, name: str) -> str:
        if not name or not self.author_override_operations:
            return name
        preferred = self.author_override_operations.get_preferred_author_name(name)
        return preferred or name

    def _apply_override_to_book(self, book: Dict):
        if not book or not self.author_override_operations:
            return
        author_value = book.get("Author")
        asin_value = book.get("ASIN")
        preferred = self.author_override_operations.get_preferred_author_name(author_value, asin_value)
        if preferred and preferred != author_value:
            book["Author"] = preferred
            book["author"] = preferred

    def _split_author_field(self, author_value: str) -> List[str]:
        """Split a stored author string into individual author names."""
        if not author_value:
            return []

        if not isinstance(author_value, str):
            author_value = str(author_value)

        parts = _AUTHOR_DELIMITER_PATTERN.split(author_value)
        authors: List[str] = []
        for part in parts:
            normalized = self._normalize_author_name(part)
            if normalized:
                authors.append(self._apply_override_to_name(normalized))
        return authors

    def _author_field_matches(self, author_field: str, target_author: str) -> bool:
        """Check whether a stored author field references the requested author."""
        if not author_field or not target_author:
            return False

        normalized_target = self._apply_override_to_name(
            self._normalize_author_name(target_author)
        ).lower()
        if not normalized_target:
            return False

        for name in self._split_author_field(author_field):
            if name.lower() == normalized_target:
                return True
        return False

    def _build_author_search_terms(self, author: str) -> List[str]:
        terms: List[str] = []
        normalized = self._normalize_author_name(author)
        if normalized:
            terms.append(normalized)

        if self.author_override_operations:
            aliases = self.author_override_operations.get_aliases_for_preferred(author)
            for alias in aliases:
                normalized_alias = self._normalize_author_name(alias)
                if normalized_alias and normalized_alias not in terms:
                    terms.append(normalized_alias)

        return terms if terms else [author]
    
    def get_all_authors(self) -> List[str]:
        """Get all unique authors."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT DISTINCT author 
                FROM books 
                WHERE author IS NOT NULL AND author != '' 
                ORDER BY author COLLATE NOCASE
            """)

            unique_authors: Set[str] = set()
            for (author_field,) in cursor.fetchall():
                for name in self._split_author_field(author_field):
                    unique_authors.add(name)

            authors_list = sorted(unique_authors, key=lambda value: value.lower())
            self.logger.debug("Retrieved unique authors", extra={
                "author_count": len(authors_list)
            })
            return authors_list
        
        except Exception as e:
            self.logger.exception("Error getting all authors", extra={
                "error": str(e)
            })
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_books_by_author(self, author: str) -> List[Dict]:
        """Get all books by a specific author."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            books: List[Dict] = []
            seen_ids: Set[int] = set()
            search_terms = self._build_author_search_terms(author)

            for term in search_terms:
                search_pattern = f"%{term}%"
                cursor.execute(
                    "SELECT * FROM books WHERE author LIKE ? ORDER BY title COLLATE NOCASE",
                    (search_pattern,)
                )
                rows = cursor.fetchall()

                for row in rows:
                    book_id = row[0]
                    if book_id in seen_ids:
                        continue

                    book = dict(zip(BOOK_COLUMN_ORDER, row))
                    if self._author_field_matches(book.get("Author"), author):
                        self._apply_override_to_book(book)
                        books.append(book)
                        seen_ids.add(book_id)

            self.logger.debug("Retrieved books for author", extra={
                "author": author,
                "book_count": len(books),
                "search_terms": search_terms
            })
            return books
        
        except Exception as e:
            self.logger.exception("Error getting books for author", extra={
                "author": author,
                "error": str(e)
            })
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_author_stats(self, author: str) -> Dict:
        """Get comprehensive statistics for a specific author."""
        try:
            books = self.get_books_by_author(author)

            stats = {
                'author': author,
                'total_books': len(books),
                'series_count': 0,
                'status_distribution': {},
                'total_runtime_minutes': 0,
                'average_rating': 0,
                'languages': set(),
                'publishers': set(),
                'date_range': {'earliest': None, 'latest': None}
            }

            total_rating = 0.0
            rated_books = 0
            series_set: Set[str] = set()

            for book in books:
                status_value = book.get('Status') or book.get('ownership_status')
                if status_value:
                    stats['status_distribution'][status_value] = stats['status_distribution'].get(status_value, 0) + 1

                series_name = book.get('Series')
                if series_name and series_name != 'N/A':
                    series_set.add(series_name)

                runtime = book.get('Runtime')
                if runtime:
                    try:
                        if 'hrs' in runtime:
                            parts = runtime.split(' hrs')
                            hours = int(parts[0])
                            minutes = 0
                            if len(parts) > 1 and 'mins' in parts[1]:
                                minutes = int(parts[1].split(' mins')[0].strip())
                            stats['total_runtime_minutes'] += hours * 60 + minutes
                    except Exception:
                        pass

                rating_value = book.get('Overall Rating') or book.get('Rating')
                if rating_value and rating_value != 'N/A':
                    try:
                        total_rating += float(rating_value)
                        rated_books += 1
                    except Exception:
                        pass

                language_value = book.get('Language')
                if language_value:
                    stats['languages'].add(language_value)

                publisher_value = book.get('Publisher')
                if publisher_value:
                    stats['publishers'].add(publisher_value)

                release_date = book.get('Release Date')
                if release_date and release_date != 'Unknown':
                    earliest = stats['date_range']['earliest']
                    latest = stats['date_range']['latest']
                    if not earliest or release_date < earliest:
                        stats['date_range']['earliest'] = release_date
                    if not latest or release_date > latest:
                        stats['date_range']['latest'] = release_date

            stats['series_count'] = len(series_set)
            stats['average_rating'] = round(total_rating / rated_books, 2) if rated_books > 0 else 0
            stats['total_runtime_hours'] = round(stats['total_runtime_minutes'] / 60, 1)
            stats['languages'] = list(stats['languages'])
            stats['publishers'] = list(stats['publishers'])

            self.logger.debug("Calculated author stats", extra={
                "author": author,
                "book_count": stats.get('total_books', 0)
            })
            return stats

        except Exception as e:
            self.logger.exception("Error getting author stats", extra={
                "author": author,
                "error": str(e)
            })
            return {'error': str(e)}
    
    def search_authors(self, query: str) -> List[str]:
        """Search authors by name."""
        try:
            normalized_query = (query or "").strip().lower()
            if not normalized_query:
                return []

            all_authors = self.get_all_authors()
            matched = [name for name in all_authors if normalized_query in name.lower()]
            matched.sort(key=lambda value: value.lower())
            self.logger.debug("Author search completed", extra={
                "query": query,
                "result_count": len(matched)
            })
            return matched

        except Exception as e:
            self.logger.exception("Error searching authors", extra={
                "query": query,
                "error": str(e)
            })
            return []
    
    def get_top_authors_by_book_count(self, limit: int = 10) -> List[Dict]:
        """Get top authors by number of books."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()

            cursor.execute("""
                SELECT author
                FROM books
                WHERE author IS NOT NULL AND author != ''
            """)

            author_counts: DefaultDict[str, int] = defaultdict(int)
            for (author_field,) in cursor.fetchall():
                for name in self._split_author_field(author_field):
                    author_counts[name] += 1

            sorted_authors = sorted(
                author_counts.items(),
                key=lambda item: item[1],
                reverse=True
            )[:limit]

            results = [{'author': name, 'book_count': count} for name, count in sorted_authors]
            self.logger.debug("Retrieved top authors by book count", extra={
                "limit": limit,
                "result_count": len(results)
            })
            return results

        except Exception as e:
            self.logger.exception("Error getting top authors by book count", extra={
                "limit": limit,
                "error": str(e)
            })
            return []

        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_authors_with_series(self) -> List[Dict]:
        """Get authors who have books in series."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT author, series
                FROM books
                WHERE author IS NOT NULL AND author != '' AND series != 'N/A'
            """)

            author_series: DefaultDict[str, Set[str]] = defaultdict(set)
            author_book_counts: DefaultDict[str, int] = defaultdict(int)

            for author_field, series_name in cursor.fetchall():
                if not series_name or series_name == 'N/A':
                    continue

                for name in self._split_author_field(author_field):
                    author_series[name].add(series_name)
                    author_book_counts[name] += 1

            author_entries = [
                {
                    'author': name,
                    'series_count': len(series_set),
                    'total_books': author_book_counts.get(name, 0)
                }
                for name, series_set in author_series.items()
                if series_set
            ]

            author_entries.sort(key=lambda item: (item['series_count'], item['total_books']), reverse=True)
            self.logger.debug("Retrieved authors with series", extra={
                "result_count": len(author_entries)
            })
            return author_entries
        
        except Exception as e:
            self.logger.exception("Error getting authors with series", extra={
                "error": str(e)
            })
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    # Author metadata operations
    
    def get_author_metadata(self, author_name: str) -> Dict:
        """Get author metadata from the authors table."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT * FROM authors WHERE name = ?
            """, (author_name,))
            
            row = cursor.fetchone()
            if row:
                columns = ["id", "name", "audible_author_id", "author_image_url", 
                          "author_bio", "author_page_url", "total_books_count", 
                          "audible_books_count", "last_fetched_at", "created_at", "updated_at"]
                
                metadata = dict(zip(columns, row))
                self.logger.debug("Retrieved author metadata", extra={
                    "author": author_name
                })
                return metadata
            else:
                self.logger.debug("No author metadata found", extra={
                    "author": author_name
                })
                return {}
        
        except Exception as e:
            self.logger.exception("Error getting author metadata", extra={
                "author": author_name,
                "error": str(e)
            })
            return {}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def upsert_author_metadata(self, author_data: Dict) -> bool:
        """Insert or update author metadata."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Check if author exists
            cursor.execute("SELECT id FROM authors WHERE name = ?", (author_data['name'],))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing author
                cursor.execute("""
                    UPDATE authors SET
                        audible_author_id = ?,
                        author_image_url = ?,
                        author_bio = ?,
                        author_page_url = ?,
                        total_books_count = ?,
                        audible_books_count = ?,
                        last_fetched_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE name = ?
                """, (
                    author_data.get('audible_author_id'),
                    author_data.get('author_image_url'),
                    author_data.get('author_bio'),
                    author_data.get('author_page_url'),
                    author_data.get('total_books_count', 0),
                    author_data.get('audible_books_count', 0),
                    author_data['name']
                ))
                self.logger.debug("Updated author metadata", extra={
                    "author": author_data.get('name')
                })
            else:
                # Insert new author
                cursor.execute("""
                    INSERT INTO authors (
                        name, audible_author_id, author_image_url, author_bio,
                        author_page_url, total_books_count, audible_books_count,
                        last_fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    author_data['name'],
                    author_data.get('audible_author_id'),
                    author_data.get('author_image_url'),
                    author_data.get('author_bio'),
                    author_data.get('author_page_url'),
                    author_data.get('total_books_count', 0),
                    author_data.get('audible_books_count', 0)
                ))
                self.logger.debug("Inserted new author metadata", extra={
                    "author": author_data.get('name')
                })
            
            conn.commit()
            return True
        
        except Exception as e:
            self.logger.exception("Error upserting author metadata", extra={
                "author": author_data.get('name'),
                "error": str(e)
            })
            if conn:
                conn.rollback()
            return False
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_authors_needing_refresh(self, hours_threshold: int = 24) -> List[str]:
        """Get list of authors that need metadata refresh from Audible."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get library authors that either don't have metadata or haven't been refreshed recently
            cursor.execute("""
                SELECT DISTINCT b.author
                FROM books b
                LEFT JOIN authors a ON b.author = a.name
                WHERE b.author IS NOT NULL AND b.author != ''
                AND (a.last_fetched_at IS NULL 
                     OR datetime(a.last_fetched_at) < datetime('now', '-{} hours'))
                ORDER BY b.author
            """.format(hours_threshold))
            
            pending_authors: Set[str] = set()
            for (author_field,) in cursor.fetchall():
                for name in self._split_author_field(author_field):
                    pending_authors.add(name)

            author_list = sorted(pending_authors, key=lambda value: value.lower())
            self.logger.debug("Found authors needing metadata refresh", extra={
                "result_count": len(author_list),
                "hours_threshold": hours_threshold
            })
            return author_list
        
        except Exception as e:
            self.logger.exception("Error getting authors needing refresh", extra={
                "hours_threshold": hours_threshold,
                "error": str(e)
            })
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)