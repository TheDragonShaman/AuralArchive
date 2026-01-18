"""
Module Name: series_sync_service.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Fetches and syncs series data from Audible API into the local database.

Location:
    /services/series_sync_service.py

"""

from typing import Dict, List, Optional, Tuple

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Audible.SeriesSync")


class SeriesSyncService:
    """Service for syncing series data from Audible API."""

    def __init__(self, audible_client, database_service, *, logger=None):
        self.client = audible_client
        self.db = database_service
        self.logger = logger or _LOGGER

    def extract_series_from_relationships(self, product_data: Dict) -> Optional[Dict]:
        """Extract series information from product relationships."""
        try:
            relationships = product_data.get("relationships", [])

            for relationship in relationships:
                if relationship.get("relationship_type") == "series":
                    return {
                        "series_asin": relationship.get("asin"),
                        "series_title": relationship.get("title"),
                        "series_url": relationship.get("url"),
                        "sku": relationship.get("sku"),
                        "sku_lite": relationship.get("sku_lite"),
                        "sequence": relationship.get("sequence"),
                        "sort_order": relationship.get("sort"),
                    }

            return None

        except Exception as e:
            self.logger.error(
                "Error extracting series from relationships", extra={"error": str(e)}, exc_info=True
            )
            return None

    def fetch_series_books(self, series_asin: str) -> Tuple[bool, List[Dict], str]:
        """Fetch all books in a series from Audible API."""
        try:
            self.logger.info("Fetching series books", extra={"series_asin": series_asin})

            params = {
                "asin": series_asin,
                "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships",
            }

            response = self.client.get(f"1.0/catalog/products/{series_asin}", params=params)

            if response.status_code != 200:
                error_msg = f"API error: {response.status_code}"
                self.logger.error(
                    "API error fetching series",
                    extra={"series_asin": series_asin, "status_code": response.status_code},
                )
                return False, [], error_msg

            product = response.json().get("product", {})

            series_metadata = {
                "series_asin": series_asin,
                "series_title": product.get("title", "Unknown Series"),
                "series_url": f"/pd/{product.get('title', '').replace(' ', '-')}-Audiobook/{series_asin}",
                "sku": product.get("sku"),
                "sku_lite": product.get("sku_lite"),
                "description": product.get("publisher_summary", ""),
                "cover_url": None,
            }

            if "product_images" in product:
                images = product.get("product_images", {})
                series_metadata["cover_url"] = images.get("500") or images.get("1000") or images.get("2000")

            relationships = product.get("relationships", [])
            books = []

            for relationship in relationships:
                if relationship.get("relationship_to_product") == "child" and relationship.get(
                    "content_delivery_type"
                ) in ["SingleASIN", "MultiPartBook"]:
                    book_data = {
                        "book_asin": relationship.get("asin"),
                        "book_title": relationship.get("title"),
                        "sequence": relationship.get("sequence"),
                        "sort_order": relationship.get("sort"),
                        "relationship_type": "child",
                        "url": relationship.get("url"),
                    }
                    books.append(book_data)

            self.logger.info(
                "Found books in series",
                extra={
                    "series_asin": series_asin,
                    "series_title": series_metadata["series_title"],
                    "book_count": len(books),
                },
            )

            return True, books, series_metadata

        except Exception as e:
            error_msg = f"Error fetching series books: {e}"
            self.logger.error(
                "Error fetching series books", extra={"series_asin": series_asin, "error": str(e)}, exc_info=True
            )
            return False, [], error_msg

    def sync_series(self, series_asin: str) -> Tuple[bool, str]:
        """Sync a complete series to the database."""
        try:
            success, books, series_metadata = self.fetch_series_books(series_asin)

            if not success:
                return False, series_metadata

            if not self.db.series.upsert_series_metadata(series_metadata):
                return False, "Failed to save series metadata"

            books_added = 0
            for book in books:
                book["series_asin"] = series_asin
                if self.db.series.upsert_series_book(book):
                    books_added += 1

            self.db.series.update_series_book_counts(series_asin)

            message = f"Synced series '{series_metadata['series_title']}': {books_added} books"
            self.logger.info(
                "Synced series",
                extra={
                    "series_asin": series_asin,
                    "series_title": series_metadata["series_title"],
                    "books_added": books_added,
                },
            )

            return True, message

        except Exception as e:
            error_msg = f"Error syncing series: {e}"
            self.logger.error("Error syncing series", extra={"series_asin": series_asin, "error": str(e)}, exc_info=True)
            return False, error_msg

    def sync_book_series(self, book_asin: str) -> Tuple[bool, str]:
        """Sync series data for a specific book."""
        try:
            self.logger.info("Syncing series for book", extra={"book_asin": book_asin})

            params = {
                "asin": book_asin,
                "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series,rating,media,relationships",
            }

            response = self.client.get(f"1.0/catalog/products/{book_asin}", params=params)

            if response.status_code != 200:
                return False, f"API error: {response.status_code}"

            product = response.json().get("product", {})

            series_info = self.extract_series_from_relationships(product)

            if not series_info:
                return False, "No series found for this book"

            series_asin = series_info["series_asin"]

            self.db.series.update_book_series_asin(book_asin, series_asin)

            success, message = self.sync_series(series_asin)

            if success:
                self.db.series.mark_series_book_as_owned(series_asin, book_asin)

            return success, message

        except Exception as e:
            error_msg = f"Error syncing book series: {e}"
            self.logger.error(
                "Error syncing book series", extra={"book_asin": book_asin, "error": str(e)}, exc_info=True
            )
            return False, error_msg

    def sync_all_books_series(self, limit: Optional[int] = None) -> Tuple[int, int, List[str]]:
        """Sync series data for all books in the library."""
        try:
            books = self.db.get_all_books()

            if limit:
                books = books[:limit]

            successful = 0
            failed = 0
            errors: List[str] = []
            processed_series = set()

            self.logger.info("Starting series sync", extra={"book_count": len(books)})

            for book in books:
                book_asin = book.get("asin")

                if not book_asin or book_asin == "N/A":
                    continue

                try:
                    if book.get("series_asin") and book["series_asin"] in processed_series:
                        self.db.series.mark_series_book_as_owned(book["series_asin"], book_asin)
                        successful += 1
                        continue

                    success, message = self.sync_book_series(book_asin)

                    if success:
                        successful += 1
                        if book.get("series_asin"):
                            processed_series.add(book["series_asin"])
                    else:
                        failed += 1
                        errors.append(f"{book.get('title', book_asin)}: {message}")

                except Exception as e:
                    failed += 1
                    error_msg = f"{book.get('title', book_asin)}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(
                        "Series sync failure",
                        extra={
                            "book_asin": book_asin,
                            "book_title": book.get("title", book_asin),
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            self.logger.info(
                "Series sync complete",
                extra={"successful": successful, "failed": failed},
            )

            return successful, failed, errors

        except Exception as e:
            error_msg = f"Error in bulk series sync: {e}"
            self.logger.error("Error in bulk series sync", extra={"error": str(e)}, exc_info=True)
            return 0, 0, [error_msg]

    def sync_library_status(self) -> int:
        """Update in_library status for all series books based on current library."""
        try:
            updated = self.db.series.sync_library_status()
            self.logger.info("Synced library status", extra={"updated_count": updated})
            return updated

        except Exception as e:
            self.logger.error("Error syncing library status", extra={"error": str(e)}, exc_info=True)
            return 0
