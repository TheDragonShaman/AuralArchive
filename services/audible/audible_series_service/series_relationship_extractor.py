"""
Module Name: series_relationship_extractor.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 23, 2025
Description:
    Extract series ASIN and metadata from Audible relationships response groups.
Location:
    /services/audible/audible_series_service/series_relationship_extractor.py

"""

from utils.logger import get_module_logger


class SeriesRelationshipExtractor:
    """Extracts series information from Audible API book relationships."""

    def __init__(self, logger=None):
        self.logger = logger or get_module_logger("Service.Audible.Series.RelationshipExtractor")
    
    def extract_series_asin(self, book_metadata):
        """
        Extract series ASIN from book metadata relationships
        
        Args:
            book_metadata: Full book metadata from Audible API with relationships response group
            
        Returns:
            str: Series ASIN if found, None otherwise
        """
        try:
            if not book_metadata:
                return None
            
            # Try method 1: Check product.series array (simpler)
            product = book_metadata.get('product', book_metadata)
            series_array = product.get('series', [])
            if series_array and len(series_array) > 0:
                series_asin = series_array[0].get('asin')
                if series_asin:
                    self.logger.info("Found series ASIN from series array", extra={"series_asin": series_asin})
                    return series_asin
            
            # Method 2: Check relationships for parent series
            relationships = product.get('relationships', [])
            if not relationships:
                self.logger.debug("No relationships or series found in book metadata")
                return None
            
            # Look for series relationship where relationship_to_product == "parent"
            for relationship in relationships:
                if (relationship.get('relationship_type') == 'series' and 
                    relationship.get('relationship_to_product') == 'parent'):
                    series_asin = relationship.get('asin')
                    if series_asin:
                        self.logger.info(
                            "Found series ASIN from relationships",
                            extra={"series_asin": series_asin},
                        )
                        return series_asin
            
            self.logger.debug("No series relationship found")
            return None
            
        except Exception as e:
            self.logger.error("Error extracting series ASIN", extra={"error": str(e)}, exc_info=True)
            return None
    
    def extract_series_metadata(self, book_metadata):
        """
        Extract series metadata (title, sequence, etc.) from book relationships
        
        Args:
            book_metadata: Full book metadata from Audible API
            
        Returns:
            dict: Series metadata containing asin, title, sequence, url
        """
        try:
            product = book_metadata.get('product', book_metadata)
            
            # Method 1: Try the simple series array first
            series_array = product.get('series', [])
            if series_array and len(series_array) > 0:
                first_series = series_array[0]
                series_data = {
                    'series_asin': first_series.get('asin'),
                    'series_title': first_series.get('title'),
                    'series_url': first_series.get('url'),
                    'sku': None,  # Not in series array
                    'sequence': first_series.get('sequence')
                }
                self.logger.info(
                    "Extracted series metadata from series array",
                    extra={"series_asin": series_data.get('series_asin'), "series_title": series_data.get('series_title')},
                )
                return series_data
            
            # Method 2: Check relationships for parent series (has more details)
            relationships = product.get('relationships', [])
            
            for relationship in relationships:
                if (
                    relationship.get('relationship_type') == 'series'
                    and relationship.get('relationship_to_product') == 'parent'
                ):
                    series_data = {
                        'series_asin': relationship.get('asin'),
                        'series_title': relationship.get('title'),
                        'series_url': relationship.get('url'),
                        'sku': relationship.get('sku'),
                        'sequence': relationship.get('sequence'),  # Book's position in series
                    }

                    self.logger.info(
                        "Extracted series metadata from relationships",
                        extra={"series_asin": series_data.get('series_asin'), "series_title": series_data.get('series_title')},
                    )
                    return series_data

            self.logger.warning("No series information found")
            return None

        except Exception as e:
            self.logger.error("Error extracting series metadata", extra={"error": str(e)}, exc_info=True)
            return None
