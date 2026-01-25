"""
Module Name: audible_library.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    CRUD and bulk operations for the audible_library table (ASIN primary key).

Location:
    /services/database/audible_library.py

"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import get_module_logger


class AudibleLibraryOperations:
    """Database operations for Audible library books with ASIN primary key"""

    def __init__(self, connection_manager, *, logger=None):
        """Initialize audible library database operations."""
        self.connection_manager = connection_manager
        self.logger = logger or get_module_logger("Service.Database.AudibleLibrary")
        self._lock = threading.Lock()
    
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
                    SELECT asin, title, author, authors, narrator, narrators,
                           series_title, series_sequence, publisher, publication_date,
                           release_date, duration_minutes, runtime_length_min, summary,
                           description, genres, tags, language, format, rating,
                           num_ratings, purchase_date, listened, progress, favorite,
                           cover_image_url, local_cover_path, file_path, file_size,
                           added_date, last_updated, metadata_source, sync_status
                    FROM audible_library 
                    ORDER BY last_updated DESC
                """
            else:
                query = """
                    SELECT asin, title, author, narrator, rating, num_ratings,
                           runtime_length_min, series_title, series_sequence
                    FROM audible_library 
                    ORDER BY last_updated DESC
                """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Convert to list of dictionaries
            columns = [description[0] for description in cursor.description]
            books = [dict(zip(columns, row)) for row in results]
            
            conn.close()
            
            self.logger.debug(f"Retrieved {len(books)} books from audible library")
            return books
            
        except Exception as e:
            self.logger.error(f"Error getting all books: {e}")
            return []
    
    def get_book_by_asin(self, asin: str) -> Optional[Dict[str, Any]]:
        """Get a single book by ASIN"""
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT * FROM audible_library WHERE asin = ?", (asin,))
            result = cursor.fetchone()
            
            if result:
                columns = [description[0] for description in cursor.description]
                book = dict(zip(columns, result))
                conn.close()
                return book
            
            conn.close()
            return None
                
        except Exception as e:
            self.logger.error(f"Error getting book by ASIN {asin}: {e}")
            return None
    
    def insert_book(self, book_data: Dict[str, Any]) -> bool:
        """
        Insert a single book into the audible library.
        
        Args:
            book_data: Dictionary containing book information with ASIN as key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not book_data.get('asin'):
                self.logger.error("Cannot insert book without ASIN")
                return False
            
            with self._lock:
                conn, cursor = self.connection_manager.connect_db()
                
                # Build dynamic insert query
                columns = list(book_data.keys())
                placeholders = ['?' for _ in columns]
                values = list(book_data.values())
                
                # Ensure last_updated is set
                if 'last_updated' not in columns:
                    columns.append('last_updated')
                    placeholders.append('?')
                    values.append(datetime.now().isoformat())
                
                query = f"""
                    INSERT OR REPLACE INTO audible_library ({', '.join(columns)}) 
                    VALUES ({', '.join(placeholders)})
                """
                
                cursor.execute(query, values)
                conn.commit()
                conn.close()
                
                self.logger.debug(f"Inserted book with ASIN: {book_data['asin']}")
                
                # Automatically extract and sync series information for this book
                asin = book_data.get('asin')
                if asin:
                    try:
                        from services.service_manager import get_audible_service_manager
                        audible_manager = get_audible_service_manager()
                        
                        # Check if series service is initialized
                        if audible_manager.series_service and audible_manager.series_service.fetcher:
                            # Use the convenience method that handles metadata fetching internally
                            series_result = audible_manager.series_service.sync_book_series_by_asin(asin)
                            
                            if series_result.get('success') and series_result.get('series_count', 0) > 0:
                                series_count = series_result.get('series_count', 0)
                                self.logger.info(f"Auto-synced {series_count} series for Audible book ASIN: {asin}")
                            elif not series_result.get('success'):
                                self.logger.debug(f"Series sync returned: {series_result.get('message', series_result.get('error'))}")
                        else:
                            self.logger.debug("Series service not initialized, skipping auto-sync")
                    except Exception as e:
                        # Don't fail the book insertion if series sync fails
                        self.logger.warning(f"Failed to auto-sync series for ASIN {asin}: {e}")
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error inserting book: {e}")
            return False
    
    def update_book(self, asin: str, book_data: Dict[str, Any]) -> bool:
        """
        Update a book in the audible library.
        
        Args:
            asin: The ASIN of the book to update
            book_data: Dictionary containing updated book information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not book_data:
                return False
            
            with self._lock:
                conn, cursor = self.connection_manager.connect_db()
                
                # Build dynamic update query
                set_clauses = []
                values = []
                
                for key, value in book_data.items():
                    if key != 'asin':  # Don't update the primary key
                        set_clauses.append(f"{key} = ?")
                        values.append(value)
                
                # Always update last_updated
                set_clauses.append("last_updated = ?")
                values.append(datetime.now().isoformat())
                
                # Add ASIN for WHERE clause
                values.append(asin)
                
                query = f"""
                    UPDATE audible_library 
                    SET {', '.join(set_clauses)}
                    WHERE asin = ?
                """
                
                cursor.execute(query, values)
                rows_affected = cursor.rowcount
                conn.commit()
                conn.close()
                
                if rows_affected > 0:
                    self.logger.debug(f"Updated book with ASIN: {asin}")
                    return True
                else:
                    self.logger.warning(f"No book found with ASIN: {asin}")
                    return False
                
        except Exception as e:
            self.logger.error(f"Error updating book {asin}: {e}")
            return False
    
    def delete_book(self, asin: str) -> bool:
        """
        Delete a book from the audible library.
        
        Args:
            asin: The ASIN of the book to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                conn, cursor = self.connection_manager.connect_db()
                cursor.execute("DELETE FROM audible_library WHERE asin = ?", (asin,))
                rows_affected = cursor.rowcount
                conn.commit()
                conn.close()
                
                if rows_affected > 0:
                    self.logger.debug(f"Deleted book with ASIN: {asin}")
                    return True
                else:
                    self.logger.warning(f"No book found with ASIN: {asin}")
                    return False
                
        except Exception as e:
            self.logger.error(f"Error deleting book {asin}: {e}")
            return False
    
    def bulk_insert_or_update_books(self, books: List[Dict[str, Any]], 
                                   max_workers: int = 8) -> Tuple[int, int]:
        """
        Bulk insert or update books using parallel processing.
        
        Args:
            books: List of book dictionaries with ASIN keys
            max_workers: Maximum number of parallel workers
            
        Returns:
            Tuple of (successful_operations, failed_operations)
        """
        if not books:
            return 0, 0
        
        successful = 0
        failed = 0
        
        # Filter books with valid ASINs
        valid_books = [book for book in books if book.get('asin')]
        
        if len(valid_books) != len(books):
            failed = len(books) - len(valid_books)
            self.logger.warning(f"Filtered out {failed} books without valid ASINs")
        
        try:
            # Process books in parallel batches
            batch_size = min(20, max(1, len(valid_books) // max_workers))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit batch operations
                futures = []
                for i in range(0, len(valid_books), batch_size):
                    batch = valid_books[i:i + batch_size]
                    future = executor.submit(self._process_book_batch, batch)
                    futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        batch_successful, batch_failed = future.result()
                        successful += batch_successful
                        failed += batch_failed
                    except Exception as e:
                        self.logger.error(f"Batch processing failed: {e}")
                        failed += len(batch)
            
            self.logger.info(f"Bulk operation completed: {successful} successful, {failed} failed")
            return successful, failed
            
        except Exception as e:
            self.logger.error(f"Error in bulk insert/update: {e}")
            return successful, len(valid_books) - successful
    
    def _process_book_batch(self, books: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Process a batch of books for bulk operations"""
        successful = 0
        failed = 0
        
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            for book in books:
                try:
                    # Build dynamic insert query for each book
                    columns = list(book.keys())
                    placeholders = ['?' for _ in columns]
                    values = list(book.values())
                    
                    # Ensure last_updated is set
                    if 'last_updated' not in columns:
                        columns.append('last_updated')
                        placeholders.append('?')
                        values.append(datetime.now().isoformat())
                    
                    query = f"""
                        INSERT OR REPLACE INTO audible_library ({', '.join(columns)}) 
                        VALUES ({', '.join(placeholders)})
                    """
                    
                    cursor.execute(query, values)
                    successful += 1
                    
                except Exception as e:
                    self.logger.error(f"Error processing book {book.get('asin', 'unknown')}: {e}")
                    failed += 1
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {e}")
            failed += len(books) - successful
        
        return successful, failed
    
    def search_books(self, query: str, fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search books in the audible library.
        
        Args:
            query: Search query string
            fields: List of fields to search in (default: title, author, series)
            
        Returns:
            List of matching book dictionaries
        """
        try:
            if not query.strip():
                return []
            
            if fields is None:
                fields = ['title', 'author', 'authors', 'narrator', 'series_title']
            
            conn, cursor = self.connection_manager.connect_db()
            
            # Build search conditions
            search_conditions = []
            search_values = []
            
            for field in fields:
                search_conditions.append(f"{field} LIKE ?")
                search_values.append(f"%{query}%")
            
            where_clause = " OR ".join(search_conditions)
            
            query_sql = f"""
                SELECT asin, title, author, narrator, rating, num_ratings,
                       runtime_length_min, series_title, series_sequence,
                       cover_image_url, last_updated
                FROM audible_library 
                WHERE {where_clause}
                ORDER BY title ASC
            """
            
            cursor.execute(query_sql, search_values)
            results = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            books = [dict(zip(columns, row)) for row in results]
            
            conn.close()
            
            self.logger.debug(f"Search for '{query}' returned {len(books)} results")
            return books
            
        except Exception as e:
            self.logger.error(f"Error searching books: {e}")
            return []
    
    def get_outdated_books(self, hours: int = 6) -> List[str]:
        """
        Get ASINs of books that need metadata refresh.
        
        Args:
            hours: Number of hours to consider outdated
            
        Returns:
            List of ASINs that need updating
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT asin FROM audible_library 
                WHERE last_updated < ? OR sync_status = 'pending'
                ORDER BY last_updated ASC
            """, (cutoff_time,))
            
            results = cursor.fetchall()
            asins = [row[0] for row in results]
            
            conn.close()
            
            self.logger.debug(f"Found {len(asins)} books needing update (older than {hours} hours)")
            return asins
            
        except Exception as e:
            self.logger.error(f"Error getting outdated books: {e}")
            return []
    
    def get_all_asins(self) -> List[str]:
        """
        Get all ASINs currently in the database.
        
        Returns:
            List of all ASINs in the library
        """
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("SELECT asin FROM audible_library ORDER BY asin")
            results = cursor.fetchall()
            asins = [row[0] for row in results]
            
            conn.close()
            
            self.logger.debug(f"Retrieved {len(asins)} ASINs from database")
            return asins
            
        except Exception as e:
            self.logger.error(f"Error getting all ASINs: {e}")
            return []
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get comprehensive library statistics"""
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get basic counts
            cursor.execute("SELECT COUNT(*) FROM audible_library")
            total_books = cursor.fetchone()[0]
            
            # Get total hours
            cursor.execute("SELECT SUM(runtime_length_min) FROM audible_library WHERE runtime_length_min IS NOT NULL")
            total_minutes = cursor.fetchone()[0] or 0
            total_hours = total_minutes // 60
            
            # Get finished books
            cursor.execute("SELECT COUNT(*) FROM audible_library WHERE listened = 1")
            finished_books = cursor.fetchone()[0]
            
            # Get average rating
            cursor.execute("SELECT AVG(rating) FROM audible_library WHERE rating IS NOT NULL AND rating > 0")
            avg_rating = cursor.fetchone()[0] or 0
            
            # Get last updated time
            cursor.execute("SELECT MAX(last_updated) FROM audible_library")
            last_updated = cursor.fetchone()[0]
            
            conn.close()
            
            completion_rate = (finished_books / total_books * 100) if total_books > 0 else 0
            
            return {
                'total_books': total_books,
                'total_hours': total_hours,
                'finished_books': finished_books,
                'completion_rate': round(completion_rate, 2),
                'average_rating': round(avg_rating, 2) if avg_rating else 0,
                'last_updated': last_updated or datetime.now().isoformat()
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
    
    def cleanup_orphaned_covers(self) -> int:
        """Clean up orphaned cover image files"""
        # This would be implemented to clean up cover files
        # that no longer have corresponding database entries
        try:
            import os
            from services.image_cache.image_cache_service import ImageCacheService
            
            image_cache = ImageCacheService()
            # Implementation would check audible cache directory
            # and remove files not referenced in database
            
            return 0  # Placeholder
            
        except Exception as e:
            self.logger.error(f"Error cleaning up orphaned covers: {e}")
            return 0