"""
Database Operations - Handles import-related database operations
Manages import tracking in the books table

Location: services/import/database_operations.py
Purpose: Database operations for import tracking
"""

import logging
from typing import Dict, Optional
from datetime import datetime


class ImportDatabaseOperations:
    """
    Handles database operations for import tracking.
    
    Features:
    - Update book import information
    - Query import status
    - Clear import records
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ImportService.DatabaseOperations")
    
    def update_book_import_info(self, asin: str, file_path: str, file_size: int,
                                file_format: str, file_quality: str, naming_template: str,
                                database_service, source_label: str = 'manual_import') -> bool:
        """
        Update book record with import information.
        
        Args:
            asin: Book ASIN
            file_path: Path to imported file
            file_size: File size in bytes
            file_format: File format (M4B, MP3, etc.)
            file_quality: Quality descriptor
            naming_template: Template used for naming
            database_service: DatabaseService instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn, cursor = database_service.connection_manager.connect_db()
            
            # Get current timestamp
            import_date = int(datetime.now().timestamp())
            
            # Update book record
            update_sql = """
                UPDATE books SET
                    file_path = ?,
                    file_size = ?,
                    file_format = ?,
                    file_quality = ?,
                    status = ?,
                    ownership_status = ?,
                    source = ?,
                    imported_to_library = 1,
                    import_date = ?,
                    naming_template = ?
                WHERE asin = ?
            """
            
            cursor.execute(update_sql, (
                file_path,
                file_size,
                file_format,
                file_quality,
                'Owned',
                'owned',
                source_label,
                import_date,
                naming_template,
                asin
            ))
            
            conn.commit()
            
            if cursor.rowcount > 0:
                self.logger.info(f"Updated import info for ASIN: {asin}")
                
                # Sync series library status after successful import
                try:
                    if database_service.series:
                        updated = database_service.series.sync_library_status()
                        self.logger.debug(f"Synced series library status: {updated} records updated")
                except Exception as e:
                    self.logger.warning(f"Failed to sync series library status: {e}")
                
                return True
            else:
                self.logger.warning(f"No book found with ASIN: {asin}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating import info for ASIN {asin}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_book_import_info(self, asin: str, database_service) -> Optional[Dict]:
        """
        Get import information for a book.
        
        Args:
            asin: Book ASIN
            database_service: DatabaseService instance
            
        Returns:
            Dictionary with import info or None if not found
        """
        try:
            conn, cursor = database_service.connection_manager.connect_db()
            
            query_sql = """
                SELECT 
                    file_path,
                    file_size,
                    file_format,
                    file_quality,
                    imported_to_library,
                    import_date,
                    naming_template
                FROM books
                WHERE asin = ?
            """
            
            cursor.execute(query_sql, (asin,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'file_path': row[0],
                    'file_size': row[1],
                    'file_format': row[2],
                    'file_quality': row[3],
                    'imported_to_library': bool(row[4]),
                    'import_date': row[5],
                    'naming_template': row[6]
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting import info for ASIN {asin}: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def clear_book_import_info(self, asin: str, database_service) -> bool:
        """
        Clear import information for a book.
        
        Args:
            asin: Book ASIN
            database_service: DatabaseService instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn, cursor = database_service.connection_manager.connect_db()
            
            # Clear import fields
            update_sql = """
                UPDATE books SET
                    file_path = NULL,
                    file_size = NULL,
                    file_format = NULL,
                    file_quality = NULL,
                    imported_to_library = 0,
                    import_date = NULL,
                    naming_template = NULL
                WHERE asin = ?
            """
            
            cursor.execute(update_sql, (asin,))
            conn.commit()
            
            if cursor.rowcount > 0:
                self.logger.info(f"Cleared import info for ASIN: {asin}")
                return True
            else:
                self.logger.warning(f"No book found with ASIN: {asin}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error clearing import info for ASIN {asin}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_all_imported_books(self, database_service) -> list:
        """
        Get all books that have been imported.
        
        Args:
            database_service: DatabaseService instance
            
        Returns:
            List of dictionaries with book and import information
        """
        try:
            conn, cursor = database_service.connection_manager.connect_db()
            
            query_sql = """
                SELECT 
                    asin,
                    title,
                    author,
                    file_path,
                    file_size,
                    file_format,
                    file_quality,
                    import_date,
                    naming_template
                FROM books
                WHERE imported_to_library = 1
                ORDER BY import_date DESC
            """
            
            cursor.execute(query_sql)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'asin': row[0],
                    'title': row[1],
                    'author': row[2],
                    'file_path': row[3],
                    'file_size': row[4],
                    'file_format': row[5],
                    'file_quality': row[6],
                    'import_date': row[7],
                    'naming_template': row[8]
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error getting imported books: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_import_statistics(self, database_service) -> Dict:
        """
        Get statistics about imported books.
        
        Args:
            database_service: DatabaseService instance
            
        Returns:
            Dictionary with import statistics
        """
        try:
            conn, cursor = database_service.connection_manager.connect_db()
            
            stats = {
                'total_imported': 0,
                'total_size_bytes': 0,
                'formats': {},
                'recent_imports': []
            }
            
            # Get total count and size
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(file_size), 0)
                FROM books
                WHERE imported_to_library = 1
            """)
            row = cursor.fetchone()
            if row:
                stats['total_imported'] = row[0]
                stats['total_size_bytes'] = row[1]
            
            # Get format breakdown
            cursor.execute("""
                SELECT file_format, COUNT(*)
                FROM books
                WHERE imported_to_library = 1
                GROUP BY file_format
            """)
            for row in cursor.fetchall():
                if row[0]:
                    stats['formats'][row[0]] = row[1]
            
            # Get 5 most recent imports
            cursor.execute("""
                SELECT title, author, import_date
                FROM books
                WHERE imported_to_library = 1
                ORDER BY import_date DESC
                LIMIT 5
            """)
            stats['recent_imports'] = [
                {'title': row[0], 'author': row[1], 'import_date': row[2]}
                for row in cursor.fetchall()
            ]
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting import statistics: {e}")
            return {
                'total_imported': 0,
                'total_size_bytes': 0,
                'formats': {},
                'recent_imports': []
            }
        finally:
            if conn:
                conn.close()
