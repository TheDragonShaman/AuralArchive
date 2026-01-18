"""
Module Name: database_updates.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Handles database update operations for the metadata service, including
    validation, sanitization, and persistence of refreshed metadata.

Location:
    /services/metadata/database_updates.py

"""

from typing import Dict, Tuple, List
from .error_handling import error_handler
from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Metadata.DatabaseUpdates")

class MetadataDatabaseUpdates:
    """Handles database update operations for metadata service"""
    
    def __init__(self, database_service, *, logger=None):
        self.database_service = database_service
        self.logger = logger or _LOGGER
    
    def update_book_in_database(self, book_id: int, fresh_metadata: Dict, current_status: str) -> Tuple[bool, str]:
        """Update book in database with fresh metadata"""
        try:
            error_handler.log_update_attempt(book_id, "Database update", f"Updating with fresh metadata")
            
            # Validate the fresh metadata first
            is_valid, validation_message = error_handler.validate_book_data(fresh_metadata)
            if not is_valid:
                return False, f"Invalid metadata: {validation_message}"
            
            # Sanitize metadata to prevent database issues
            sanitized_metadata = error_handler.sanitize_metadata(fresh_metadata)
            
            # Get database connection
            conn, cursor = self.database_service.connect_db()
            
            try:
                # Use the exact column names from database schema
                update_query = """
                    UPDATE books SET
                        title = ?,
                        author = ?,
                        series = ?,
                        sequence = ?,
                        narrator = ?,
                        runtime = ?,
                        release_date = ?,
                        language = ?,
                        publisher = ?,
                        overall_rating = ?,
                        rating = ?,
                        status = ?,
                        asin = ?,
                        summary = ?,
                        cover_image = ?,
                        num_ratings = ?,
                        series_asin = ?
                    WHERE id = ?
                """
                
                # Extract values from sanitized metadata
                # NOTE: normalize_metadata_to_db_format() returns lowercase/snake_case keys
                # Try both capitalized (from Audible API formatter) and normalized (from metadata processor) keys
                
                # Helper function to get value with fallback to capitalized key
                def get_metadata_value(normalized_key, capitalized_key, default):
                    return sanitized_metadata.get(normalized_key) or sanitized_metadata.get(capitalized_key) or default
                
                series_asin_value = sanitized_metadata.get('series_asin')
                
                values = (
                    get_metadata_value('title', 'Title', 'Unknown Title'),
                    get_metadata_value('author', 'Author', 'Unknown Author'),
                    get_metadata_value('series_title', 'Series', 'N/A'),
                    get_metadata_value('series_sequence', 'Sequence', 'N/A'),
                    get_metadata_value('narrator', 'Narrator', 'Unknown Narrator'),
                    get_metadata_value('runtime_length_min', 'Runtime', 'Unknown Runtime'),
                    get_metadata_value('release_date', 'Release Date', 'Unknown'),
                    get_metadata_value('language', 'Language', 'Unknown'),
                    get_metadata_value('publisher', 'Publisher', 'Unknown Publisher'),
                    get_metadata_value('rating', 'Overall Rating', 'N/A'),  # For overall_rating column
                    get_metadata_value('rating', 'Overall Rating', 'N/A'),  # For rating column  
                    current_status,  # Preserve the user's current status
                    sanitized_metadata.get('asin') or sanitized_metadata.get('ASIN', ''),  # Update ASIN too in case it was missing
                    get_metadata_value('summary', 'Summary', 'No summary available'),
                    get_metadata_value('cover_image_url', 'Cover Image', ''),
                    sanitized_metadata.get('num_ratings', 0),  # Use lowercase
                    series_asin_value,  # Add series_asin
                    book_id
                )
                
                self.logger.debug(
                    "Executing book update",
                    extra={"book_id": book_id, "param_count": len(values)},
                )
                cursor.execute(update_query, values)
                rows_affected = cursor.rowcount
                
                conn.commit()
                
                if rows_affected > 0:
                    # Process contributor metadata for author updates after successful save
                    try:
                        from routes.authors import process_book_contributors_for_authors
                        author_results = process_book_contributors_for_authors(fresh_metadata)
                        if author_results:
                            self.logger.info(
                                "Processed contributor authors during metadata update",
                                extra={"book_id": book_id, "authors_processed": len(author_results)},
                            )
                    except Exception as contributor_error:
                        self.logger.warning(
                            "Author contributor processing failed",
                            extra={"book_id": book_id, "error": str(contributor_error)},
                            exc_info=True,
                        )

                    success_message = "Successfully updated book in database"
                    self.logger.info(success_message, extra={"book_id": book_id, "rows_affected": rows_affected})
                    error_handler.log_update_result(book_id, True, success_message)
                    return True, success_message
                else:
                    error_message = "No rows updated for book"
                    self.logger.warning(error_message, extra={"book_id": book_id})
                    error_handler.log_update_result(book_id, False, error_message)
                    return False, error_message
                    
            finally:
                conn.close()
                
        except Exception as e:
            error_message = "Database update failed"
            self.logger.error(
                error_message,
                extra={"book_id": book_id, "error": str(e)},
                exc_info=True,
            )
            error_handler.log_update_result(book_id, False, error_message)
            
            # Try to close connection if it exists
            try:
                if 'conn' in locals():
                    conn.close()
            except:
                pass
            
            return False, error_message
    
    def get_book_from_database(self, book_id: int) -> Tuple[bool, Dict, str]:
        """Retrieve book data from database for updating"""
        try:
            error_handler.log_update_attempt(book_id, "Database retrieval", "Fetching current book data")
            
            book = self.database_service.get_book_by_id(book_id)
            
            if not book:
                error_message = "Book not found in database"
                self.logger.warning(error_message, extra={"book_id": book_id})
                return False, {}, error_message
            
            # Validate essential fields
            title = book.get('Title', '').strip()
            if not title:
                error_message = "Book missing title"
                self.logger.error(
                    error_message,
                    extra={"book_id": book_id},
                    exc_info=True,
                )
                return False, book, error_message
            
            success_message = "Successfully retrieved book"
            self.logger.debug(success_message, extra={"book_id": book_id, "title": title})
            return True, book, success_message
            
        except Exception as e:
            error_message = "Error retrieving book from database"
            self.logger.error(
                error_message,
                extra={"book_id": book_id, "error": str(e)},
                exc_info=True,
            )
            return False, {}, error_message
    
    def backup_book_data(self, book_id: int, book_data: Dict) -> bool:
        """Create a backup of book data before updating (for potential rollback)"""
        try:
            # This could be implemented to store backup data
            # For now, we'll just log the current state
            self.logger.info(
                "Backup snapshot created",
                extra={
                    "book_id": book_id,
                    "title": book_data.get('Title', 'Unknown'),
                    "author": book_data.get('Author', 'Unknown'),
                },
            )
            
            # In a full implementation, this might:
            # 1. Store in a backup table
            # 2. Write to backup files
            # 3. Store in a versioning system
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Error backing up book data",
                extra={"book_id": book_id, "error": str(e)},
                exc_info=True,
            )
            return False
    
    def validate_database_connection(self) -> Tuple[bool, str]:
        """Validate that database connection is working"""
        try:
            if not self.database_service:
                return False, "No database service available"
            
            # Test connection
            conn, cursor = self.database_service.connect_db()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return True, "Database connection successful"
            else:
                return False, "Database connection test failed"
                
        except Exception as e:
            return False, f"Database connection error: {str(e)}"
    
    def get_update_statistics(self) -> Dict[str, int]:
        """Get statistics about recent updates (placeholder for future implementation)"""
        try:
            # This could query a log table or analyze recent database changes
            # For now, return placeholder data
            return {
                'total_updates_today': 0,
                'successful_updates': 0,
                'failed_updates': 0,
                'books_needing_updates': 0
            }
            
        except Exception as e:
            self.logger.error(
                "Error getting update statistics",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {'error': str(e)}
    
    def find_books_needing_metadata_updates(self, limit: int = 100) -> List[Dict]:
        """Find books that might need metadata updates"""
        try:
            # Look for books with minimal or potentially outdated metadata
            all_books = self.database_service.get_all_books()
            
            books_needing_updates = []
            
            for book in all_books:
                needs_update = False
                
                # Check for missing or minimal data
                if (book.get('Summary') in ['No summary available', '', None] or
                    book.get('Cover Image') in ['', None] or
                    book.get('Overall Rating') in ['N/A', '', None] or
                    book.get('Runtime') in ['Unknown Runtime', '', None]):
                    needs_update = True
                
                # Check for generic placeholder values
                if (book.get('Author') == 'Unknown Author' or
                    book.get('Narrator') == 'Unknown Narrator' or
                    book.get('Publisher') == 'Unknown Publisher'):
                    needs_update = True
                
                if needs_update:
                    books_needing_updates.append(book)
                    
                    if len(books_needing_updates) >= limit:
                        break
            
            self.logger.info(
                "Found books needing metadata updates",
                extra={"count": len(books_needing_updates), "limit": limit},
            )
            return books_needing_updates
            
        except Exception as e:
            self.logger.error(
                "Error finding books needing updates",
                extra={"error": str(e)},
                exc_info=True,
            )
            return []
    
    def update_multiple_books(self, book_updates: List[Tuple[int, Dict, str]]) -> Dict[str, int]:
        """Update multiple books in a batch operation"""
        try:
            results = {
                'successful': 0,
                'failed': 0,
                'total': len(book_updates)
            }
            
            self.logger.info(
                "Starting batch metadata update",
                extra={"total": results['total']},
            )
            
            for book_id, metadata, status in book_updates:
                try:
                    success, message = self.update_book_in_database(book_id, metadata, status)
                    if success:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        self.logger.warning(
                            "Batch update failed",
                            extra={"book_id": book_id, "error": message},
                        )
                        
                except Exception as e:
                    results['failed'] += 1
                    self.logger.error(
                        "Error in batch update",
                        extra={"book_id": book_id, "error": str(e)},
                        exc_info=True,
                    )
            
            self.logger.info(
                "Batch update completed",
                extra={"successful": results['successful'], "failed": results['failed']},
            )
            return results
            
        except Exception as e:
            self.logger.error(
                "Error in batch update operation",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {'successful': 0, 'failed': len(book_updates), 'total': len(book_updates), 'error': str(e)}

# This will be instantiated by the main service with dependency injection