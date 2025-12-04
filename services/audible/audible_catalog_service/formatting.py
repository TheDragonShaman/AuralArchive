import logging
from typing import List, Dict, Any, Optional
from .cover_utils import cover_utils

class AudibleFormatter:
    """Handles formatting and processing of Audible API response data"""
    
    def __init__(self):
        self.logger = logging.getLogger("AudibleService.Formatting")
    
    def process_search_results(self, products: List[Dict], region: str = "us") -> List[Dict]:
        """Process raw API results into standardized book data format"""
        books = []
        
        for book in products:
            try:
                formatted_book = self._format_single_book(book, region)
                books.append(formatted_book)
                
            except Exception as e:
                self.logger.error(f"Error processing book data: {e}")
                # Log the problematic book for debugging
                self.logger.debug(f"Problematic book data: {book.get('title', 'Unknown')}")
                continue
        
        self.logger.info(f"Successfully processed {len(books)} books")
        return books
    
    def _format_single_book(self, book: Dict, region: str) -> Dict[str, Any]:
        """Format a single book from API response to standardized format"""
        try:
            # Extract basic information
            asin = book.get("asin", "")
            title = book.get("title", "Unknown Title")
            
            # Debug: Log raw series data from API
            raw_series = book.get("series", [])
            if raw_series:
                self.logger.info(f"Raw series data for '{title}': {raw_series}")
            
            # Process runtime
            runtime_minutes = book.get("runtime_length_min", 0)
            runtime_str = self._format_runtime(runtime_minutes)
            
            # Process authors
            authors = book.get("authors", [])
            author_str = self._format_authors(authors)
            
            # Process narrators
            narrators = book.get("narrators", [])
            narrator_str = self._format_narrators(narrators)
            
            # Process series information
            series_info = book.get("series", [])
            series_name, series_sequence, series_asin_from_series_array = self._format_series(series_info)
            
            # Extract series ASIN from relationships (not from series array)
            series_asin = self._extract_series_asin_from_relationships(book)
            if not series_asin and series_asin_from_series_array:
                series_asin = series_asin_from_series_array
            
            # Debug logging for series extraction
            if series_asin:
                self.logger.info(f"Extracted series_asin '{series_asin}' for book '{title}'")
            else:
                self.logger.debug(f"No series_asin found for book '{title}'")
            
            # Process rating
            rating_info = book.get("rating", {})
            overall_rating = self._format_rating(rating_info)
            num_ratings = self._extract_num_ratings(rating_info)
            
            # Extract cover image
            cover_image = cover_utils.extract_cover_image(book, asin)
            
            # Process other fields
            release_date = self._format_release_date(book.get("release_date"))
            language = self._format_language(book.get("language"))
            publisher = book.get("publisher_name", "Unknown Publisher")
            summary = self._format_summary(book.get("publisher_summary", "") or 
                                           book.get("merchandising_summary", "") or
                                           book.get("description", "") or
                                           book.get("editorial_review", "") or
                                           "")
            
            # Build standardized book data
            book_data = {
                "Title": title,
                "Author": author_str,
                "Series": series_name,
                "Sequence": series_sequence,
                "series_asin": series_asin,  # Add series ASIN
                "Narrator": narrator_str,
                "Summary": summary,
                "Runtime": runtime_str,
                "Release Date": release_date,
                "Language": language,
                "Publisher": publisher,
                "Overall Rating": overall_rating,
                "num_ratings": num_ratings,  # Use lowercase to match database and routes
                "ASIN": asin,
                "Cover Image": cover_image,
                "Region": region
            }
            
            # Persist contributor metadata for downstream author handling
            formatted_contributors = self._format_contributors(book)
            if formatted_contributors:
                book_data["Contributors"] = formatted_contributors
                book_data["contributors"] = formatted_contributors

            self.logger.debug(f"Formatted book: {title} by {author_str}")
            return book_data
            
        except Exception as e:
            self.logger.error(f"Error formatting book {book.get('title', 'Unknown')}: {e}")
            raise
    
    def _format_runtime(self, runtime_minutes: int) -> str:
        """Format runtime from minutes to 'X hrs Y mins' format"""
        try:
            if not runtime_minutes or runtime_minutes <= 0:
                return "Unknown Runtime"
            
            hours = runtime_minutes // 60
            minutes = runtime_minutes % 60
            
            return f"{hours} hrs {minutes} mins"
            
        except Exception as e:
            self.logger.debug(f"Error formatting runtime {runtime_minutes}: {e}")
            return "Unknown Runtime"
    
    def _format_authors(self, authors: List[Dict]) -> str:
        """Format authors list into comma-separated string"""
        try:
            if not authors:
                return "Unknown Author"
            
            author_names = []
            for author in authors:
                if isinstance(author, dict) and "name" in author:
                    author_names.append(author["name"])
                elif isinstance(author, str):
                    author_names.append(author)
            
            return ", ".join(author_names) if author_names else "Unknown Author"
            
        except Exception as e:
            self.logger.debug(f"Error formatting authors {authors}: {e}")
            return "Unknown Author"
    
    def _format_narrators(self, narrators: List[Dict]) -> str:
        """Format narrators list into comma-separated string"""
        try:
            if not narrators:
                return "Unknown Narrator"
            
            narrator_names = []
            for narrator in narrators:
                if isinstance(narrator, dict) and "name" in narrator:
                    narrator_names.append(narrator["name"])
                elif isinstance(narrator, str):
                    narrator_names.append(narrator)
            
            return ", ".join(narrator_names) if narrator_names else "Unknown Narrator"
            
        except Exception as e:
            self.logger.debug(f"Error formatting narrators {narrators}: {e}")
            return "Unknown Narrator"
    
    def _format_series(self, series_info: List[Dict]) -> tuple[str, str, str]:
        """Format series information into series name, sequence, and ASIN"""
        try:
            if not series_info or not isinstance(series_info, list):
                return "N/A", "N/A", None
            
            # Take the first (primary) series
            primary_series = series_info[0] if series_info else {}
            
            if isinstance(primary_series, dict):
                series_name = primary_series.get("title", "N/A")
                series_sequence = str(primary_series.get("sequence", "N/A"))
                series_asin = primary_series.get("asin")  # Extract series ASIN
                return series_name, series_sequence, series_asin
            
            return "N/A", "N/A", None
            
        except Exception as e:
            self.logger.debug(f"Error formatting series {series_info}: {e}")
            return "N/A", "N/A", None
    
    def _extract_series_asin_from_relationships(self, book: Dict) -> Optional[str]:
        """Extract series ASIN from relationships (relationships response group required)"""
        try:
            # Check product.series array first (simpler, if available)
            product = book.get('product', book)
            series_array = product.get('series', [])
            if series_array and len(series_array) > 0:
                series_asin = series_array[0].get('asin')
                if series_asin:
                    return series_asin
            
            # Check relationships for parent series
            relationships = product.get('relationships', [])
            if not relationships:
                return None
            
            # Look for series relationship where relationship_to_product == "parent"
            for relationship in relationships:
                if (relationship.get('relationship_type') == 'series' and 
                    relationship.get('relationship_to_product') == 'parent'):
                    series_asin = relationship.get('asin')
                    if series_asin:
                        return series_asin
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting series ASIN from relationships: {e}")
            return None
    
    def _format_rating(self, rating_info: Dict) -> str:
        """Format rating information"""
        try:
            if not rating_info or not isinstance(rating_info, dict):
                return "N/A"
            
            # Try different rating fields
            overall_dist = rating_info.get("overall_distribution", {})
            if overall_dist and isinstance(overall_dist, dict):
                avg_rating = overall_dist.get("display_average_rating")
                if avg_rating:
                    return str(avg_rating)
            
            # Try alternative rating fields
            rating_value = rating_info.get("overall_rating") or rating_info.get("rating")
            if rating_value:
                return str(rating_value)
            
            return "N/A"
            
        except Exception as e:
            self.logger.debug(f"Error formatting rating {rating_info}: {e}")
            return "N/A"

    def _extract_num_ratings(self, rating_info: Dict) -> int:
        """Extract number of ratings from rating information"""
        try:
            if not rating_info or not isinstance(rating_info, dict):
                return 0
            
            # Extract from overall_distribution.num_ratings
            overall_dist = rating_info.get("overall_distribution", {})
            if overall_dist and isinstance(overall_dist, dict):
                num_ratings = overall_dist.get("num_ratings", 0)
                return int(num_ratings) if num_ratings else 0
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error extracting num_ratings {rating_info}: {e}")
            return 0
    
    def _format_release_date(self, release_date: Any) -> str:
        """Format release date"""
        try:
            if not release_date:
                return "Unknown"
            
            # Handle different date formats
            if isinstance(release_date, str):
                # Take first 10 characters for YYYY-MM-DD format
                return release_date[:10] if len(release_date) >= 10 else release_date
            
            return str(release_date)
            
        except Exception as e:
            self.logger.debug(f"Error formatting release date {release_date}: {e}")
            return "Unknown"
    
    def _format_language(self, language: Any) -> str:
        """Format language field"""
        try:
            if not language:
                return "English"  # Default assumption
            
            if isinstance(language, str):
                return language.capitalize()
            
            return str(language)
            
        except Exception as e:
            self.logger.debug(f"Error formatting language {language}: {e}")
            return "English"
    
    def _format_summary(self, summary: Any) -> str:
        """Format and clean summary text"""
        try:
            if not summary:
                return "No summary available."
            
            if isinstance(summary, str):
                # Clean up summary text
                cleaned = summary.strip()
                
                # Remove excessive whitespace
                import re
                cleaned = re.sub(r'\s+', ' ', cleaned)
                
                # Limit length if too long
                if len(cleaned) > 2000:
                    cleaned = cleaned[:1997] + "..."
                
                return cleaned if cleaned else "No summary available."
            
            return str(summary)
            
        except Exception as e:
            self.logger.debug(f"Error formatting summary: {e}")
            return "No summary available."

    def _format_contributors(self, book: Dict) -> List[Dict[str, Any]]:
        """Normalize contributor data from Audible responses."""
        try:
            contributors_source = book.get("contributors")

            # Some responses wrap product data under a nested key
            if not contributors_source and isinstance(book.get("product"), dict):
                contributors_source = book["product"].get("contributors")

            if not contributors_source or not isinstance(contributors_source, list):
                return []

            formatted: List[Dict[str, Any]] = []
            for contributor in contributors_source:
                if not isinstance(contributor, dict):
                    continue

                name = contributor.get("name") or contributor.get("Name")
                role = contributor.get("role") or contributor.get("Role")
                asin = contributor.get("asin") or contributor.get("ASIN")

                if not name or not role:
                    continue

                formatted.append({
                    "Name": name,
                    "Role": role if role else "Contributor",
                    "ASIN": asin
                })

            return formatted

        except Exception as e:
            self.logger.debug(f"Error formatting contributors: {e}")
            return []
    
    def format_book_for_display(self, book_data: Dict) -> Dict[str, Any]:
        """Format book data specifically for UI display"""
        try:
            display_data = book_data.copy()
            
            # Add computed fields for display
            display_data["author_short"] = self._truncate_text(book_data.get("Author", ""), 50)
            display_data["title_short"] = self._truncate_text(book_data.get("Title", ""), 60)
            display_data["summary_short"] = self._truncate_text(book_data.get("Summary", ""), 200)
            
            # Add runtime in different formats
            runtime = book_data.get("Runtime", "0 hrs 0 mins")
            display_data["runtime_minutes"] = self._parse_runtime_to_minutes(runtime)
            
            # Format rating for display
            rating = book_data.get("Overall Rating", "N/A")
            display_data["rating_stars"] = self._format_rating_stars(rating)
            
            return display_data
            
        except Exception as e:
            self.logger.error(f"Error formatting book for display: {e}")
            return book_data
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to specified length with ellipsis"""
        if not text or len(text) <= max_length:
            return text
        
        return text[:max_length-3] + "..."
    
    def _parse_runtime_to_minutes(self, runtime_str: str) -> int:
        """Parse runtime string back to minutes"""
        try:
            if not runtime_str or "hrs" not in runtime_str:
                return 0
            
            parts = runtime_str.split(" hrs")
            hours = int(parts[0])
            minutes = 0
            
            if len(parts) > 1 and "mins" in parts[1]:
                minutes = int(parts[1].split(" mins")[0].strip())
            
            return hours * 60 + minutes
            
        except Exception:
            return 0
    
    def _format_rating_stars(self, rating: str) -> str:
        """Format rating as star representation"""
        try:
            if rating == "N/A" or not rating:
                return "☆☆☆☆☆"
            
            rating_float = float(rating)
            full_stars = int(rating_float)
            half_star = rating_float - full_stars >= 0.5
            
            stars = "★" * full_stars
            if half_star:
                stars += "☆"
            stars += "☆" * (5 - len(stars))
            
            return stars
            
        except Exception:
            return "☆☆☆☆☆"

# Global instance for easy access
formatter = AudibleFormatter()

