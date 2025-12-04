import logging
from typing import List, Optional, Dict
from .error_handling import error_handler


class AuthorOverrideOperations:
    """Manages canonical author name overrides scoped by optional ASIN."""

    GLOBAL_SCOPE = ""

    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        self.logger = logging.getLogger("DatabaseService.AuthorOverrides")

    def _normalize_name(self, name: Optional[str]) -> str:
        if not name:
            return ""
        cleaned = str(name).replace("\u00a0", " ")
        return " ".join(cleaned.strip().split())

    def _normalize_asin(self, asin: Optional[str]) -> str:
        if not asin:
            return self.GLOBAL_SCOPE
        return str(asin).strip().upper()

    def get_preferred_author_name(self, source_author_name: str, asin: Optional[str] = None) -> Optional[str]:
        """Return the preferred author name if an override exists."""
        normalized_source = self._normalize_name(source_author_name)
        scope_asin = self._normalize_asin(asin)

        if not normalized_source:
            return None

        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()

            if scope_asin != self.GLOBAL_SCOPE:
                cursor.execute(
                    """
                    SELECT preferred_author_name
                    FROM author_name_overrides
                    WHERE source_author_name = ? COLLATE NOCASE
                      AND asin = ?
                    LIMIT 1
                    """,
                    (normalized_source, scope_asin)
                )
                row = cursor.fetchone()
                if row:
                    preferred = row[0]
                    return self._normalize_name(preferred) or preferred

            cursor.execute(
                """
                SELECT preferred_author_name
                FROM author_name_overrides
                WHERE source_author_name = ? COLLATE NOCASE
                  AND asin = ?
                LIMIT 1
                """,
                (normalized_source, self.GLOBAL_SCOPE)
            )
            row = cursor.fetchone()
            if row:
                preferred = row[0]
                return self._normalize_name(preferred) or preferred

            cursor.execute(
                """
                SELECT preferred_author_name
                FROM author_name_overrides
                WHERE source_author_name = ? COLLATE NOCASE
                LIMIT 1
                """,
                (normalized_source,)
            )
            row = cursor.fetchone()
            if row:
                preferred = row[0]
                return self._normalize_name(preferred) or preferred

            return None
        except Exception as exc:
            self.logger.error(f"Error fetching author override for '{source_author_name}': {exc}")
            return None
        finally:
            error_handler.handle_connection_cleanup(conn)

    def get_aliases_for_preferred(self, preferred_author_name: str) -> List[str]:
        """Return alternate spellings that map to the preferred author name."""
        normalized_preferred = self._normalize_name(preferred_author_name)
        if not normalized_preferred:
            return []

        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute(
                """
                SELECT DISTINCT source_author_name
                FROM author_name_overrides
                WHERE preferred_author_name = ? COLLATE NOCASE
                """,
                (normalized_preferred,)
            )
            values = [self._normalize_name(row[0]) for row in cursor.fetchall() if row[0]]
            return values
        except Exception as exc:
            self.logger.error(f"Error fetching aliases for '{preferred_author_name}': {exc}")
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)

    def upsert_override(
        self,
        source_author_name: str,
        preferred_author_name: str,
        asin: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Insert or update a canonical author override."""
        normalized_source = self._normalize_name(source_author_name)
        normalized_preferred = self._normalize_name(preferred_author_name)
        normalized_asin = self._normalize_asin(asin)

        if not normalized_source or not normalized_preferred:
            self.logger.warning("Cannot upsert override with empty names")
            return False

        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute(
                """
                INSERT INTO author_name_overrides (
                    source_author_name,
                    preferred_author_name,
                    asin,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(source_author_name, asin) DO UPDATE SET
                    preferred_author_name=excluded.preferred_author_name,
                    notes=COALESCE(excluded.notes, author_name_overrides.notes),
                    updated_at=CURRENT_TIMESTAMP
                """,
                (normalized_source, normalized_preferred, normalized_asin, notes),
            )
            conn.commit()
            self.logger.info(
                "Upserted author override: %s (%s) -> %s",
                normalized_source,
                normalized_asin or "global",
                normalized_preferred,
            )
            return True
        except Exception as exc:
            if conn:
                conn.rollback()
            self.logger.error(f"Error upserting author override: {exc}")
            return False
        finally:
            error_handler.handle_connection_cleanup(conn)

    def list_overrides(self) -> List[Dict[str, str]]:
        """Return all configured overrides."""
        conn = None
        try:
            conn, cursor = self.connection_manager.connect_db()
            cursor.execute(
                """
                SELECT source_author_name, preferred_author_name, asin, notes
                FROM author_name_overrides
                ORDER BY source_author_name COLLATE NOCASE
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "source_author_name": row[0],
                    "preferred_author_name": row[1],
                    "asin": row[2],
                    "notes": row[3],
                }
                for row in rows
            ]
        except Exception as exc:
            self.logger.error(f"Error listing author overrides: {exc}")
            return []
        finally:
            error_handler.handle_connection_cleanup(conn)
