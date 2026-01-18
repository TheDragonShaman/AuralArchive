"""
Module Name: series_data_fetcher.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Fetch complete series metadata and books from Audible using the shared client.
Location:
    /services/audible/audible_series_service/series_data_fetcher.py

"""

from utils.logger import get_module_logger


class SeriesDataFetcher:
    """Fetches series data from Audible API."""
    
    def __init__(self, audible_client, logger=None):
        """
        Initialize with Audible API client
        
        Args:
            audible_client: Authenticated Audible API client
        """
        self.logger = logger or get_module_logger("Service.Audible.Series.DataFetcher")
        self.client = audible_client
    
    def fetch_series_metadata(self, series_asin):
        """
        Fetch series metadata from Audible API
        
        Args:
            series_asin: The ASIN of the series
            
        Returns:
            dict: Series metadata including title, description, cover_url, etc.
        """
        try:
            self.logger.debug("Fetching series metadata", extra={"series_asin": series_asin})
            
            # Query Audible API for series information
            # Note: This uses the catalog/products endpoint with the series ASIN
            response = self.client.get(
                f"1.0/catalog/products/{series_asin}",
                response_groups="product_desc,product_extended_attrs,media,relationships,customer_rights"
            )
            
            if not response:
                self.logger.warning(
                    "No response for series ASIN",
                    extra={"series_asin": series_asin},
                )
                return None
            
            # Handle both wrapped and unwrapped responses
            product = response.get('product', response)
            
            series_data = {
                'series_asin': series_asin,
                'series_title': product.get('title'),
                'series_url': product.get('url'),
                'sku': product.get('sku'),
                'description': product.get('publisher_summary', ''),
                'cover_url': self._extract_cover_url(product),
                'total_books': self._extract_total_books(product)
            }
            
            self.logger.info(
                "Fetched series metadata",
                extra={"series_asin": series_asin, "series_title": series_data.get('series_title')},
            )
            return series_data
            
        except Exception as e:
            self.logger.error(
                "Error fetching series metadata",
                extra={"series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return None
    
    def fetch_series_books(self, series_asin):
        """
        Fetch all books in a series from Audible API with complete metadata
        
        Args:
            series_asin: The ASIN of the series
            
        Returns:
            list: List of book metadata dicts for all books in the series
        """
        try:
            self.logger.debug("Fetching all books for series", extra={"series_asin": series_asin})
            
            # Query for series with relationships to get all book ASINs
            response = self.client.get(
                f"1.0/catalog/products/{series_asin}",
                response_groups="relationships,product_desc,customer_rights"
            )
            
            if not response:
                return []
            
            # Handle both wrapped and unwrapped responses
            product = response.get('product', response)
            relationships = product.get('relationships', [])
            
            # Extract all child books from series relationships
            # Look for relationship_type == 'series' AND relationship_to_product == 'child'
            book_asins = []
            for relationship in relationships:
                if (relationship.get('relationship_type') == 'series' and 
                    relationship.get('relationship_to_product') == 'child'):
                    book_asins.append({
                        'asin': relationship.get('asin'),
                        'sequence': relationship.get('sequence', ''),
                        'sort_order': int(relationship.get('sort', 0))
                    })
            
            self.logger.info(
                "Found books in series; fetching detailed metadata",
                extra={"series_asin": series_asin, "count": len(book_asins)},
            )
            
            # Now fetch full metadata for each book
            books = []
            for book_info in book_asins:
                book_asin = book_info['asin']
                try:
                    # Fetch complete book metadata
                    book_metadata = self.fetch_book_metadata(book_asin)
                    if book_metadata:
                        # Merge sequence info with metadata
                        book_metadata['sequence'] = book_info['sequence']
                        book_metadata['sort_order'] = book_info['sort_order']
                        books.append(book_metadata)
                    else:
                        # If we can't fetch metadata, use minimal data
                        self.logger.warning(
                            "Could not fetch metadata for book; using minimal data",
                            extra={"book_asin": book_asin},
                        )
                        books.append({
                            'asin': book_asin,
                            'title': 'Unknown',
                            'sequence': book_info['sequence'],
                            'sort_order': book_info['sort_order']
                        })
                except Exception as e:
                    self.logger.error(
                        "Error fetching metadata for book",
                        extra={"book_asin": book_asin, "error": str(e)},
                        exc_info=True,
                    )
                    # Add minimal book data so we don't lose the book entirely
                    books.append({
                        'asin': book_asin,
                        'title': 'Unknown',
                        'sequence': book_info['sequence'],
                        'sort_order': book_info['sort_order']
                    })
            
            self.logger.info(
                "Fetched metadata for series books",
                extra={"series_asin": series_asin, "count": len(books)},
            )
            return books
            
        except Exception as e:
            self.logger.error(
                "Error fetching series books",
                extra={"series_asin": series_asin, "error": str(e)},
                exc_info=True,
            )
            return []
    
    def fetch_book_metadata(self, book_asin):
        """
        Fetch complete metadata for a single book
        
        Args:
            book_asin: The ASIN of the book
            
        Returns:
            dict: Complete book metadata
        """
        try:
            self.logger.info("Fetching metadata for book", extra={"book_asin": book_asin})
            
            response = self.client.get(
                f"1.0/catalog/products/{book_asin}",
                params={
                    # Request series, relationships, and customer rights so downstream extractors can identify series membership
                    "response_groups": "product_desc,product_extended_attrs,contributors,media,rating,series,relationships,customer_rights",
                    "image_sizes": "500"
                }
            )
            
            if not response:
                self.logger.warning(
                    "No response from Audible API for book",
                    extra={"book_asin": book_asin},
                )
                return None
                
            if 'product' not in response:
                self.logger.warning("No 'product' key in response for book", extra={"book_asin": book_asin})
                self.logger.debug(
                    "Response keys for book fetch",
                    extra={"book_asin": book_asin, "keys": list(response.keys())},
                )
                return None
            
            product = response['product']
            self.logger.info(
                "Successfully fetched metadata for book",
                extra={"book_asin": book_asin, "title": product.get('title', 'Unknown')},
            )
            
            # Extract all the metadata we need
            customer_rights = product.get('customer_rights') or {}
            metadata = {
                'asin': book_asin,
                'title': product.get('title', 'Unknown'),
                'author': self._extract_authors(product),
                'narrator': self._extract_narrators(product),
                'publisher': product.get('publisher_name', 'Unknown'),
                'release_date': product.get('release_date', ''),
                'runtime': self._extract_runtime(product),
                'rating': self._extract_rating(product),
                'num_ratings': self._extract_num_ratings(product),
                'summary': product.get('publisher_summary', 'No summary available'),
                'cover_image': self._extract_cover_url(product),
                'language': product.get('language', 'en'),
                'customer_rights': customer_rights,
                'is_buyable': product.get('is_buyable', customer_rights.get('is_buyable')),
                'product_state': product.get('product_state', customer_rights.get('product_state')),
                # Preserve raw product metadata for series extraction logic
                'product': {
                    'series': product.get('series', []),
                    'relationships': product.get('relationships', []),
                    'title': product.get('title'),
                    'asin': product.get('asin')
                }
            }
            
            self.logger.debug(
                "Extracted metadata",
                extra={
                    "book_asin": book_asin,
                    "title": metadata['title'],
                    "author": metadata['author'],
                    "narrator": metadata['narrator'],
                },
            )
            return metadata
            
        except Exception as e:
            self.logger.error(
                "Error fetching book metadata",
                extra={"book_asin": book_asin, "error": str(e)},
                exc_info=True,
            )
            return None
    
    def _extract_authors(self, product):
        """Extract author names from product"""
        try:
            authors = []
            for contributor in product.get('authors', []):
                if contributor.get('name'):
                    authors.append(contributor['name'])
            return ', '.join(authors) if authors else 'Unknown Author'
        except Exception:
            return 'Unknown Author'
    
    def _extract_narrators(self, product):
        """Extract narrator names from product"""
        try:
            narrators = []
            for contributor in product.get('narrators', []):
                if contributor.get('name'):
                    narrators.append(contributor['name'])
            return ', '.join(narrators) if narrators else 'Unknown Narrator'
        except Exception:
            return 'Unknown Narrator'
    
    def _extract_runtime(self, product):
        """Extract runtime in minutes from product"""
        try:
            return product.get('runtime_length_min', 0)
        except Exception:
            return 0
    
    def _extract_rating(self, product):
        """Extract rating from product"""
        try:
            rating = product.get('rating', {})
            return rating.get('overall_distribution', {}).get('display_average_rating', '')
        except Exception:
            return ''
    
    def _extract_num_ratings(self, product):
        """Extract number of ratings from product"""
        try:
            rating = product.get('rating', {})
            return rating.get('overall_distribution', {}).get('num_ratings', 0)
        except Exception:
            return 0
    
    def _extract_cover_url(self, product):
        """Extract cover image URL from product data"""
        try:
            images = product.get('product_images', {})
            # Try to get the largest available image
            for size in ['2400', '1215', '500', '252']:
                if size in images:
                    return images[size]
            return None
        except Exception:
            return None
    
    def _extract_total_books(self, product):
        """Extract total number of books from series metadata"""
        try:
            # This might be in extended attributes or relationships count
            relationships = product.get('relationships', [])
            child_count = sum(1 for r in relationships if r.get('type') == 'child')
            return child_count if child_count > 0 else None
        except Exception:
            return None
