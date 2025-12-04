import logging
import threading
from typing import List, Dict, Optional, TYPE_CHECKING, Any, Tuple, Set
from .error_handling import error_handler

if TYPE_CHECKING:
    from .connection import DatabaseConnection

class BookOperations:
    """Handles all book-related database operations"""
    
    def __init__(self, connection_manager, author_override_operations=None):
        self.connection_manager = connection_manager
        self.logger = logging.getLogger("DatabaseService.Books")
        self._series_sync_lock = threading.Lock()
        self._pending_series_sync: Set[str] = set()
        self._series_worker_threads: Set[threading.Thread] = set()
        self.author_override_operations = author_override_operations

    def _normalize_lookup_value(self, value: Optional[str]) -> str:
        return (value or '').strip().lower()

    def _sanitize_asin_value(self, asin_value: Optional[str]) -> Optional[str]:
        if asin_value is None:
            return None
        asin_str = str(asin_value).strip()
        if not asin_str or asin_str.upper() == 'N/A':
            return None
        return asin_str

    def _should_merge_source(self, source: Optional[str], ownership_status: Optional[str]) -> bool:
        source_value = (source or '').strip().lower()
        ownership_value = (ownership_status or '').strip().lower()
        return source_value in ('audible', 'audible_library') or ownership_value == 'audible_library'

    def _find_existing_book_by_title_author(self, cursor, title: Optional[str], author: Optional[str]) -> Optional[Dict[str, Any]]:
        normalized_title = self._normalize_lookup_value(title)
        if not normalized_title or normalized_title == 'unknown title':
            return None
        normalized_author = self._normalize_lookup_value(author)

        cursor.execute(
            """
                SELECT id, asin, source, ownership_status, status
                FROM books
                WHERE lower(title) = ? AND lower(COALESCE(author, '')) = ?
                LIMIT 1
            """,
            (normalized_title, normalized_author)
        )
        row = cursor.fetchone()
        if not row:
            return None
        keys = ['id', 'asin', 'source', 'ownership_status', 'status']
        return dict(zip(keys, row))

    def _prepare_db_row_from_book_data(self, book_data: Dict[str, Any], status: str) -> Tuple[Dict[str, Any], Optional[str]]:
        asin_clean = self._sanitize_asin_value(book_data.get('ASIN'))
        language_value = book_data.get('Language', 'Unknown Language')

        db_row = {
            'title': book_data.get('Title', 'Unknown Title'),
            'author': book_data.get('Author', 'Unknown Author'),
            'series': book_data.get('Series', 'N/A'),
            'sequence': book_data.get('Sequence', 'N/A'),
            'narrator': book_data.get('Narrator', 'Unknown Narrator'),
            'runtime': book_data.get('Runtime', 'Unknown Runtime'),
            'release_date': book_data.get('Release Date', 'Unknown Release Date'),
            'language': language_value,
            'publisher': book_data.get('Publisher', 'Unknown Publisher'),
            'overall_rating': book_data.get('Overall Rating', 'N/A'),
            'rating': book_data.get('Rating', 'No rating'),
            'status': status,
            'asin': asin_clean if asin_clean else 'N/A',
            'summary': book_data.get('Summary', 'No summary available'),
            'cover_image': book_data.get('Cover Image', ''),
            'num_ratings': book_data.get('num_ratings', 0),
            'series_asin': book_data.get('series_asin') or book_data.get('Series ASIN'),
            'source': book_data.get('source', 'manual'),
            'ownership_status': book_data.get('ownership_status', 'wanted'),
            'file_path': book_data.get('file_path')
        }

        return db_row, asin_clean

    def _merge_book_record(self, cursor, existing_record: Dict[str, Any], update_data: Dict[str, Any]) -> bool:
        allowed_columns = [
            'title', 'author', 'series', 'sequence', 'narrator', 'runtime', 'release_date',
            'language', 'publisher', 'overall_rating', 'rating', 'num_ratings', 'status',
            'asin', 'summary', 'cover_image', 'series_asin', 'source', 'ownership_status', 'file_path'
        ]

        set_clauses = []
        values: List[Any] = []

        for column in allowed_columns:
            if column not in update_data:
                continue
            value = update_data[column]
            if value is None:
                continue

            if column == 'asin':
                sanitized_asin = self._sanitize_asin_value(value)
                if not sanitized_asin:
                    continue
                existing_asin = self._sanitize_asin_value(existing_record.get('asin'))
                if existing_asin and existing_asin != sanitized_asin:
                    self.logger.debug(
                        "Skipping ASIN update for book ID %s due to mismatch (existing=%s, new=%s)",
                        existing_record.get('id'), existing_asin, sanitized_asin
                    )
                    continue
                value = sanitized_asin

            set_clauses.append(f"{column} = ?")
            values.append(value)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE books SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values + [existing_record['id']])

        if cursor.rowcount > 0:
            self.logger.info(
                "Updated existing book '%s' (ID %s) with Audible metadata",
                update_data.get('title', existing_record.get('id')),
                existing_record.get('id')
            )
            return True
        return False

    def _try_merge_existing_book_by_title(self, cursor, update_data: Dict[str, Any]) -> bool:
        existing = self._find_existing_book_by_title_author(
            cursor,
            update_data.get('title'),
            update_data.get('author')
        )
        if not existing:
            return False
        return self._merge_book_record(cursor, existing, update_data)

    def _apply_author_overrides(self, book: Dict[str, Any]):
        """If an override exists for the book's author, update the record in-place."""
        if not book or not self.author_override_operations:
            return

        author_value = book.get('Author') or book.get('author')
        asin_value = book.get('ASIN') or book.get('asin')
        if not author_value:
            return

        preferred = self.author_override_operations.get_preferred_author_name(author_value, asin_value)
        if preferred and preferred != author_value:
            book['Author'] = preferred
            book['author'] = preferred
            if 'AuthorName' in book:
                book['AuthorName'] = preferred
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def check_book_exists(self, asin: str) -> bool:
        """Check if a book with the given ASIN exists."""
        if not asin or asin.strip() == '' or asin == 'N/A':
            return False
        
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT 1 FROM books WHERE asin = ? LIMIT 1", (asin,))
            exists = cursor.fetchone() is not None
            
            self.logger.debug(f"Book existence check for ASIN {asin}: {exists}")
            return exists
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def add_book(self, book_data: Dict, status: str = "Wanted") -> bool:
        """Add a book to the database."""
        if not error_handler.validate_required_fields(book_data, ['Title']):
            return False
        
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            db_row, asin_clean = self._prepare_db_row_from_book_data(book_data, status)
            asin_for_series = asin_clean

            if self._should_merge_source(db_row.get('source'), db_row.get('ownership_status')):
                existing_match = self._find_existing_book_by_title_author(cursor, db_row.get('title'), db_row.get('author'))
                if existing_match and self._merge_book_record(cursor, existing_match, db_row):
                    conn.commit()
                    return True
            
            # Check for duplicate ASIN before insert
            if asin_clean:
                cursor.execute(
                    "SELECT id, asin, source, ownership_status, status FROM books WHERE asin = ? LIMIT 1",
                    (asin_clean,)
                )
                duplicate = cursor.fetchone()
                if duplicate:
                    keys = ['id', 'asin', 'source', 'ownership_status', 'status']
                    existing_record = dict(zip(keys, duplicate))
                    if self._merge_book_record(cursor, existing_record, db_row):
                        conn.commit()
                        return True
                    self.logger.warning(
                        f"Book with ASIN {asin_clean} already exists, skipping: {book_data.get('Title', 'Unknown')}"
                    )
                    return False
            
            # Extract series_asin if present in book_data
            series_asin = db_row.get('series_asin')
            
            # Insert book
            insert_sql = """
                INSERT INTO books (
                    title, author, series, sequence, narrator, runtime, 
                    release_date, language, publisher, overall_rating, 
                    rating, status, asin, summary, cover_image, num_ratings, series_asin,
                    source, ownership_status, file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            values = (
                db_row.get('title'),
                db_row.get('author'),
                db_row.get('series'),
                db_row.get('sequence'),
                db_row.get('narrator'),
                db_row.get('runtime'),
                db_row.get('release_date'),
                db_row.get('language'),
                db_row.get('publisher'),
                db_row.get('overall_rating'),
                db_row.get('rating'),
                db_row.get('status'),
                db_row.get('asin'),
                db_row.get('summary'),
                db_row.get('cover_image'),
                db_row.get('num_ratings'),
                series_asin,
                db_row.get('source'),
                db_row.get('ownership_status'),
                db_row.get('file_path')
            )
            
            cursor.execute(insert_sql, values)
            conn.commit()
            
            error_handler.log_operation("Book added", f"'{book_data.get('Title')}' with status '{status}'")
            
            # Cache the book cover image if available
            cover_image_url = book_data.get('Cover Image') or book_data.get('cover_image')
            if cover_image_url:
                try:
                    from services.image_cache import cache_book_cover
                    cached_cover_url = cache_book_cover(cover_image_url)
                    if cached_cover_url:
                        self.logger.debug(f"Cached book cover for '{book_data.get('Title')}': {cover_image_url}")
                except Exception as e:
                    self.logger.warning(f"Failed to cache book cover for '{book_data.get('Title')}': {e}")
            
            # Process author contributors for author metadata updates
            try:
                from routes.authors import process_book_contributors_for_authors
                author_results = process_book_contributors_for_authors(book_data)
                if author_results:
                    self.logger.info(f"Processed {len(author_results)} author(s) from book contributors")
            except Exception as e:
                self.logger.warning(f"Failed to process author contributors: {e}")
            
            # Automatically extract and sync series information for this book
            if asin_for_series:
                try:
                    from services.service_manager import get_audible_service_manager
                    audible_manager = get_audible_service_manager()
                    
                    # Check if series service is initialized
                    if audible_manager.series_service and audible_manager.series_service.fetcher:
                        # Use the convenience method that handles metadata fetching internally
                        series_result = audible_manager.series_service.sync_book_series_by_asin(asin_for_series)
                        
                        if series_result.get('success') and series_result.get('series_count', 0) > 0:
                            series_count = series_result.get('series_count', 0)
                            self.logger.info(f"Auto-synced {series_count} series for book '{book_data.get('Title')}'")
                        elif not series_result.get('success'):
                            self.logger.debug(f"Series sync returned: {series_result.get('message', series_result.get('error'))}")
                    else:
                        self.logger.debug("Series service not initialized, skipping auto-sync")
                except Exception as e:
                    # Don't fail the book addition if series sync fails
                    self.logger.warning(f"Failed to auto-sync series for '{book_data.get('Title')}': {e}")
            
            return True
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def bulk_insert_or_update_books(self, books: List[Dict[str, Any]], 
                                   max_workers: int = 8) -> Tuple[int, int]:
        """
        Bulk insert or update books using parallel processing.
        Designed for Audible sync - sets source='audible' and ownership_status='audible_library'.
        
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
        series_sync_candidates: List[str] = []
        
        # Filter books with valid ASINs
        valid_books = [book for book in books if book.get('asin')]
        
        if len(valid_books) != len(books):
            failed = len(books) - len(valid_books)
            self.logger.warning(f"Filtered out {failed} books without valid ASINs")
        
        try:
            # Process books in parallel batches
            from concurrent.futures import ThreadPoolExecutor, as_completed
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
                        batch_successful, batch_failed, batch_candidates = future.result()
                        successful += batch_successful
                        failed += batch_failed
                        if batch_candidates:
                            series_sync_candidates.extend(batch_candidates)
                    except Exception as e:
                        self.logger.error(f"Batch processing failed: {e}")
                        failed += len(batch)
            
            self.logger.info(f"Bulk operation completed: {successful} successful, {failed} failed")
            if series_sync_candidates:
                self._queue_series_sync(series_sync_candidates)
            return successful, failed
            
        except Exception as e:
            self.logger.error(f"Error in bulk insert/update: {e}")
            return successful, len(valid_books) - successful
    
    def _process_book_batch(self, books: List[Dict[str, Any]]) -> Tuple[int, int, List[str]]:
        """Process a batch of books for bulk operations"""
        successful = 0
        failed = 0
        missing_series_asins: List[str] = []
        
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            for book in books:
                try:
                    # Map Audible API field names to database column names
                    field_mapping = {
                        'asin': 'asin',
                        'title': 'title',
                        'author': 'author',
                        'authors': 'author',  # Use authors if author not present
                        'narrator': 'narrator',
                        'runtime_length_min': 'runtime',
                        'release_date': 'release_date',
                        'language': 'language',
                        'publisher': 'publisher',
                        'rating': 'overall_rating',  # Primary rating column
                        'num_ratings': 'num_ratings',
                        'summary': 'summary',
                        'cover_image_url': 'cover_image',
                        'series_title': 'series',
                        'series_sequence': 'sequence',
                        'series_asin': 'series_asin',
                        'status': 'status',
                        'Status': 'status',
                        'source': 'source',
                        'ownership_status': 'ownership_status'
                    }
                    
                    # Build mapped data for database
                    db_data = {}
                    for api_field, db_field in field_mapping.items():
                        if api_field in book and book[api_field] is not None:
                            db_data[db_field] = book[api_field]
                    
                    # Populate both rating columns with same value for consistency
                    if 'rating' in book and book['rating'] is not None:
                        db_data['overall_rating'] = book['rating']
                        db_data['rating'] = book['rating']
                    
                    # Required fields with defaults
                    asin = book.get('asin')
                    db_data['asin'] = asin
                    db_data['title'] = book.get('title') or book.get('Title', 'Unknown Title')
                    db_data['author'] = book.get('author') or book.get('authors') or book.get('Author', 'Unknown Author')
                    
                    # Set Audible-specific fields
                    ownership_status = db_data.get('ownership_status') or book.get('ownership_status')
                    if not ownership_status:
                        ownership_status = 'audible_library'
                    db_data['ownership_status'] = ownership_status

                    source_value = db_data.get('source') or book.get('source') or 'audible'
                    db_data['source'] = source_value

                    status_value = db_data.get('status') or book.get('status') or book.get('Status')
                    if not status_value:
                        status_value = 'Owned (Audible)' if ownership_status == 'audible_library' else 'Wanted'
                    db_data['status'] = status_value

                    # Preserve existing series_asin if new payload lacks it
                    series_candidate = False
                    if asin:
                        if not db_data.get('series_asin'):
                            cursor.execute(
                                "SELECT series_asin FROM books WHERE asin = ? LIMIT 1",
                                (asin,)
                            )
                            existing_series = cursor.fetchone()
                            if existing_series and existing_series[0]:
                                db_data['series_asin'] = existing_series[0]
                            else:
                                series_candidate = True
                        elif db_data.get('series_asin') in ('', None):
                            series_candidate = True
                    else:
                        series_candidate = False

                    should_merge = self._should_merge_source(
                        db_data.get('source'),
                        db_data.get('ownership_status')
                    )

                    if should_merge and self._try_merge_existing_book_by_title(cursor, db_data):
                        successful += 1
                        if series_candidate and asin:
                            missing_series_asins.append(asin)
                        continue
                    
                    # Use INSERT OR REPLACE to handle duplicates by ASIN
                    columns = list(db_data.keys())
                    placeholders = ['?' for _ in columns]
                    values = list(db_data.values())
                    
                    query = f"""
                        INSERT OR REPLACE INTO books ({', '.join(columns)}) 
                        VALUES ({', '.join(placeholders)})
                    """
                    
                    cursor.execute(query, values)
                    successful += 1
                    if series_candidate and asin:
                        missing_series_asins.append(asin)
                    
                except Exception as e:
                    self.logger.error(f"Error processing book {book.get('asin', 'unknown')}: {e}")
                    failed += 1
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {e}")
            failed += len(books) - successful
        
        return successful, failed, missing_series_asins

    def _queue_series_sync(self, asins: List[str]):
        """Queue ASINs for background series synchronization."""
        if not asins:
            return
        filtered = [asin for asin in asins if isinstance(asin, str) and asin.strip()]
        if not filtered:
            return
        new_asins: List[str] = []
        with self._series_sync_lock:
            for asin in filtered:
                asin = asin.strip()
                if asin and asin not in self._pending_series_sync:
                    self._pending_series_sync.add(asin)
                    new_asins.append(asin)
        if not new_asins:
            return
        worker = threading.Thread(
            target=self._run_series_sync_worker,
            args=(new_asins,),
            daemon=True
        )
        self._series_worker_threads.add(worker)
        worker.start()

    def _run_series_sync_worker(self, asins: List[str]):
        """Background worker to sync series metadata for provided ASINs."""
        try:
            from services.service_manager import (
                get_audible_service_manager,
                get_database_service
            )
        except Exception as import_error:
            self.logger.error(f"Unable to import services for series sync: {import_error}")
            with self._series_sync_lock:
                for asin in asins:
                    self._pending_series_sync.discard(asin)
            return
        try:
            db_service = get_database_service()
            audible_manager = get_audible_service_manager()
            if not audible_manager or not db_service:
                self.logger.warning("Series sync skipped: services unavailable")
                return
            if not audible_manager.initialize_series_service(db_service):
                self.logger.warning("Series sync skipped: Audible series service not initialized")
                return
            for asin in asins:
                try:
                    result = audible_manager.series_service.sync_book_series_by_asin(asin)
                    if not result.get('success'):
                        self.logger.debug(
                            f"Series sync failed for {asin}: {result.get('error', result.get('message'))}"
                        )
                except Exception as e:
                    self.logger.warning(f"Error syncing series for {asin}: {e}")
                finally:
                    with self._series_sync_lock:
                        self._pending_series_sync.discard(asin)
        finally:
            thread = threading.current_thread()
            with self._series_sync_lock:
                self._series_worker_threads.discard(thread)
    
    def get_all_books(self) -> List[Dict]:
        """Get all books from the database."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT * FROM books ORDER BY title COLLATE NOCASE")
            rows = cursor.fetchall()
            
            # Column order MUST match the actual database schema (29 columns total)
            columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator", 

                              "Runtime", "Release Date", "Language", "Publisher", 

                              "Overall Rating", "Rating", "num_ratings", "Status", "ASIN", 

                              "Summary", "Cover Image", "source", "ownership_status", 

                              "file_path", "Created At", "Updated At", "series_asin",

                              "file_size", "file_format", "file_quality", "imported_to_library",

                              "import_date", "naming_template"]
            
            books = []
            for row in rows:
                book = dict(zip(columns, row))
                self._apply_author_overrides(book)
                books.append(book)
            self.logger.debug(f"Retrieved {len(books)} books from database")
            return books
        
        except Exception as e:
            self.logger.error(f"Error getting all books: {e}")
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_recent_books(self, limit: int = 6) -> List[Dict]:
        """Get the most recently updated or added books."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute(
                """
                    SELECT * FROM books
                    ORDER BY datetime(COALESCE(updated_at, created_at, '1970-01-01')) DESC
                    LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()

            columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator",

                              "Runtime", "Release Date", "Language", "Publisher",

                              "Overall Rating", "Rating", "num_ratings", "Status", "ASIN",

                              "Summary", "Cover Image", "source", "ownership_status",

                              "file_path", "Created At", "Updated At", "series_asin",

                              "file_size", "file_format", "file_quality", "imported_to_library",

                              "import_date", "naming_template"]

            books = []
            for row in rows:
                book = dict(zip(columns, row))
                self._apply_author_overrides(book)
                books.append(book)
            self.logger.debug(f"Retrieved {len(books)} recent books from database")
            return books

        except Exception as e:
            self.logger.error(f"Error getting recent books: {e}")
            return []

        finally:
            error_handler.handle_connection_cleanup(conn)

    def get_book_by_asin(self, asin: str) -> Optional[Dict]:
        """Get a specific book by ASIN."""
        if not asin or asin.strip() == '' or asin == 'N/A':
            return None
            
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT * FROM books WHERE asin = ?", (asin,))
            book = cursor.fetchone()
            
            if book:
                columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator", 

                                  "Runtime", "Release Date", "Language", "Publisher", 

                                  "Overall Rating", "Rating", "num_ratings", "Status", "ASIN", 

                                  "Summary", "Cover Image", "source", "ownership_status", 

                                  "file_path", "Created At", "Updated At", "series_asin",

                                  "file_size", "file_format", "file_quality", "imported_to_library",

                                  "import_date", "naming_template"]
                result = dict(zip(columns, book))
                self._apply_author_overrides(result)
                
                # Add alternate field names for compatibility
                result['AuthorName'] = result.get('Author')
                result['SeriesName'] = result.get('Series')
                result['book_number'] = result.get('Sequence')
                result['narrator_name'] = result.get('Narrator')
                result['release_date'] = result.get('Release Date')
                result['publisher_name'] = result.get('Publisher')
                result['asin'] = result.get('ASIN')
                result['runtime_length_min'] = result.get('Runtime')
                
                self.logger.debug(f"Retrieved book by ASIN {asin}: {result.get('Title')}")
                return result
            else:
                self.logger.warning(f"Book not found with ASIN: {asin}")
                return None
        
        except Exception as e:
            self.logger.error(f"Error getting book by ASIN {asin}: {e}")
            return None
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_book_by_id(self, book_id: int) -> Optional[Dict]:
        """Get a specific book by ID."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            
            if book:
                columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator", 

                                  "Runtime", "Release Date", "Language", "Publisher", 

                                  "Overall Rating", "Rating", "num_ratings", "Status", "ASIN", 

                                  "Summary", "Cover Image", "source", "ownership_status", 

                                  "file_path", "Created At", "Updated At", "series_asin",

                                  "file_size", "file_format", "file_quality", "imported_to_library",

                                  "import_date", "naming_template"]
                result = dict(zip(columns, book))
                self._apply_author_overrides(result)
                self.logger.debug(f"Retrieved book ID {book_id}: {result.get('Title')}")
                return result
            else:
                self.logger.warning(f"Book not found with ID: {book_id}")
                return None
        
        except Exception as e:
            self.logger.error(f"Error getting book by ID {book_id}: {e}")
            return None
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    @error_handler.with_retry(max_retries=3, retry_delay=0.5)
    def update_book_status(self, book_id: int, new_status: str) -> bool:
        """Update a book's status."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            update_sql = """
                UPDATE books 
                SET status = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """
            cursor.execute(update_sql, (new_status, book_id))
            conn.commit()
            
            if cursor.rowcount > 0:
                error_handler.log_operation("Book status updated", f"ID {book_id} to '{new_status}'")
                return True
            else:
                self.logger.warning(f"No book found with ID {book_id}")
                return False
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def delete_book(self, book_id: int) -> bool:
        """Delete a book from the database."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()
            
            if cursor.rowcount > 0:
                error_handler.log_operation("Book deleted", f"ID {book_id}")
                return True
            else:
                self.logger.warning(f"No book found with ID {book_id}")
                return False
        
        except Exception as e:
            self.logger.error(f"Error deleting book ID {book_id}: {e}")
            return False
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def search_books(self, query: str) -> List[Dict]:
        """Search books by title, author, or series."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            search_pattern = f"%{query}%"
            
            search_sql = """
                SELECT * FROM books 
                WHERE title LIKE ? OR author LIKE ? OR series LIKE ?
                ORDER BY title COLLATE NOCASE
            """
            cursor.execute(search_sql, (search_pattern, search_pattern, search_pattern))
            rows = cursor.fetchall()
            
            columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator", 

            
                              "Runtime", "Release Date", "Language", "Publisher", 

            
                              "Overall Rating", "Rating", "num_ratings", "Status", "ASIN", 

            
                              "Summary", "Cover Image", "source", "ownership_status", 

            
                              "file_path", "Created At", "Updated At", "series_asin",

            
                              "file_size", "file_format", "file_quality", "imported_to_library",

            
                              "import_date", "naming_template"]
            
            books = []
            for row in rows:
                book = dict(zip(columns, row))
                self._apply_author_overrides(book)
                books.append(book)
            self.logger.debug(f"Search for '{query}' returned {len(books)} results")
            return books
        
        except Exception as e:
            self.logger.error(f"Error searching books with query '{query}': {e}")
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_books_by_status(self, status: str) -> List[Dict]:
        """Get all books with a specific status."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute("SELECT * FROM books WHERE status = ? ORDER BY title COLLATE NOCASE", (status,))
            rows = cursor.fetchall()
            
            columns = ["ID", "Title", "Author", "Series", "Sequence", "Narrator", 

            
                              "Runtime", "Release Date", "Language", "Publisher", 

            
                              "Overall Rating", "Rating", "num_ratings", "Status", "ASIN", 

            
                              "Summary", "Cover Image", "source", "ownership_status", 

            
                              "file_path", "Created At", "Updated At", "series_asin",

            
                              "file_size", "file_format", "file_quality", "imported_to_library",

            
                              "import_date", "naming_template"]
            
            books = []
            for row in rows:
                book = dict(zip(columns, row))
                self._apply_author_overrides(book)
                books.append(book)
            self.logger.debug(f"Retrieved {len(books)} books with status '{status}'")
            return books
        
        except Exception as e:
            self.logger.error(f"Error getting books by status '{status}': {e}")
            return []
        
        finally:
            error_handler.handle_connection_cleanup(conn)
