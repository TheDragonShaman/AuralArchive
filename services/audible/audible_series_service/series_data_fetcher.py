"""
Series Data Fetcher
Fetches complete series data from Audible API using series ASIN
"""

from utils.logger import get_module_logger

LOGGER_NAME = "SeriesDataFetcher"
logger = get_module_logger(LOGGER_NAME)


class SeriesDataFetcher:
    """Fetches series data from Audible API"""
    
    def __init__(self, audible_client):
        """
        Initialize with Audible API client
        
        Args:
            audible_client: Authenticated Audible API client
        """
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
            logger.debug(f"Fetching series metadata for {series_asin}")
            
            # Query Audible API for series information
            # Note: This uses the catalog/products endpoint with the series ASIN
            response = self.client.get(
                f"1.0/catalog/products/{series_asin}",
                response_groups="product_desc,product_extended_attrs,media,relationships,customer_rights"
            )
            
            if not response:
                logger.warning(f"No response for series ASIN: {series_asin}")
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
            
            logger.info(f"Fetched series metadata for {series_data.get('series_title')}")
            return series_data
            
        except Exception as e:
            logger.error(f"Error fetching series metadata for {series_asin}: {e}")
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
            logger.debug(f"Fetching all books for series {series_asin}")
            
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
            
            logger.info(f"Found {len(book_asins)} books in series {series_asin}; fetching detailed metadata")
            
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
                        logger.warning(f"Could not fetch metadata for book {book_asin}, using minimal data")
                        books.append({
                            'asin': book_asin,
                            'title': 'Unknown',
                            'sequence': book_info['sequence'],
                            'sort_order': book_info['sort_order']
                        })
                except Exception as e:
                    logger.error(f"Error fetching metadata for book {book_asin}: {e}")
                    # Add minimal book data so we don't lose the book entirely
                    books.append({
                        'asin': book_asin,
                        'title': 'Unknown',
                        'sequence': book_info['sequence'],
                        'sort_order': book_info['sort_order']
                    })
            
            logger.info(f"Fetched metadata for {len(books)} books in series {series_asin}")
            return books
            
        except Exception as e:
            logger.error(f"Error fetching series books for {series_asin}: {e}")
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
            logger.info(f"Fetching metadata for book {book_asin}")
            
            response = self.client.get(
                f"1.0/catalog/products/{book_asin}",
                params={
                    # Request series, relationships, and customer rights so downstream extractors can identify series membership
                    "response_groups": "product_desc,product_extended_attrs,contributors,media,rating,series,relationships,customer_rights",
                    "image_sizes": "500"
                }
            )
            
            if not response:
                logger.warning(f"No response from Audible API for book {book_asin}")
                return None
                
            if 'product' not in response:
                logger.warning(f"No 'product' key in response for book {book_asin}")
                logger.debug(f"Response keys: {list(response.keys())}")
                return None
            
            product = response['product']
            logger.info(f"Successfully fetched metadata for book: {product.get('title', 'Unknown')}")
            
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
            
            logger.debug(f"Extracted metadata: title={metadata['title']}, author={metadata['author']}, narrator={metadata['narrator']}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error fetching book metadata for {book_asin}: {e}", exc_info=True)
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
