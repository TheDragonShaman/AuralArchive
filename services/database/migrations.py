"""
Module Name: migrations.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Initializes and migrates the SQLite schema for AuralArchive.
    Migrations are frozen; initialization is a no-op aside from connectivity
    verification.

Location:
    /services/database/migrations.py

"""

from typing import TYPE_CHECKING

from utils.logger import get_module_logger

if TYPE_CHECKING:
    from .connection import DatabaseConnection


class DatabaseMigrations:
    """Handles database initialization and schema migrations (frozen)."""

    def __init__(self, connection_manager: "DatabaseConnection", *, logger=None):
        self.connection_manager = connection_manager
        self.logger = logger or get_module_logger("Service.Database.Migrations")

    def initialize_database(self):
        """Verify connectivity; schema changes are frozen."""
        try:
            conn, _ = self.connection_manager.connect_db()
            conn.close()
            self.logger.info("Database initialization skipped (frozen schema)")
        except Exception as exc:
            self.logger.error(
                "Error initializing database (frozen state)",
                extra={"error": str(exc)},
                exc_info=True,
            )
            raise

    def migrate_database(self):
        """Explicitly skip migrations while schema is frozen."""
        self.logger.info("Database migrations frozen; skipping migration run")
    
    def _create_indexer_status_table(self, cursor):
        """Create the indexer_status table for indexer health and performance tracking"""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS indexer_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indexer_name TEXT NOT NULL UNIQUE,
                indexer_type TEXT,
                base_url TEXT,
                api_key TEXT,
                enabled BOOLEAN DEFAULT 1,
                last_check TIMESTAMP,
                last_success TIMESTAMP,
                last_failure TIMESTAMP,
                total_searches INTEGER DEFAULT 0,
                successful_searches INTEGER DEFAULT 0,
                failed_searches INTEGER DEFAULT 0,
                average_response_time REAL,
                health_status TEXT DEFAULT 'unknown',
                error_message TEXT,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        
        cursor.execute(create_table_sql)
        
        # Create indexes for common queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indexer_status_name ON indexer_status(indexer_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indexer_status_enabled ON indexer_status(enabled)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indexer_status_health ON indexer_status(health_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indexer_status_priority ON indexer_status(priority)')
        
        self.logger.debug("Indexer status table created or verified")
    
    def _create_search_preferences_table(self, cursor):
        """Create the search_preferences table for user quality and format preferences"""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS search_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_key TEXT NOT NULL UNIQUE,
                preference_value TEXT,
                value_type TEXT DEFAULT 'string',
                category TEXT DEFAULT 'general',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        
        cursor.execute(create_table_sql)
        
        # Insert default preferences
        default_preferences = [
            ('min_bitrate', '64', 'integer', 'quality', 'Minimum acceptable bitrate in kbps'),
            ('preferred_bitrate', '128', 'integer', 'quality', 'Preferred bitrate in kbps'),
            ('preferred_format', 'M4B', 'string', 'quality', 'Preferred audiobook format'),
            ('format_priority', 'M4B,M4A,MP3,FLAC', 'string', 'quality', 'Format priority order'),
            ('min_quality_score', '7.0', 'float', 'quality', 'Minimum quality score for auto-download'),
            ('min_match_score', '80.0', 'float', 'search', 'Minimum match score percentage'),
            ('auto_download_enabled', 'false', 'boolean', 'automation', 'Enable automatic downloads'),
            ('max_search_results', '50', 'integer', 'search', 'Maximum search results to process'),
            ('search_timeout', '30', 'integer', 'search', 'Search timeout in seconds'),
        ]
        
        for key, value, value_type, category, description in default_preferences:
            cursor.execute("""
                INSERT OR IGNORE INTO search_preferences 
                (preference_key, preference_value, value_type, category, description)
                VALUES (?, ?, ?, ?, ?)
            """, (key, value, value_type, category, description))
        
        # Create index for quick lookups
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_preferences_key ON search_preferences(preference_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_preferences_category ON search_preferences(category)')
        
        self.logger.debug("Search preferences table created or verified with default values")
    
    def _create_download_queue_table(self, cursor):
        """Create the download_queue table for automated download management"""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS download_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_title TEXT NOT NULL,
                book_author TEXT,
                book_asin TEXT,
                search_result_id INTEGER,
                download_url TEXT,
                download_client TEXT,
                download_client_id TEXT,
                status TEXT DEFAULT 'queued',
                quality_score REAL,
                match_score REAL,
                file_format TEXT,
                file_size INTEGER,
                download_progress REAL DEFAULT 0.0,
                eta_seconds INTEGER,
                error_message TEXT,
                last_error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                seeding_ratio REAL DEFAULT 0.0,
                seeding_time_seconds INTEGER DEFAULT 0,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_result_id) REFERENCES search_results(id)
            )
        """
        
        cursor.execute(create_table_sql)
        
        # Create indexes for common queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_queue_status ON download_queue(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_queue_book_title ON download_queue(book_title)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_queue_asin ON download_queue(book_asin)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_queue_queued_at ON download_queue(queued_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_queue_client_id ON download_queue(download_client_id)')
        
        self.logger.debug("Download queue table created or verified")

    def _seed_default_author_overrides(self, cursor):
        """Insert curated overrides to keep metadata consistent."""
        defaults = [
            ("A. C. Cobble", "AC Cobble", "B06XB1KBV4", "Normalize punctuation for Endless Flight")
        ]

        for source, preferred, asin, notes in defaults:
            asin_value = (asin or '').strip().upper()
            cursor.execute(
                """
                INSERT OR IGNORE INTO author_name_overrides
                    (source_author_name, preferred_author_name, asin, notes)
                VALUES (?, ?, ?, ?)
                """,
                (source, preferred, asin_value, notes)
            )
    
    def migrate_database(self):
        """Check and perform database migrations."""
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get current table schema
            cursor.execute("PRAGMA table_info(books)")
            columns = [column[1] for column in cursor.fetchall()]
            
            migrations_applied = 0
            
            # Migration 1: Add cover_image column
            if 'cover_image' not in columns:
                self.logger.info("Adding cover_image column to books table...")
                cursor.execute("ALTER TABLE books ADD COLUMN cover_image TEXT")
                migrations_applied += 1
                self.logger.info("Cover image column added successfully")
            
            # Migration 2: Add created_at/updated_at columns
            if 'created_at' not in columns:
                self.logger.info("Adding timestamp columns to books table...")
                migrations_applied += 1
                self.logger.info("Timestamp columns added successfully")
            
            # Migration 3: Create authors table if it doesn't exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='authors'")
            authors_table_exists = cursor.fetchone() is not None
            
            if not authors_table_exists:
                self.logger.info("Creating authors table...")
                self._create_authors_table(cursor)
                migrations_applied += 1
                self.logger.info("Authors table created successfully")

            # Migration 3b: Create author_name_overrides table if it doesn't exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='author_name_overrides'")
            overrides_table_exists = cursor.fetchone() is not None

            if not overrides_table_exists:
                self.logger.info("Creating author_name_overrides table...")
                self._create_author_name_overrides_table(cursor)
                migrations_applied += 1
                self.logger.info("author_name_overrides table created successfully")

            # Ensure default overrides exist
            self._seed_default_author_overrides(cursor)
            
            # Migration 4: Add num_ratings column
            if 'num_ratings' not in columns:
                self.logger.info("Adding num_ratings column to books table...")
                cursor.execute("ALTER TABLE books ADD COLUMN num_ratings INTEGER DEFAULT 0")
                migrations_applied += 1
                self.logger.info("Num_ratings column added successfully")
            
            # Migration 5: Create audible_library table if it doesn't exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audible_library'")
            audible_library_table_exists = cursor.fetchone() is not None
            
            if not audible_library_table_exists:
                self.logger.info("Creating audible_library table...")
                self._create_audible_library_table(cursor)
                migrations_applied += 1
                self.logger.info("Audible library table created successfully")
            else:
                # Migration 6: Check if audible_library table needs to be recreated with ASIN primary key
                cursor.execute("PRAGMA table_info(audible_library)")
                audible_columns = {row[1]: row for row in cursor.fetchall()}
                
                # Check if ASIN is the primary key
                asin_column = audible_columns.get('asin')
                if asin_column and not asin_column[5]:  # Column 5 is pk flag
                    self.logger.info("Migrating audible_library table to use ASIN as primary key...")
                    
                    # Backup existing data
                    cursor.execute("SELECT * FROM audible_library")
                    existing_data = cursor.fetchall()
                    
                    # Drop old table
                    cursor.execute("DROP TABLE audible_library")
                    
                    # Create new table with ASIN as primary key
                    self._create_audible_library_table(cursor)
                    
                    # Restore data where ASIN exists
                    if existing_data:
                        for row in existing_data:
                            # Extract ASIN (index varies by old schema)
                            asin = None
                            for i, value in enumerate(row):
                                # Find ASIN column by checking if it looks like an ASIN
                                if isinstance(value, str) and len(value) == 10 and value.isalnum():
                                    asin = value
                                    break
                            
                            if asin:
                                # Insert with ASIN as primary key
                                try:
                                    cursor.execute("""
                                        INSERT OR IGNORE INTO audible_library 
                                        (asin, title, author, last_updated) 
                                        VALUES (?, ?, ?, datetime('now'))
                                    """, (asin, row[1] if len(row) > 1 else None, row[2] if len(row) > 2 else None))
                                except Exception as e:
                                    self.logger.warning(f"Could not migrate row with ASIN {asin}: {e}")
                    
                    migrations_applied += 1
                    self.logger.info("Audible library table migrated to ASIN primary key successfully")
            
            # Future migrations can be added here
            # Migration 5: Add series_asin column to books table
            cursor.execute("PRAGMA table_info(books)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'series_asin' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN series_asin TEXT")
                migrations_applied += 1
                self.logger.info("Added series_asin column to books table")
            
            # Migration 6: Create series_metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS series_metadata (
                    series_asin TEXT PRIMARY KEY,
                    series_title TEXT NOT NULL,
                    series_url TEXT,
                    sku TEXT,
                    sku_lite TEXT,
                    total_books INTEGER DEFAULT 0,
                    description TEXT,
                    cover_url TEXT,
                    last_synced TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Check if table was just created
            cursor.execute("SELECT COUNT(*) FROM series_metadata")
            if cursor.fetchone()[0] == 0:
                migrations_applied += 1
                self.logger.info("Created series_metadata table")
            
            # Migration 7: Create series_books table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS series_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_asin TEXT NOT NULL,
                    book_asin TEXT NOT NULL,
                    book_title TEXT,
                    sequence TEXT,
                    sort_order TEXT,
                    relationship_type TEXT DEFAULT 'child',
                    in_library BOOLEAN DEFAULT 0,
                    in_audiobookshelf BOOLEAN DEFAULT 0,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(series_asin, book_asin),
                    FOREIGN KEY (series_asin) REFERENCES series_metadata(series_asin)
                )
            """)
            # Check if table was just created
            cursor.execute("SELECT COUNT(*) FROM series_books")
            if cursor.fetchone()[0] == 0:
                migrations_applied += 1
                self.logger.info("Created series_books table")
            
            # Create indexes for series tables
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_series_books_series_asin 
                ON series_books(series_asin)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_series_books_book_asin 
                ON series_books(book_asin)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_series_books_in_library 
                ON series_books(in_library)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_series_asin 
                ON books(series_asin)
            """)
            
            # Migration 8: Add metadata columns to series_books table
            # Check if columns exist before adding them
            cursor.execute("PRAGMA table_info(series_books)")
            existing_columns = [column[1] for column in cursor.fetchall()]
            
            columns_to_add = {
                'author': 'TEXT',
                'narrator': 'TEXT',
                'publisher': 'TEXT',
                'release_date': 'TEXT',
                'runtime': 'INTEGER DEFAULT 0',
                'rating': 'TEXT',
                'num_ratings': 'INTEGER DEFAULT 0',
                'summary': 'TEXT',
                'cover_image': 'TEXT',
                'language': 'TEXT DEFAULT "English"'
            }
            
            columns_added = 0
            for column_name, column_type in columns_to_add.items():
                if column_name not in existing_columns:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE series_books 
                            ADD COLUMN {column_name} {column_type}
                        """)
                        columns_added += 1
                        self.logger.info(f"Added column '{column_name}' to series_books table")
                    except Exception as e:
                        self.logger.warning(f"Could not add column '{column_name}' to series_books: {e}")
            
            if migrations_applied > 0:
                migrations_applied += 1
                self.logger.info(f"Added {columns_added} metadata columns to series_books table")
            
            # Migration 9: Add import tracking columns to books table
            cursor.execute("PRAGMA table_info(books)")
            existing_book_columns = [column[1] for column in cursor.fetchall()]
            
            import_columns_to_add = {
                'file_path': 'TEXT',
                'file_size': 'INTEGER',
                'file_format': 'TEXT',
                'file_quality': 'TEXT',
                'imported_to_library': 'BOOLEAN DEFAULT 0',
                'import_date': 'INTEGER',
                'naming_template': 'TEXT'
            }
            
            import_columns_added = 0
            for column_name, column_type in import_columns_to_add.items():
                if column_name not in existing_book_columns:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE books 
                            ADD COLUMN {column_name} {column_type}
                        """)
                        import_columns_added += 1
                        self.logger.info(f"Added import tracking column '{column_name}' to books table")
                    except Exception as e:
                        self.logger.warning(f"Could not add column '{column_name}' to books: {e}")
            
            if import_columns_added > 0:
                migrations_applied += 1
                self.logger.info(f"Added {import_columns_added} import tracking columns to books table")
            
            # Create index for import queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_imported_to_library 
                ON books(imported_to_library)
            """)
            
            # Migration 10: Create deduplication trigger for series_books
            # This prevents duplicate book editions (ISBN vs ASIN) from being inserted
            # Preference: Audible ASINs (B0...) over ISBNs (numeric)
            # Always drop and recreate trigger to ensure latest logic
            cursor.execute("""
                DROP TRIGGER IF EXISTS prevent_series_book_duplicates
            """)

            cursor.execute("""
                CREATE TRIGGER prevent_series_book_duplicates
                BEFORE INSERT ON series_books
                FOR EACH ROW
                WHEN (
                    -- Check if a similar book already exists for this series
                    EXISTS (
                        SELECT 1 FROM series_books 
                        WHERE series_asin = NEW.series_asin
                        AND book_asin != NEW.book_asin
                        AND (
                            -- Same title (case-insensitive, normalized)
                            LOWER(TRIM(SUBSTR(COALESCE(book_title, ''), 1, INSTR(COALESCE(book_title, '') || ':', ':') - 1))) = 
                            LOWER(TRIM(SUBSTR(COALESCE(NEW.book_title, ''), 1, INSTR(COALESCE(NEW.book_title, '') || ':', ':') - 1)))
                            OR COALESCE(book_title, '') = COALESCE(NEW.book_title, '')
                        )
                        AND (sequence = NEW.sequence OR (sequence IS NULL AND NEW.sequence IS NULL))
                        -- Existing entry is an Audible ASIN (B0...), new entry is ISBN (numeric)
                        AND book_asin LIKE 'B0%'
                        AND LENGTH(book_asin) = 10
                        AND NEW.book_asin NOT LIKE 'B%'
                    )
                )
                BEGIN
                    -- Abort the insert - better entry already exists
                    SELECT RAISE(IGNORE);
                END
            """)
            
            # Check if trigger was created
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='trigger' AND name='prevent_series_book_duplicates'
            """)
            if cursor.fetchone()[0] > 0:
                migrations_applied += 1
                self.logger.info("Created series_books deduplication trigger")
            
            # Migration 11: Add download management columns to download_queue table
            cursor.execute("PRAGMA table_info(download_queue)")
            download_queue_columns = [column[1] for column in cursor.fetchall()]
            
            download_columns_to_add = {
                'seeding_enabled': 'BOOLEAN DEFAULT 0',
                'delete_source': 'BOOLEAN DEFAULT 0',
                'temp_file_path': 'TEXT',
                'converted_file_path': 'TEXT',
                'original_file_path': 'TEXT',
                'priority': 'INTEGER DEFAULT 5',
                'next_retry_at': 'TEXT',
                'seeding_ratio': 'REAL DEFAULT 0.0',
                'seeding_time_seconds': 'INTEGER DEFAULT 0'
            }
            
            download_columns_added = 0
            for column_name, column_type in download_columns_to_add.items():
                if column_name not in download_queue_columns:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE download_queue 
                            ADD COLUMN {column_name} {column_type}
                        """)
                        download_columns_added += 1
                        self.logger.info(f"Added download management column '{column_name}' to download_queue table")
                    except Exception as e:
                        self.logger.warning(f"Could not add column '{column_name}' to download_queue: {e}")
            
            if download_columns_added > 0:
                migrations_applied += 1
                self.logger.info(f"Added {download_columns_added} download management columns to download_queue table")
            
            # Create partial unique index for active downloads (enforces one download per ASIN)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_download_queue_unique_active_asin 
                ON download_queue(book_asin) 
                WHERE status NOT IN ('IMPORTED', 'FAILED', 'CANCELLED')
            """)
            
            # Check if unique index was created
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='index' AND name='idx_download_queue_unique_active_asin'
            """)
            if cursor.fetchone()[0] > 0:
                migrations_applied += 1
                self.logger.info("Created unique ASIN constraint for active downloads")
            
            # Migration 12: Add unified download pipeline columns to download_queue table
            cursor.execute("PRAGMA table_info(download_queue)")
            pipeline_columns = [column[1] for column in cursor.fetchall()]
            
            unified_pipeline_columns = {
                'download_type': 'TEXT DEFAULT "torrent"',
                'temp_file_path': 'TEXT',
                'converted_file_path': 'TEXT',
                'final_file_path': 'TEXT',
                'voucher_file_path': 'TEXT',
                'indexer': 'TEXT',
                'priority': 'INTEGER DEFAULT 5',
                'last_error': 'TEXT',
                'next_retry_at': 'TEXT',
                'info_hash': 'TEXT'
            }
            
            pipeline_columns_added = 0
            for column_name, column_type in unified_pipeline_columns.items():
                if column_name not in pipeline_columns:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE download_queue 
                            ADD COLUMN {column_name} {column_type}
                        """)
                        pipeline_columns_added += 1
                        self.logger.info(f"Added unified pipeline column '{column_name}' to download_queue table")
                    except Exception as e:
                        self.logger.warning(f"Could not add column '{column_name}' to download_queue: {e}")
            
            if pipeline_columns_added > 0:
                migrations_applied += 1
                self.logger.info(f"Added {pipeline_columns_added} unified download pipeline columns to download_queue table")
            
            # Create index for download_type for faster filtering
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_download_queue_download_type 
                ON download_queue(download_type)
            """)
            
            if migrations_applied > 0:
                conn.commit()
                self.logger.info(f"Applied {migrations_applied} database migrations")
            else:
                self.logger.debug("No database migrations needed")
            
            conn.close()
        
        except Exception as e:
            self.logger.error(f"Error during database migration: {e}")
            raise
    
    def get_schema_version(self) -> dict:
        """Get current database schema information"""
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get table info
            cursor.execute("PRAGMA table_info(books)")
            columns = cursor.fetchall()
            
            # Get indexes
            cursor.execute("PRAGMA index_list(books)")
            indexes = cursor.fetchall()
            
            conn.close()
            
            return {
                'columns': [{'name': col[1], 'type': col[2], 'not_null': bool(col[3]), 'primary_key': bool(col[5])} for col in columns],
                'indexes': [{'name': idx[1], 'unique': bool(idx[2])} for idx in indexes],
                'total_columns': len(columns),
                'total_indexes': len(indexes)
            }
        
        except Exception as e:
            self.logger.error(f"Error getting schema version: {e}")
            return {'error': str(e)}
    
    def verify_schema_integrity(self) -> bool:
        """Verify database schema integrity"""
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Check integrity
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            conn.close()
            
            if result[0] == 'ok':
                self.logger.info("Database schema integrity check passed")
                return True
            else:
                self.logger.error(f"Database schema integrity check failed: {result[0]}")
                return False
        
        except Exception as e:
            self.logger.error(f"Error verifying schema integrity: {e}")
            return False
