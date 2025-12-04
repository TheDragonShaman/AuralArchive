import logging
from typing import List, Dict, Optional, TYPE_CHECKING
from .error_handling import error_handler

if TYPE_CHECKING:
    from .connection import DatabaseConnection

class SeriesOperations:
    """Handles all series-related database operations"""
    
    def __init__(self, connection_manager, author_override_operations=None):
        self.connection_manager = connection_manager
        self.logger = logging.getLogger("DatabaseService.Series")
        self.author_override_operations = author_override_operations

    def _apply_author_override(self, author_name: Optional[str], asin: Optional[str]) -> Optional[str]:
        if not author_name or not self.author_override_operations:
            return author_name
        preferred = self.author_override_operations.get_preferred_author_name(author_name, asin)
        return preferred or author_name
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def upsert_series_metadata(self, series_data: Dict) -> bool:
        """Insert or update series metadata"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                INSERT INTO series_metadata (
                    series_asin, series_title, series_url, sku, sku_lite,
                    total_books, description, cover_url, last_synced, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(series_asin) DO UPDATE SET
                    series_title = excluded.series_title,
                    series_url = excluded.series_url,
                    sku = excluded.sku,
                    sku_lite = excluded.sku_lite,
                    total_books = excluded.total_books,
                    description = excluded.description,
                    cover_url = excluded.cover_url,
                    last_synced = excluded.last_synced,
                    updated_at = datetime('now')
            """, (
                series_data.get('series_asin'),
                series_data.get('series_title'),
                series_data.get('series_url'),
                series_data.get('sku'),
                series_data.get('sku_lite'),
                series_data.get('total_books', 0),
                series_data.get('description'),
                series_data.get('cover_url'),
            ))
            
            conn.commit()
            self.logger.info(f"Upserted series metadata: {series_data.get('series_title')}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error upserting series metadata: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def upsert_series_book(self, series_book_data: Dict) -> bool:
        """Insert or update a book in a series with full metadata"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Check if book exists in main books table
            cursor.execute("SELECT 1 FROM books WHERE asin = ?", (series_book_data.get('book_asin'),))
            in_library = cursor.fetchone() is not None
            
            normalized_author = self._apply_author_override(
                series_book_data.get('author'),
                series_book_data.get('book_asin')
            )

            cursor.execute("""
                INSERT INTO series_books (
                    series_asin, book_asin, book_title, sequence, sort_order,
                    relationship_type, in_library, in_audiobookshelf, 
                    author, narrator, publisher, release_date, runtime,
                    rating, num_ratings, summary, cover_image, language,
                    last_checked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(series_asin, book_asin) DO UPDATE SET
                    book_title = excluded.book_title,
                    sequence = excluded.sequence,
                    sort_order = excluded.sort_order,
                    relationship_type = excluded.relationship_type,
                    in_library = excluded.in_library,
                    author = excluded.author,
                    narrator = excluded.narrator,
                    publisher = excluded.publisher,
                    release_date = excluded.release_date,
                    runtime = excluded.runtime,
                    rating = excluded.rating,
                    num_ratings = excluded.num_ratings,
                    summary = excluded.summary,
                    cover_image = excluded.cover_image,
                    language = excluded.language,
                    last_checked = datetime('now')
            """, (
                series_book_data.get('series_asin'),
                series_book_data.get('book_asin'),
                series_book_data.get('book_title'),
                series_book_data.get('sequence'),
                series_book_data.get('sort_order'),
                series_book_data.get('relationship_type', 'child'),
                in_library,
                series_book_data.get('in_audiobookshelf', False),
                normalized_author,
                series_book_data.get('narrator'),
                series_book_data.get('publisher'),
                series_book_data.get('release_date'),
                series_book_data.get('runtime'),
                series_book_data.get('rating'),
                series_book_data.get('num_ratings'),
                series_book_data.get('summary'),
                series_book_data.get('cover_image'),
                series_book_data.get('language'),
            ))
            
            conn.commit()
            return True
        
        except Exception as e:
            self.logger.error(f"Error upserting series book: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def get_all_series(self) -> List[Dict]:
        """Get all series with statistics"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT 
                    sm.series_asin,
                    sm.series_title,
                    sm.series_url,
                    sm.cover_url,
                    sm.total_books,
                    COUNT(sb.id) as known_books,
                    SUM(CASE WHEN sb.in_library = 1 THEN 1 ELSE 0 END) as owned_books,
                    SUM(CASE WHEN sb.in_audiobookshelf = 1 THEN 1 ELSE 0 END) as downloaded_books,
                    sm.last_synced
                FROM series_metadata sm
                LEFT JOIN series_books sb ON sm.series_asin = sb.series_asin
                GROUP BY sm.series_asin
                ORDER BY sm.series_title ASC
            """)
            
            rows = cursor.fetchall()
            series_list = []
            
            for row in rows:
                raw_total_books = row[4] or 0
                known_books = row[5] or 0
                owned_books = row[6] or 0
                downloaded_books = row[7] or 0

                # Prefer recorded total_books but fall back to known_books so UI percentages work
                total_books = raw_total_books if raw_total_books > 0 else known_books
                effective_total = max(total_books, known_books, owned_books)
                missing_books = max(effective_total - owned_books, 0)
                completion_percentage = 0.0
                if effective_total > 0:
                    completion_percentage = round((owned_books / effective_total) * 100, 1)

                series_list.append({
                    'series_asin': row[0],
                    'series_title': row[1],
                    'series_url': row[2],
                    'cover_url': row[3],
                    'total_books': effective_total,
                    'known_books': known_books,
                    'owned_books': owned_books,
                    'downloaded_books': downloaded_books,
                    'missing_books': missing_books,
                    'completion_percentage': completion_percentage,
                    'last_synced': row[8]
                })
            
            return series_list
        
        except Exception as e:
            self.logger.error(f"Error getting all series: {e}")
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def get_series_by_asin(self, series_asin: str) -> Optional[Dict]:
        """Get series metadata by ASIN"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT * FROM series_metadata WHERE series_asin = ?
            """, (series_asin,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'series_asin': row[0],
                'series_title': row[1],
                'series_url': row[2],
                'sku': row[3],
                'sku_lite': row[4],
                'total_books': row[5],
                'description': row[6],
                'cover_url': row[7],
                'last_synced': row[8],
                'created_at': row[9],
                'updated_at': row[10]
            }
        
        except Exception as e:
            self.logger.error(f"Error getting series by ASIN: {e}")
            return None
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def get_series_books(self, series_asin: str) -> List[Dict]:
        """Get all books in a series"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            self.logger.info(f"Executing query for series_asin: {series_asin}")
            
            cursor.execute("""
                SELECT 
                    sb.book_asin,
                    sb.book_title,
                    sb.sequence,
                    sb.sort_order,
                    sb.in_library,
                    sb.in_audiobookshelf,
                    CASE 
                        WHEN b.file_path IS NOT NULL AND TRIM(b.file_path) != '' THEN 1
                        ELSE 0
                    END as has_local_file,
                    CASE 
                        WHEN b.asin IS NOT NULL THEN 1
                        ELSE 0
                    END as has_library_entry,
                    COALESCE(b.title, sb.book_title) as title,
                    COALESCE(b.author, sb.author) as author,
                    COALESCE(b.narrator, sb.narrator) as narrator,
                    COALESCE(b.runtime, sb.runtime) as runtime,
                    COALESCE(b.rating, sb.rating) as rating,
                    COALESCE(b.num_ratings, sb.num_ratings) as num_ratings,
                    COALESCE(b.release_date, sb.release_date) as release_date,
                    CASE 
                        WHEN sb.cover_image LIKE '/static/cache/%' THEN sb.cover_image
                        WHEN b.cover_image LIKE '/static/cache/%' THEN b.cover_image
                        ELSE COALESCE(sb.cover_image, b.cover_image)
                    END as cover_image,
                    COALESCE(b.publisher, sb.publisher) as publisher,
                    COALESCE(b.summary, sb.summary) as summary
                FROM series_books sb
                LEFT JOIN books b ON sb.book_asin = b.asin
                WHERE sb.series_asin = ?
                ORDER BY CAST(sb.sort_order AS REAL) ASC, COALESCE(b.title, sb.book_title) ASC
            """, (series_asin,))
            
            rows = cursor.fetchall()
            self.logger.info(f"Query returned {len(rows)} rows")
            
            books = []
            
            for row in rows:
                # Use COALESCE values from query (prioritizes books table if in library)
                has_local_file = row[6] == 1
                library_entry_exists = row[7] == 1
                book_title = row[8] if row[8] else f"Book {row[2]}" if row[2] else "Unknown Title"
                library_status = 'in_library' if has_local_file else ('wanted' if library_entry_exists else 'missing')
                
                author_name = row[9] or 'Unknown Author'
                author_name = self._apply_author_override(author_name, row[0]) or author_name

                books.append({
                    'asin': row[0],
                    'title': book_title,
                    'sequence': row[2],
                    'sort_order': row[3],
                    'in_library': has_local_file,
                    'in_audiobookshelf': row[5] == 1,
                    'author': author_name,
                    'narrator': row[10] or 'Unknown Narrator',
                    'runtime': row[11] or 0,
                    'rating': row[12] or '',
                    'num_ratings': row[13] or 0,
                    'release_date': row[14] or '',
                    'cover_image': row[15] or '',
                    'publisher': row[16] or 'Unknown Publisher',
                    'summary': row[17] or 'No summary available',
                    'library_status': library_status
                })
            
            self.logger.info(f"Returning {len(books)} books")
            return books
        
        except Exception as e:
            self.logger.error(f"Error getting series books: {e}", exc_info=True)
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def get_missing_books(self, series_asin: str) -> List[Dict]:
        """Get books in a series that are not in library"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT book_asin, book_title, sequence, sort_order
                FROM series_books
                WHERE series_asin = ? AND in_library = 0
                ORDER BY CAST(sort_order AS REAL) ASC
            """, (series_asin,))
            
            rows = cursor.fetchall()
            missing = []
            
            for row in rows:
                missing.append({
                    'asin': row[0],
                    'title': row[1],
                    'sequence': row[2],
                    'sort_order': row[3]
                })
            
            return missing
        
        except Exception as e:
            self.logger.error(f"Error getting missing books: {e}")
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def update_book_series_asin(self, book_asin: str, series_asin: str) -> bool:
        """Update the series_asin for a book in the books table"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                UPDATE books SET series_asin = ? WHERE asin = ?
            """, (series_asin, book_asin))
            
            conn.commit()
            return True
        
        except Exception as e:
            self.logger.error(f"Error updating book series ASIN: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def sync_library_status(self) -> int:
        """Sync in_library status for all series_books based on books table"""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                UPDATE series_books
                SET in_library = (
                    SELECT CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM books 
                            WHERE books.asin = series_books.book_asin
                              AND file_path IS NOT NULL
                              AND TRIM(file_path) != ''
                        ) THEN 1 ELSE 0 END
                ),
                last_checked = datetime('now')
            """)
            
            updated = cursor.rowcount
            conn.commit()
            self.logger.info(f"Synced library status for {updated} series books")
            return updated
        
        except Exception as e:
            self.logger.error(f"Error syncing library status: {e}")
            if conn:
                conn.rollback()
            return 0
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def get_all_series_asins(self, limit: Optional[int] = None) -> List[str]:
        """
        Get all unique series ASINs from books in the library
        
        Args:
            limit: Optional limit on number of series to return
            
        Returns:
            List of series ASINs
        """
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            query = """
                SELECT DISTINCT series_asin 
                FROM books 
                WHERE series_asin IS NOT NULL 
                AND series_asin != ''
                ORDER BY series_asin
            """
            
            if limit:
                query += f" LIMIT {int(limit)}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            series_asins = [row[0] for row in rows]
            self.logger.info(f"Found {len(series_asins)} unique series in library")
            return series_asins
            
        except Exception as e:
            self.logger.error(f"Error getting series ASINs: {e}")
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)
