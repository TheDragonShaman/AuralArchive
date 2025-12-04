import logging
from typing import Dict, TYPE_CHECKING
from .error_handling import error_handler

if TYPE_CHECKING:
    from .connection import DatabaseConnection

class DatabaseStats:
    """Handles database statistics and analytics operations"""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        self.logger = logging.getLogger("DatabaseService.Stats")
    
    def get_library_stats(self) -> Dict:
        """Get comprehensive library statistics."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Get all books for analysis
            cursor.execute("SELECT * FROM books")
            books = cursor.fetchall()
            
            stats = {
                'total_books': len(books),
                'by_status': {},
                'by_language': {},
                'total_runtime_hours': 0,
                'total_authors': 0,
                'total_series': 0,
                'average_rating': 0,
                'rating_distribution': {},
                'recent_additions': 0,
                'completion_stats': {}
            }
            
            # Process each book
            total_rating = 0
            rated_books = 0
            authors = set()
            series = set()
            runtime_minutes = 0
            
            for book in books:
                # Status distribution
                status = book[12] or 'Unknown'  # status column
                stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
                
                # Language distribution
                language = book[8] or 'Unknown'  # language column
                stats['by_language'][language] = stats['by_language'].get(language, 0) + 1
                
                # Authors tracking
                if book[2]:  # author column
                    authors.add(book[2])
                
                # Series tracking
                if book[3] and book[3] != 'N/A':  # series column
                    series.add(book[3])
                
                # Runtime calculation
                runtime = book[6]  # runtime column
                if runtime:
                    try:
                        if 'hrs' in runtime:
                            parts = runtime.split(' hrs')
                            hours = int(parts[0])
                            minutes = 0
                            if len(parts) > 1 and 'mins' in parts[1]:
                                minutes = int(parts[1].split(' mins')[0].strip())
                            runtime_minutes += hours * 60 + minutes
                    except:
                        pass
                
                # Rating calculation
                rating = book[10]  # overall_rating column
                if rating and rating != 'N/A':
                    try:
                        rating_val = float(rating)
                        total_rating += rating_val
                        rated_books += 1
                        
                        # Rating distribution
                        rating_range = f"{int(rating_val)}-{int(rating_val)+1}"
                        stats['rating_distribution'][rating_range] = stats['rating_distribution'].get(rating_range, 0) + 1
                    except:
                        pass
            
            # Calculate final stats
            stats['total_authors'] = len(authors)
            stats['total_series'] = len(series)
            stats['total_runtime_hours'] = round(runtime_minutes / 60, 1)
            stats['average_rating'] = round(total_rating / rated_books, 2) if rated_books > 0 else 0
            
            # Calculate completion stats
            owned_books = stats['by_status'].get('Owned', 0)
            wanted_books = stats['by_status'].get('Wanted', 0)
            downloading_books = stats['by_status'].get('Downloading', 0)
            
            stats['completion_stats'] = {
                'owned_percentage': round((owned_books / len(books)) * 100, 1) if books else 0,
                'wanted_percentage': round((wanted_books / len(books)) * 100, 1) if books else 0,
                'downloading_percentage': round((downloading_books / len(books)) * 100, 1) if books else 0
            }
            
            self.logger.debug(f"Calculated library stats: {len(books)} total books")
            return stats
        
        except Exception as e:
            self.logger.error(f"Error calculating library stats: {e}")
            return {'error': str(e)}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_status_distribution(self) -> Dict[str, int]:
        """Get book count by status."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM books
                GROUP BY status
                ORDER BY count DESC
            """)
            
            results = cursor.fetchall()
            distribution = {row[0] or 'Unknown': row[1] for row in results}
            
            self.logger.debug(f"Status distribution: {distribution}")
            return distribution
        
        except Exception as e:
            self.logger.error(f"Error getting status distribution: {e}")
            return {}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_language_distribution(self) -> Dict[str, int]:
        """Get book count by language."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT language, COUNT(*) as count
                FROM books
                WHERE language IS NOT NULL AND language != ''
                GROUP BY language
                ORDER BY count DESC
            """)
            
            results = cursor.fetchall()
            distribution = {row[0]: row[1] for row in results}
            
            self.logger.debug(f"Language distribution: {distribution}")
            return distribution
        
        except Exception as e:
            self.logger.error(f"Error getting language distribution: {e}")
            return {}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_recent_activity_stats(self, days: int = 30) -> Dict:
        """Get recent activity statistics."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            # Books added in last N days
            cursor.execute("""
                SELECT COUNT(*) as recent_additions
                FROM books
                WHERE created_at >= datetime('now', '-{} days')
            """.format(days))
            
            recent_additions = cursor.fetchone()[0]
            
            # Books updated in last N days
            cursor.execute("""
                SELECT COUNT(*) as recent_updates
                FROM books
                WHERE updated_at >= datetime('now', '-{} days')
                AND updated_at != created_at
            """.format(days))
            
            recent_updates = cursor.fetchone()[0]
            
            stats = {
                'period_days': days,
                'recent_additions': recent_additions,
                'recent_updates': recent_updates,
                'total_activity': recent_additions + recent_updates
            }
            
            self.logger.debug(f"Recent activity ({days} days): {stats}")
            return stats
        
        except Exception as e:
            self.logger.error(f"Error getting recent activity stats: {e}")
            return {'error': str(e)}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
    
    def get_series_completion_stats(self) -> Dict:
        """Get statistics about series completion."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            
            cursor.execute("""
                SELECT 
                    series,
                    COUNT(*) as total_books,
                    SUM(CASE WHEN status = 'Owned' THEN 1 ELSE 0 END) as owned_books,
                    SUM(CASE WHEN status = 'Wanted' THEN 1 ELSE 0 END) as wanted_books
                FROM books
                WHERE series != 'N/A' AND series IS NOT NULL
                GROUP BY series
                HAVING total_books > 1
                ORDER BY total_books DESC
            """)
            
            results = cursor.fetchall()
            series_stats = []
            
            for row in results:
                series_name, total, owned, wanted = row
                completion_percentage = round((owned / total) * 100, 1) if total > 0 else 0
                
                series_stats.append({
                    'series_name': series_name,
                    'total_books': total,
                    'owned_books': owned,
                    'wanted_books': wanted,
                    'completion_percentage': completion_percentage,
                    'is_complete': completion_percentage == 100.0
                })
            
            # Overall series stats
            total_series = len(series_stats)
            complete_series = sum(1 for s in series_stats if s['is_complete'])
            
            stats = {
                'total_series': total_series,
                'complete_series': complete_series,
                'incomplete_series': total_series - complete_series,
                'completion_rate': round((complete_series / total_series) * 100, 1) if total_series > 0 else 0,
                'series_details': series_stats[:20]  # Top 20 series by book count
            }
            
            self.logger.debug(f"Series completion stats: {total_series} series, {complete_series} complete")
            return stats
        
        except Exception as e:
            self.logger.error(f"Error getting series completion stats: {e}")
            return {'error': str(e)}
        
        finally:
            error_handler.handle_connection_cleanup(conn)
