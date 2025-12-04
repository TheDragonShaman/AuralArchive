"""
Queue Manager
=============

Handles download queue operations:
- Add/remove queue items
- ASIN uniqueness enforcement
- Priority management
- Queue statistics
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

from utils.logger import get_module_logger

logger = get_module_logger("QueueManager")


class QueueManager:
    """
    Manages the download queue database operations.
    
    Features:
    - Enforces one active download per ASIN
    - Priority-based queue ordering
    - Queue statistics and filtering
    """
    
    def __init__(self):
        """Initialize queue manager."""
        self.logger = logger
        self._database_service = None
    
    def _get_database_service(self):
        """Lazy load DatabaseService."""
        if self._database_service is None:
            from services.service_manager import get_database_service
            self._database_service = get_database_service()
        return self._database_service
    
    def add_to_queue(self, book_asin: str, search_result_id: Optional[int] = None,
                     priority: int = 5, **kwargs) -> int:
        """
        Add item to download queue.
        
        Args:
            book_asin: Audible ASIN
            search_result_id: Reference to search_results table
            priority: Queue priority 1-10
            **kwargs: Additional metadata including:
                - title, author: Book metadata
                - download_type: 'audible', 'torrent', or 'nzb' (default: 'torrent')
                - download_url: Source URL (for torrents/NZB)
                - audible_format: 'aaxc', 'aax', or 'aax-fallback' (for Audible)
                - audible_quality: 'best', 'high', or 'normal' (for Audible)
                - indexer: Name of indexer/source
                - Other fields: download_client, quality_score, match_score, file_format, file_size
        
        Returns:
            download_id: ID of created queue item
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            # Prepare insert data with required fields
            insert_data = {
                'book_asin': book_asin,
                'search_result_id': search_result_id,
                'status': 'QUEUED',
                'priority': priority,
                'queued_at': datetime.now().isoformat(),
                'retry_count': 0,
                'max_retries': kwargs.get('max_retries', 3),
                'download_type': kwargs.get('download_type', 'torrent'),  # New unified pipeline field
                'next_retry_at': None
            }
            
            # Map API field names to database column names
            field_mapping = {
                'title': 'book_title',
                'author': 'book_author'
            }
            
            # Add optional fields from kwargs
            optional_fields = [
                'book_title', 'book_author', 'download_url', 'download_client',
                'quality_score', 'match_score', 'file_format', 'file_size',
                # New unified pipeline fields
                'temp_file_path', 'converted_file_path', 'final_file_path',
                'voucher_file_path', 'indexer', 'next_retry_at', 'info_hash'
            ]
            
            # Handle Audible-specific metadata
            if insert_data['download_type'] == 'audible':
                # Store Audible format/quality preferences in JSON or dedicated fields
                audible_metadata = {}
                if 'audible_format' in kwargs:
                    audible_metadata['format'] = kwargs['audible_format']
                if 'audible_quality' in kwargs:
                    audible_metadata['quality'] = kwargs['audible_quality']
                
                # Store in file_format field for now (could use JSON field later)
                if audible_metadata:
                    insert_data['file_format'] = f"{audible_metadata.get('format', 'aaxc')}:{audible_metadata.get('quality', 'best')}"
                
                # Set indexer to 'Audible' for Audible downloads
                insert_data['indexer'] = 'Audible'
            
            # Apply field name mapping and add fields
            for field in optional_fields:
                if field in kwargs:
                    insert_data[field] = kwargs[field]
            
            # Handle mapped field names (e.g., 'title' -> 'book_title')
            for api_name, db_name in field_mapping.items():
                if api_name in kwargs and db_name not in insert_data:
                    insert_data[db_name] = kwargs[api_name]
            
            # Build INSERT query
            columns = ', '.join(insert_data.keys())
            placeholders = ', '.join(['?' for _ in insert_data])
            query = f"INSERT INTO download_queue ({columns}) VALUES ({placeholders})"
            
            cursor.execute(query, list(insert_data.values()))
            conn.commit()
            
            download_id = cursor.lastrowid
            download_type = insert_data['download_type']
            self.logger.debug(f"Added to queue: {book_asin} (ID: {download_id}, type: {download_type}, priority: {priority})")
            
            return download_id
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def get_download(self, download_id: int) -> Optional[Dict[str, Any]]:
        """
        Get download by ID.
        
        Args:
            download_id: Download queue ID
        
        Returns:
            Download record or None
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            cursor.execute("SELECT * FROM download_queue WHERE id=?", (download_id,))
            row = cursor.fetchone()
            
            if row:
                # Get column names and convert row to dictionary
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def get_active_download_by_asin(self, book_asin: str) -> Optional[Dict[str, Any]]:
        """
        Check if book has active download (not IMPORTED, FAILED, or CANCELLED).
        
        Args:
            book_asin: Audible ASIN
        
        Returns:
            Active download record or None
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            query = """
                SELECT * FROM download_queue 
                WHERE book_asin=? 
                AND status NOT IN ('IMPORTED', 'FAILED', 'CANCELLED')
                LIMIT 1
            """
            cursor.execute(query, (book_asin,))
            row = cursor.fetchone()
            
            if row:
                # Get column names and convert row to dictionary
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def get_queue(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all queue items, optionally filtered by status.
        
        Args:
            status_filter: Optional status to filter by
        
        Returns:
            List of download records
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            if status_filter:
                query = """
                    SELECT * FROM download_queue 
                    WHERE status=?
                    ORDER BY priority DESC, queued_at ASC
                """
                cursor.execute(query, (status_filter,))
            else:
                query = """
                    SELECT * FROM download_queue 
                    WHERE status NOT IN ('IMPORTED', 'FAILED', 'CANCELLED')
                    ORDER BY priority DESC, queued_at ASC
                """
                cursor.execute(query)
            
            # Get column names
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            return [dict(zip(columns, row)) for row in rows]
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def update_download(self, download_id: int, updates: Dict[str, Any]):
        """
        Update download record.
        
        Args:
            download_id: Download queue ID
            updates: Dictionary of fields to update
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            # Add updated_at timestamp
            updates['updated_at'] = datetime.now().isoformat()
            
            # Build UPDATE query
            set_clause = ', '.join([f"{key}=?" for key in updates.keys()])
            query = f"UPDATE download_queue SET {set_clause} WHERE id=?"
            
            values = list(updates.values()) + [download_id]
            cursor.execute(query, values)
            conn.commit()
            
            self.logger.debug(f"Updated download {download_id}: {updates}")
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def delete_download(self, download_id: int):
        """
        Delete download from queue.
        
        Args:
            download_id: Download queue ID
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            cursor.execute("DELETE FROM download_queue WHERE id=?", (download_id,))
            conn.commit()
            self.logger.debug(f"Deleted download {download_id} from queue")
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def get_queue_statistics(self) -> Dict[str, int]:
        """
        Get queue statistics by status.
        
        Returns:
            Dictionary of counts by status
        """
        db = self._get_database_service()
        conn, cursor = db.connection_manager.connect_db()
        
        try:
            query = """
                SELECT status, COUNT(*) as count 
                FROM download_queue 
                GROUP BY status
            """
            cursor.execute(query)
            rows = cursor.fetchall()

            stats = {}
            for row in rows:
                status, count = row[0], row[1]
                stats[status] = count
            stats['total_active'] = sum(
                count for status, count in stats.items()
                if status not in ('IMPORTED', 'FAILED', 'CANCELLED')
            )
            
            return stats
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
