"""
Module Name: audible_library_old.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Legacy Audible library database operations with CRUD, bulk flows, and
    synchronization helpers.

Location:
    /services/database/audible_library_old.py

"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import get_module_logger


class AudibleLibraryOperations:
    """Database operations for Audible library books"""

    def __init__(self, connection_manager, *, logger=None):
        """Initialize audible library database operations."""
        self.connection_manager = connection_manager
        self.logger = logger or get_module_logger("Service.Database.AudibleLibraryLegacy")
        self._db_lock = threading.Lock()
    
    def get_all_books(self, include_metadata: bool = True) -> List[Dict[str, Any]]:
        """
        Get all books from audible library.
        
        Args:
            include_metadata: Whether to include all metadata fields
            
        Returns:
            List of book dictionaries
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            if include_metadata:
                query = """
                    SELECT id, title, author, series, sequence, narrator, runtime, 
                           release_date, language, publisher, overall_rating, rating, 
                           num_ratings, status, asin, summary, cover_image, cover_url,
                           purchase_date, date_added, percent_complete, is_finished,
                           genres, series_title, series_sequence, subtitle, 
                           runtime_length_min, last_synced, created_at, updated_at
                    FROM audible_library 
                    ORDER BY date_added DESC
                """
            else:
                query = """
                    SELECT id, title, author, asin, cover_url, rating, num_ratings
                    FROM audible_library 
                    ORDER BY date_added DESC
                """
                
            cursor.execute(query)
            columns = [description[0] for description in cursor.description]
            books = []
            
            for row in cursor.fetchall():
                book = dict(zip(columns, row))
                # Convert boolean fields
                if 'is_finished' in book and book['is_finished'] is not None:
                    book['is_finished'] = bool(book['is_finished'])
                books.append(book)
            
            conn.close()
            self.logger.debug(f"Retrieved {len(books)} books from audible library")
            return books
            
        except Exception as e:
            self.logger.error(f"Error retrieving audible library books: {e}")
            return []
    
    def get_book_by_asin(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific book by ASIN.
        
        Args:
            asin: The book's ASIN
            
        Returns:
            Book dictionary or None if not found
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            query = """
                SELECT id, title, author, series, sequence, narrator, runtime, 
                       release_date, language, publisher, overall_rating, rating, 
                       num_ratings, status, asin, summary, cover_image, cover_url,
                       purchase_date, date_added, percent_complete, is_finished,
                       genres, series_title, series_sequence, subtitle, 
                       runtime_length_min, last_synced, created_at, updated_at
                FROM audible_library 
                WHERE asin = ?
            """
            
            cursor.execute(query, (asin,))
            row = cursor.fetchone()
            
            if row:
                columns = [description[0] for description in cursor.description]
                book = dict(zip(columns, row))
                # Convert boolean fields
                if book['is_finished'] is not None:
                    book['is_finished'] = bool(book['is_finished'])
                conn.close()
                return book
            
            conn.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving book by ASIN {asin}: {e}")
            return None
    
    def insert_or_update_book(self, book_data: Dict[str, Any]) -> bool:
        """
        Insert a new book or update existing one based on ASIN.
        
        Args:
            book_data: Dictionary containing book information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._db_lock:
                conn, cursor = self.connection_manager.connect_db()
                
                # Check if book exists
                cursor.execute("SELECT id FROM audible_library WHERE asin = ?", (book_data.get('asin'),))
                exists = cursor.fetchone() is not None
                
                current_time = datetime.now().isoformat()
                
                if exists:
                    # Update existing book
                    update_query = """
                        UPDATE audible_library SET
                            title = ?, author = ?, series = ?, sequence = ?, narrator = ?,
                            runtime = ?, release_date = ?, language = ?, publisher = ?,
                            overall_rating = ?, rating = ?, num_ratings = ?, status = ?,
                            summary = ?, cover_image = ?, cover_url = ?, purchase_date = ?,
                            date_added = ?, percent_complete = ?, is_finished = ?, genres = ?,
                            series_title = ?, series_sequence = ?, subtitle = ?, 
                            runtime_length_min = ?, last_synced = ?, updated_at = ?
                        WHERE asin = ?
                    """
                    
                    cursor.execute(update_query, (
                        book_data.get('title'), book_data.get('author'), book_data.get('series'),
                        book_data.get('sequence'), book_data.get('narrator'), book_data.get('runtime'),
                        book_data.get('release_date'), book_data.get('language'), book_data.get('publisher'),
                        book_data.get('overall_rating'), book_data.get('rating'), book_data.get('num_ratings'),
                        book_data.get('status', 'Owned'), book_data.get('summary'), book_data.get('cover_image'),
                        book_data.get('cover_url'), book_data.get('purchase_date'), book_data.get('date_added'),
                        book_data.get('percent_complete', 0.0), book_data.get('is_finished', False),
                        book_data.get('genres'), book_data.get('series_title'), book_data.get('series_sequence'),
                        book_data.get('subtitle'), book_data.get('runtime_length_min'), current_time, current_time,
                        book_data.get('asin')
                    ))
                else:
                    # Insert new book
                    insert_query = """
                        INSERT INTO audible_library (
                            title, author, series, sequence, narrator, runtime, release_date,
                            language, publisher, overall_rating, rating, num_ratings, status,
                            asin, summary, cover_image, cover_url, purchase_date, date_added,
                            percent_complete, is_finished, genres, series_title, series_sequence,
                            subtitle, runtime_length_min, last_synced, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    cursor.execute(insert_query, (
                        book_data.get('title'), book_data.get('author'), book_data.get('series'),
                        book_data.get('sequence'), book_data.get('narrator'), book_data.get('runtime'),
                        book_data.get('release_date'), book_data.get('language'), book_data.get('publisher'),
                        book_data.get('overall_rating'), book_data.get('rating'), book_data.get('num_ratings'),
                        book_data.get('status', 'Owned'), book_data.get('asin'), book_data.get('summary'),
                        book_data.get('cover_image'), book_data.get('cover_url'), book_data.get('purchase_date'),
                        book_data.get('date_added'), book_data.get('percent_complete', 0.0), 
                        book_data.get('is_finished', False), book_data.get('genres'), book_data.get('series_title'),
                        book_data.get('series_sequence'), book_data.get('subtitle'), book_data.get('runtime_length_min'),
                        current_time, current_time, current_time
                    ))
                
                conn.commit()
                conn.close()
                
                action = "Updated" if exists else "Inserted"
                self.logger.debug(f"{action} book: {book_data.get('title', 'Unknown')} (ASIN: {book_data.get('asin')})")
                return True
                
        except Exception as e:
            self.logger.error(f"Error inserting/updating book {book_data.get('asin', 'Unknown')}: {e}")
            return False
    
    def bulk_insert_or_update_books(self, books_data: List[Dict[str, Any]], batch_size: int = 50) -> Tuple[int, int]:
        """
        Efficiently insert or update multiple books using threading.
        
        Args:
            books_data: List of book dictionaries
            batch_size: Number of books to process in each batch
            
        Returns:
            Tuple of (successful_operations, failed_operations)
        """
        successful = 0
        failed = 0
        
        # Process in batches to avoid overwhelming the database
        for i in range(0, len(books_data), batch_size):
            batch = books_data[i:i + batch_size]
            
            with ThreadPoolExecutor(max_workers=min(batch_size // 10 + 1, 4)) as executor:
                futures = {executor.submit(self.insert_or_update_book, book): book for book in batch}
                
                for future in as_completed(futures):
                    try:
                        if future.result():
                            successful += 1
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                        book = futures[future]
                        self.logger.error(f"Failed to process book {book.get('asin', 'Unknown')}: {e}")
        
        self.logger.info(f"Bulk operation completed: {successful} successful, {failed} failed")
        return successful, failed
    
    def get_outdated_books(self, hours_threshold: int = 6) -> List[str]:
        """
        Get ASINs of books that haven't been synced recently.
        
        Args:
            hours_threshold: Hours since last sync to consider outdated
            
        Returns:
            List of ASINs that need updating
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            threshold_time = (datetime.now() - timedelta(hours=hours_threshold)).isoformat()
            
            query = """
                SELECT asin FROM audible_library 
                WHERE last_synced < ? OR last_synced IS NULL
                ORDER BY last_synced ASC
            """
            
            cursor.execute(query, (threshold_time,))
            asins = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            self.logger.debug(f"Found {len(asins)} books needing sync")
            return asins
            
        except Exception as e:
            self.logger.error(f"Error finding outdated books: {e}")
            return []
    
    def delete_book_by_asin(self, asin: str) -> bool:
        """
        Delete a book by ASIN.
        
        Args:
            asin: The book's ASIN
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._db_lock:
                conn, cursor = self.connection_manager.connect_db()
                
                cursor.execute("DELETE FROM audible_library WHERE asin = ?", (asin,))
                deleted_count = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                if deleted_count > 0:
                    self.logger.info(f"Deleted book with ASIN: {asin}")
                    return True
                else:
                    self.logger.warning(f"No book found with ASIN: {asin}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error deleting book {asin}: {e}")
            return False
    
    def get_library_stats(self) -> Dict[str, Any]:
        """
        Get library statistics.
        
        Returns:
            Dictionary with library statistics
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get basic counts
            cursor.execute("SELECT COUNT(*) FROM audible_library")
            total_books = cursor.fetchone()[0]
            
            # Get total runtime
            cursor.execute("SELECT SUM(runtime_length_min) FROM audible_library WHERE runtime_length_min IS NOT NULL")
            total_minutes = cursor.fetchone()[0] or 0
            total_hours = round(total_minutes / 60, 1) if total_minutes else 0
            
            # Get finished books count
            cursor.execute("SELECT COUNT(*) FROM audible_library WHERE is_finished = 1")
            finished_books = cursor.fetchone()[0]
            
            # Get average rating
            cursor.execute("SELECT AVG(CAST(rating AS REAL)) FROM audible_library WHERE rating IS NOT NULL AND rating != ''")
            avg_rating_result = cursor.fetchone()[0]
            avg_rating = round(avg_rating_result, 1) if avg_rating_result else 0
            
            conn.close()
            
            return {
                'total_books': total_books,
                'total_hours': total_hours,
                'finished_books': finished_books,
                'completion_rate': round((finished_books / total_books * 100), 1) if total_books > 0 else 0,
                'average_rating': avg_rating,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting library stats: {e}")
            return {
                'total_books': 0,
                'total_hours': 0,
                'finished_books': 0,
                'completion_rate': 0,
                'average_rating': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def search_books(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search books by title, author, or series.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching books
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            search_query = """
                SELECT id, title, author, series_title, narrator, rating, num_ratings, 
                       asin, cover_url, runtime_length_min
                FROM audible_library 
                WHERE title LIKE ? OR author LIKE ? OR series_title LIKE ? OR narrator LIKE ?
                ORDER BY 
                    CASE 
                        WHEN title LIKE ? THEN 1
                        WHEN author LIKE ? THEN 2
                        WHEN series_title LIKE ? THEN 3
                        ELSE 4
                    END,
                    title
                LIMIT ?
            """
            
            search_term = f"%{query}%"
            cursor.execute(search_query, (
                search_term, search_term, search_term, search_term,
                search_term, search_term, search_term, limit
            ))
            
            columns = [description[0] for description in cursor.description]
            books = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            conn.close()
            return books
            
        except Exception as e:
            self.logger.error(f"Error searching books: {e}")
            return []