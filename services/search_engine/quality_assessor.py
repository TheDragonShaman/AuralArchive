"""
Quality Assessor - Quality scoring system for audiobook search results
Assesses format preferences, bitrate, source reputation, and metadata completeness

Location: services/search_engine/quality_assessor.py
Purpose: Evaluate and rank search results by quality metrics
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
from dataclasses import dataclass
import re
from .fuzzy_matcher import FuzzyMatcher


@dataclass
class QualityScore:
    """Represents a quality assessment result."""
    total_score: float
    format_score: float
    bitrate_score: float
    source_score: float
    metadata_score: float
    relevance_score: float  # 0-10 how well result matches search query
    confidence: float  # 0-100 confidence percentage
    breakdown: Dict[str, Any]


class QualityAssessor:
    """
    Assesses the quality of audiobook search results.
    
    Features:
    - Format preferences (M4B > M4A > MP3)
    - Bitrate scoring (64kbps minimum, 128kbps preferred)
    - Source reputation assessment
    - Metadata completeness evaluation
    - Weighted quality calculation
    """
    
    def __init__(self):
        """Initialize the quality assessor."""
        self.logger = logging.getLogger("SearchEngineService.QualityAssessor")
        
        # Format preferences (higher score = better)
        self.format_scores = {
            'm4b': 10,    # Best for audiobooks
            'm4a': 8,     # Good quality
            'mp3': 6,     # Acceptable
            'aac': 5,     # Lower quality
            'ogg': 4,     # Less common
            'flac': 7,    # High quality but large
            'unknown': 1  # Unknown format
        }
        
        # Bitrate preferences
        self.min_bitrate = 64      # Minimum acceptable
        self.preferred_bitrate = 128  # Preferred quality
        self.max_useful_bitrate = 320  # Diminishing returns above this
        
        # Weighting for final score calculation
        # GOAL: Find the RIGHT book - relevance is almost everything
        self.weights = {
            'relevance': 0.95,    # Finding the correct book (dominant factor)
            'format': 0.03,       # Minor preference toward better container
            'bitrate': 0.00,
            'source': 0.00,
            'metadata': 0.02,
            'availability': 0.00
        }
        
        self.initialized = False
        self._initialize()
    
    def _initialize(self):
        """Initialize the quality assessor."""
        try:
            self.logger.debug("Initializing QualityAssessor...")
            
            # Initialize fuzzy matcher for relevance scoring
            self.fuzzy_matcher = FuzzyMatcher()
            
            # Validate configuration
            if not self.format_scores or not self.weights:
                raise Exception("Missing configuration data")
            
            self.initialized = True
            self.logger.debug("QualityAssessor initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize QualityAssessor: {e}")
            self.initialized = False

    @staticmethod
    def _extract_numbers(text: str) -> List[str]:
        """Return all standalone numeric tokens present in the supplied text."""
        if not text:
            return []
        return re.findall(r"\b(\d+)\b", str(text))
    
    def assess_result_quality(self, result: Dict[str, Any], search_title: str = '', search_author: str = '') -> QualityScore:
        """
        Assess the quality of a search result.
        
        Args:
            result: Search result dictionary
            search_title: User's search title query
            search_author: User's search author query
            
        Returns:
            QualityScore with relevance-weighted assessment
        """
        try:
            self.logger.info(f"⚙️ assess_result_quality called: search_title='{search_title}', search_author='{search_author}', result_title='{result.get('title', 'N/A')}'")
            
            # Extract result data
            format_str = result.get('format', 'unknown').lower()
            bitrate = result.get('bitrate', 0)
            seeders = result.get('seeders', 0)
            result_title = result.get('title', '')
            result_author = result.get('author', '')
            
            # Assess each component
            relevance_score, relevance_meta = self._assess_relevance(
                result_title,
                result_author,
                search_title,
                search_author
            )
            format_score = self._assess_format_quality(format_str)
            bitrate_score = self._assess_bitrate_quality(bitrate)
            source_score = 7.0  # Default source score
            metadata_score = self._assess_metadata_quality(result)
            availability_score = self._assess_availability_quality(seeders)

            # AudiobookBay always shows seeders as 1; don't penalize those results
            indexer_name = (result.get('indexer') or '').lower()
            source_tag = (result.get('_source') or '').lower()
            if ('audiobookbay' in indexer_name or 'audiobookbay' in source_tag) and seeders <= 1:
                availability_score = 8.0  # treat as healthy to avoid low-seeder penalties
            
            self.logger.info(f"Quality scores for '{result_title}': relevance={relevance_score:.1f}, format={format_score:.1f}, confidence will be calculated")
            
            # Calculate weighted total
            total_score = (
                relevance_score * self.weights['relevance'] +
                format_score * self.weights['format'] +
                bitrate_score * self.weights['bitrate'] +
                source_score * self.weights['source'] +
                metadata_score * self.weights['metadata'] +
                availability_score * self.weights['availability']
            )
            
            # Calculate confidence percentage (0-100)
            confidence = self._calculate_confidence(
                total_score=total_score,
                format_score=format_score,
                bitrate_score=bitrate_score,
                metadata_score=metadata_score,
                availability_score=availability_score,
                result=result,
                relevance_meta=relevance_meta
            )
            
            return QualityScore(
                total_score=total_score,
                format_score=format_score,
                bitrate_score=bitrate_score,
                source_score=source_score,
                metadata_score=metadata_score,
                relevance_score=relevance_score,
                confidence=confidence,
                breakdown={
                    'relevance_score': relevance_score,
                    'book_number_status': relevance_meta.get('book_number_status'),
                    'author': relevance_meta.get('author'),
                    'title': relevance_meta.get('title'),
                    'series': relevance_meta.get('series')
                }
            )
            
        except Exception as e:
            import traceback
            self.logger.error(f"Quality assessment failed: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return QualityScore(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {})
    
    def _assess_relevance(self, result_title: str, result_author: str, 
                          search_title: str, search_author: str) -> Tuple[float, Dict[str, Any]]:
        """
        Assess how well the result matches the search query using multi-strategy matching.
        
        Relevance Scoring (NEW SYSTEM):
        - Author match: 60% weight (0-6 points) - MOST IMPORTANT
          Strategy 1: Exact normalized match (remove ALL punctuation/spaces)
          Strategy 2: Token set overlap (handles "Author1, Author2")
          Strategy 3: Fuzzy character match (handles typos)
        
        - Title match: 25% weight (0-2.5 points)
          Strategy 1: All search tokens present in result
          Strategy 2: Token set overlap (70%+ words match)
          Strategy 3: Substring or fuzzy match
        
        - Series match: 15% weight (0-1.5 points)
        
        Total: 0-10 points
        
        Args:
            result_title: The title from the search result
            result_author: The author from the search result
            search_title: User's search title query
            search_author: User's search author query
            
        Returns:
            Relevance score (0-10)
        """
        # Convert None to empty string to avoid AttributeError
        search_title = search_title or ''
        search_author = search_author or ''
        result_title = result_title or ''
        result_author = result_author or ''
        
        score = 0.0
        meta: Dict[str, Any] = {
            'author': {'score': 0.0, 'status': 'unknown'},
            'title': {'score': 0.0, 'status': 'unknown'},
            'series': {'score': 0.0, 'status': 'unknown'},
            'book_number_status': 'not_applicable',
            'search_numbers': [],
            'result_numbers': []
        }
        
        # If no search query provided, give default neutral score
        if not search_title and not search_author:
            return 5.0, meta  # Neutral relevance when no search criteria
        
        # ========================================
        # AUTHOR MATCHING (60% = 6 points max)
        # ========================================
        author_score = 0.0
        if search_author and result_author:
            # Strategy 1: Exact normalized match (aggressive - strips ALL punctuation/spaces)
            # This catches: "SouppatchHero" vs "Sourpatch Hero" vs "Sourpatchhero"
            search_author_norm = self.fuzzy_matcher.normalize_author(search_author)
            result_author_norm = self.fuzzy_matcher.normalize_author(result_author)
            
            self.logger.debug(f"Author norm: search='{search_author_norm}' result='{result_author_norm}'")
            
            # Check if search author is CONTAINED in result author (handles extra text in result)
            if search_author_norm in result_author_norm or result_author_norm in search_author_norm:
                # Normalized substring match!
                author_score = 6.0
                self.logger.debug(f"✓ Author EXACT normalized match (substring): {author_score}/6.0")
            else:
                # Strategy 2: Token set overlap (handles multiple authors)
                # Tokenize using normalized titles first
                search_author_cleaned = self.fuzzy_matcher.normalize_title(search_author)
                result_author_cleaned = self.fuzzy_matcher.normalize_title(result_author)
                
                search_tokens = self.fuzzy_matcher.tokenize(search_author_cleaned)
                result_tokens = self.fuzzy_matcher.tokenize(result_author_cleaned)
                
                if search_tokens and result_tokens:
                    # Check if ANY search author token appears in result
                    # (handles "Tommy Kerper, SourpatchHero" searches)
                    common = search_tokens & result_tokens
                    
                    if common:
                        overlap = len(common) / max(len(search_tokens), len(result_tokens))
                        
                        if overlap >= 0.5:  # 50%+ overlap is good
                            author_score = 6.0 * overlap
                            self.logger.debug(f"✓ Author TOKEN overlap ({overlap:.0%}): {author_score:.1f}/6.0")
                        else:
                            # Strategy 3: Fuzzy character match (handles typos)
                            author_match = self.fuzzy_matcher.fuzzy_match(result_author, search_author)
                            
                            if author_match.score >= 0.7:  # Lowered from 0.95
                                author_score = 6.0 * author_match.score
                                self.logger.debug(f"✓ Author FUZZY match ({author_match.score:.0%}): {author_score:.1f}/6.0")
                    else:
                        # No token overlap, try fuzzy
                        author_match = self.fuzzy_matcher.fuzzy_match(result_author, search_author)
                        if author_match.score >= 0.7:
                            author_score = 6.0 * author_match.score
                            self.logger.debug(f"✓ Author FUZZY match ({author_match.score:.0%}): {author_score:.1f}/6.0")
                else:
                    # Fallback to fuzzy match
                    author_match = self.fuzzy_matcher.fuzzy_match(result_author, search_author)
                    if author_match.score >= 0.7:
                        author_score = 6.0 * author_match.score
                        self.logger.debug(f"✓ Author FUZZY match ({author_match.score:.0%}): {author_score:.1f}/6.0")
            
            if author_score == 0.0:
                self.logger.debug(f"✗ Author NO match: 0.0/6.0")
        elif search_author:
            # Author was searched but result has no author - penalty
            author_score = 0.0
            self.logger.debug(f"✗ Author missing in result: 0.0/6.0")
        else:
            # No author search, give neutral score
            author_score = 3.0
            self.logger.debug(f"○ Author not searched (neutral): 3.0/6.0")
        
        meta['author']['score'] = author_score
        if not search_author:
            meta['author']['status'] = 'not_provided'
        elif author_score > 0:
            meta['author']['status'] = 'match'
        else:
            meta['author']['status'] = 'no_match'

        score += author_score
        
        # Extract series information from result title
        result_series = self._extract_series_from_title(result_title)
        search_series = self._extract_series_from_title(search_title)
        
        # Debug: Log what was extracted
        self.logger.debug(f"📚 Series extraction:")
        self.logger.debug(f"  Search '{search_title}' → series='{search_series['series_name']}' book#={search_series['book_number']}")
        self.logger.debug(f"  Result '{result_title}' → series='{result_series['series_name']}' book#={result_series['book_number']}")
        
        # ========================================
        # TITLE MATCHING (25% = 2.5 points max)
        # ========================================
        title_score = 0.0
        if search_title and result_title:
            # Normalize titles for comparison
            search_title_norm = self.fuzzy_matcher.normalize_title(search_title)
            result_title_norm = self.fuzzy_matcher.normalize_title(result_title)
            
            # Remove series info to get core title
            if result_series['full_series']:
                result_title_core = result_title_norm.replace(result_series['full_series'].lower(), '').strip(' ,:;-')
            else:
                result_title_core = result_title_norm
                
            if search_series['full_series']:
                search_title_core = search_title_norm.replace(search_series['full_series'].lower(), '').strip(' ,:;-')
            else:
                search_title_core = search_title_norm
            
            self.logger.debug(f"Title norm: search='{search_title_core}' result='{result_title_core}'")
            
            # Strategy 1: Tokenize and check if ALL search tokens are in result
            search_tokens = self.fuzzy_matcher.tokenize(search_title_core)
            result_tokens = self.fuzzy_matcher.tokenize(result_title_core)
            
            if search_tokens and result_tokens:
                # Check if all search tokens appear in result
                if search_tokens.issubset(result_tokens):
                    # Perfect token match!
                    title_score = 2.5
                    self.logger.debug(f"✓ Title ALL tokens match: {title_score}/2.5")
                else:
                    # Strategy 2: Token set overlap (partial match)
                    overlap = self.fuzzy_matcher.token_set_overlap(search_tokens, result_tokens)
                    
                    if overlap >= 0.7:  # 70%+ words match
                        title_score = 2.5 * overlap
                        self.logger.debug(f"✓ Title TOKEN overlap ({overlap:.0%}): {title_score:.1f}/2.5")
                    else:
                        # Strategy 3: Substring check (handles split titles like "Secrets and Strife" + "An Isekai")
                        if (search_title_core in result_title_core or 
                            result_title_core in search_title_core or
                            search_title_norm in result_title_norm or 
                            result_title_norm in search_title_norm):
                            title_score = 2.5
                            self.logger.debug(f"✓ Title SUBSTRING match: {title_score}/2.5")
                        else:
                            # Strategy 4: Fuzzy character match (last resort)
                            title_match = self.fuzzy_matcher.fuzzy_match(result_title_core, search_title_core)
                            
                            if title_match.score >= 0.7:  # Lowered from 0.8
                                title_score = 2.5 * title_match.score
                                self.logger.debug(f"✓ Title FUZZY match ({title_match.score:.0%}): {title_score:.1f}/2.5")
            else:
                # No tokens, fall back to substring/fuzzy
                if search_title_core in result_title_core or result_title_core in search_title_core:
                    title_score = 2.5
                    self.logger.debug(f"✓ Title SUBSTRING match: {title_score}/2.5")
                else:
                    title_match = self.fuzzy_matcher.fuzzy_match(result_title_core, search_title_core)
                    if title_match.score >= 0.7:
                        title_score = 2.5 * title_match.score
                        self.logger.debug(f"✓ Title FUZZY match ({title_match.score:.0%}): {title_score:.1f}/2.5")
            
            # CRITICAL: Check book number alignment using strict matching
            search_numbers = self._extract_numbers(search_title)
            result_numbers = self._extract_numbers(result_title)
            meta['search_numbers'] = search_numbers
            meta['result_numbers'] = result_numbers

            if search_numbers:
                if result_numbers:
                    if set(search_numbers) & set(result_numbers):
                        title_score = min(title_score + 0.75, 2.5)
                        meta['book_number_status'] = 'match'
                        self.logger.debug(
                            f"✓ Book number MATCH (search: {search_numbers}, result: {result_numbers})"
                        )
                    else:
                        title_score = 0.0
                        meta['book_number_status'] = 'mismatch'
                        self.logger.debug(
                            f"✗ Book number MISMATCH (search: {search_numbers} vs result: {result_numbers})"
                        )
                else:
                    title_score *= 0.2  # retain a hint of relevance but heavily penalize
                    meta['book_number_status'] = 'result_missing'
                    self.logger.debug(
                        f"⚠ Book number missing in result (wanted {search_numbers})"
                    )
            elif result_numbers:
                meta['book_number_status'] = 'search_missing'
            else:
                meta['book_number_status'] = 'not_applicable'
            
            if title_score == 0.0:
                self.logger.debug(f"✗ Title NO match: 0.0/2.5")
        elif search_title:
            # Title was searched but result has no title
            title_score = 0.0
            self.logger.debug(f"✗ Title missing in result: 0.0/2.5")
        else:
            # No title search, give neutral score
            title_score = 1.25
            self.logger.debug(f"○ Title not searched (neutral): 1.25/2.5")
        
        meta['title']['score'] = title_score
        if not search_title:
            meta['title']['status'] = 'not_provided'
        elif title_score > 0:
            meta['title']['status'] = 'match'
        else:
            meta['title']['status'] = 'no_match'

        score += title_score
        
        # ========================================
        # SERIES MATCHING (15% = 1.5 points max)
        # ========================================
        series_score = 0.0
        if result_series['series_name'] and search_series['series_name']:
            # Both have series info - compare them
            series_match = self.fuzzy_matcher.fuzzy_match(
                result_series['series_name'], 
                search_series['series_name']
            )
            
            self.logger.debug(f"Series match: '{result_series['series_name']}' vs '{search_series['series_name']}' = {series_match.score:.2f}")
            
            # More lenient series matching
            if series_match.exact or series_match.score >= 0.8:  # Lowered from 0.9
                series_score = 1.5
            elif series_match.score >= 0.7:  # Lowered from 0.8
                series_score = 1.2
            elif series_match.score >= 0.6:  # Lowered from 0.7
                series_score = 0.9
            elif series_match.score >= 0.5:  # Lowered from 0.6
                series_score = 0.6
            # Below 50% = 0 points
                
            # Bonus if book numbers match
            if (result_series['book_number'] and search_series['book_number'] and 
                result_series['book_number'] == search_series['book_number']):
                series_score = min(series_score + 0.3, 1.5)  # Cap at max
                self.logger.debug(f"Book number match bonus: {result_series['book_number']}")
        elif search_series['series_name'] and not result_series['series_name']:
            # Search specified series but result doesn't have it - slight penalty
            series_score = 0.0
        elif result_series['series_name'] and search_title and search_series['series_name']:
            # Result has series, check if series name appears in search query
            if search_series['series_name'].lower() in search_title.lower():
                series_score = 1.0
                self.logger.debug(f"Series name found in search query: {result_series['series_name']}")
        else:
            # No series matching needed, give neutral score
            series_score = 0.75
        
        meta['series']['score'] = series_score
        if not (result_series['series_name'] and search_series['series_name']):
            meta['series']['status'] = 'not_applicable'
        elif series_score > 0:
            meta['series']['status'] = 'match'
        else:
            meta['series']['status'] = 'no_match'

        score += series_score
        
        self.logger.debug(f"🎯 FINAL relevance: {score:.1f}/10 (author: {author_score:.1f}/6, title: {title_score:.1f}/2.5, series: {series_score:.1f}/1.5)")
        meta['combined_score'] = min(score, 10.0)
        return min(score, 10.0), meta
    
    def _extract_series_from_title(self, title: str) -> Dict[str, Any]:
        """
        Extract series information from a title.
        
        Handles patterns like:
        - "Title: Series Name, Book 3"
        - "Title (Series Name, #3)"
        - "Title [Series Name 3]"
        - "Series Name: Title"
        
        Returns:
            Dict with series_name, book_number, and full_series string
        """
        import re
        
        result = {
            'series_name': None,
            'book_number': None,
            'full_series': None
        }
        
        if not title:
            return result
        
        # Pattern 1: "Title: Series Name, Book 3" or "Title Series Name, Book 3"
        match = re.search(r'[:\s]([^,:]+),\s*(?:Book|#)\s*(\d+)', title, re.IGNORECASE)
        if match:
            result['series_name'] = match.group(1).strip()
            result['book_number'] = match.group(2)
            result['full_series'] = match.group(0).strip(':, ')
            return result
        
        # Pattern 2: "Title (Series Name #3)" or "Title [Series Name 3]"
        match = re.search(r'[\(\[]([^)\]]+?)\s*[#\s](\d+)[\)\]]', title)
        if match:
            result['series_name'] = match.group(1).strip()
            result['book_number'] = match.group(2)
            result['full_series'] = match.group(0)
            return result
        
        # Pattern 3: "Series Name: Title" (series first)
        match = re.search(r'^([^:]+):\s*(.+)', title)
        if match:
            # Check if first part looks like a series (contains "series", "saga", etc)
            first_part = match.group(1).strip()
            if any(word in first_part.lower() for word in ['series', 'saga', 'chronicles', 'trilogy']):
                result['series_name'] = first_part
                result['full_series'] = first_part + ':'
                return result
        
        # Pattern 4: "Title, Book 3" (series name might be in title itself)
        match = re.search(r',\s*(?:Book|#)\s*(\d+)', title, re.IGNORECASE)
        if match:
            result['book_number'] = match.group(1)
            result['full_series'] = match.group(0).strip(', ')
            return result
        
        # Pattern 5: "Title Name 8" or "Title Name Book 8" (book number at end)
        # Handles: "Mark of the Fool 8", "Foundation Book 7", etc.
        match = re.search(r'^(.+?)\s+(?:Book\s+)?(\d+)$', title, re.IGNORECASE)
        if match:
            # Extract potential series name (everything before the number)
            potential_series = match.group(1).strip()
            book_num = match.group(2)
            
            # Only treat as series if title is long enough (avoid "Book 8" alone)
            if len(potential_series.split()) >= 2:  # At least 2 words
                result['series_name'] = potential_series
                result['book_number'] = book_num
                result['full_series'] = f"{potential_series} {book_num}"
                return result
        
        return result
    
    def _assess_format_quality(self, format_str: str) -> float:
        """Assess format quality score."""
        return float(self.format_scores.get(format_str, self.format_scores['unknown']))
    
    def _assess_bitrate_quality(self, bitrate: int) -> float:
        """Assess bitrate quality score."""
        if bitrate <= 0:
            return 0.0
        
        if bitrate < self.min_bitrate:
            return 1.0
        
        if bitrate >= self.max_useful_bitrate:
            return 10.0
        
        if bitrate >= self.preferred_bitrate:
            ratio = (bitrate - self.preferred_bitrate) / (self.max_useful_bitrate - self.preferred_bitrate)
            return 8.0 + (2.0 * ratio)
        
        ratio = (bitrate - self.min_bitrate) / (self.preferred_bitrate - self.min_bitrate)
        return 3.0 + (5.0 * ratio)
    
    def _assess_metadata_quality(self, result: Dict[str, Any]) -> float:
        """Assess metadata completeness quality score."""
        score = 0.0
        
        # Check required fields
        if result.get('title'):
            score += 4.0
        if result.get('author'):
            score += 4.0
        if result.get('size'):
            score += 2.0
        
        return min(score, 10.0)
    
    def _assess_availability_quality(self, seeders: int) -> float:
        """Assess availability quality based on seeders."""
        if seeders <= 0:
            return 0.0
        if seeders >= 50:
            return 10.0
        if seeders >= 10:
            return 8.0
        if seeders >= 5:
            return 6.0
        if seeders >= 2:
            return 4.0
        return 2.0
    
    def _calculate_confidence(self, total_score: float, format_score: float, 
                             bitrate_score: float, metadata_score: float,
                             availability_score: float, result: Dict[str, Any],
                             relevance_meta: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculate confidence percentage (0-100) based on quality scores and data completeness.
        
        Confidence factors:
        - Base score from total_score (0-10 -> 0-100)
        - Penalties for missing or low-quality data
        - Bonus for excellent scores
        
        Returns:
            Confidence percentage (0-100)
        """
        # Start with base confidence from total score (0-10 scale)
        # Convert to 0-100 scale: score * 10
        base_confidence = min(total_score * 10, 100.0)
        
        # Apply penalties for missing or poor data
        penalties = 0.0
        
        # Format penalty - unknown or poor formats reduce confidence
        if format_score < 5.0:
            penalties += 15.0
        elif format_score < 7.0:
            penalties += 5.0
        
        # Bitrate penalty - missing or very low bitrate
        if bitrate_score == 0.0:
            penalties += 10.0  # No bitrate info
        elif bitrate_score < 3.0:
            penalties += 10.0  # Very low bitrate
        elif bitrate_score < 6.0:
            penalties += 5.0   # Low bitrate
        
        # Metadata penalty - incomplete information
        if metadata_score < 8.0:
            penalties += 5.0   # Missing some metadata
        if metadata_score < 5.0:
            penalties += 10.0  # Missing critical metadata
        
        # Availability penalty - low seeders
        if availability_score == 0.0:
            penalties += 20.0  # No seeders (dead torrent)
        elif availability_score < 4.0:
            penalties += 10.0  # Very few seeders
        elif availability_score < 6.0:
            penalties += 5.0   # Low seeders
        
        # Apply bonuses for excellent scores
        bonuses = 0.0
        
        # Excellent format (m4b)
        if format_score >= 9.0:
            bonuses += 5.0
        
        # High bitrate
        if bitrate_score >= 9.0:
            bonuses += 3.0
        
        # Complete metadata
        if metadata_score >= 9.0:
            bonuses += 2.0
        
        # High availability
        if availability_score >= 9.0:
            bonuses += 5.0
        
        # Book/series alignment penalties/bonuses
        meta = relevance_meta or {}
        number_status = meta.get('book_number_status')
        if number_status == 'mismatch':
            penalties += 45.0
        elif number_status == 'result_missing':
            penalties += 20.0
        elif number_status == 'match':
            bonuses += 5.0

        title_meta = (meta.get('title') or {})
        title_status = title_meta.get('status')
        if title_status == 'no_match':
            penalties += 35.0
        elif title_status == 'match' and (title_meta.get('score') or 0) >= 2.0:
            bonuses += 5.0

        series_meta = (meta.get('series') or {})
        series_status = series_meta.get('status')
        if series_status == 'no_match':
            penalties += 15.0
        elif series_status == 'match' and (series_meta.get('score') or 0) >= 1.2:
            bonuses += 5.0

        # Calculate final confidence
        confidence = base_confidence - penalties + bonuses
        
        # Clamp to 0-100 range
        confidence = max(0.0, min(100.0, confidence))
        
        return confidence
    
    def meets_user_preferences(self, result: Dict[str, Any]) -> bool:
        """Check if result meets basic user quality preferences."""
        try:
            # Check minimum format requirements
            format_str = result.get('format', 'unknown').lower()
            if format_str not in ['m4b', 'm4a', 'mp3', 'flac']:
                return False
            
            # Check minimum bitrate
            bitrate = result.get('bitrate', 0)
            if bitrate > 0 and bitrate < self.min_bitrate:
                return False
            
            # Check for required metadata
            if not result.get('title') or not result.get('author'):
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking user preferences: {e}")
            return False
    
    def rank_results_by_quality(self, results: List[Dict[str, Any]], 
                               search_title: str = '', 
                               search_author: str = '') -> List[Dict[str, Any]]:
        """
        Rank results by quality score including relevance to search query.
        
        Args:
            results: List of search results to rank
            search_title: User's search title query
            search_author: User's search author query
            
        Returns:
            Sorted list with quality_assessment added to each result
        """
        try:
            self.logger.info(f"🎯 rank_results_by_quality called with {len(results)} results, search_title='{search_title}', search_author='{search_author}'")
            scored_results = []
            
            for i, result in enumerate(results):
                self.logger.info(f"  📊 Assessing result {i+1}/{len(results)}: '{result.get('title', 'NO TITLE')}'")
                query_title = result.get('_search_query_used') or search_title
                quality_score = self.assess_result_quality(result, query_title, search_author)
                result_copy = result.copy()
                result_copy['quality_assessment'] = quality_score
                scored_results.append(result_copy)
                self.logger.info(f"  ✓ Result scored: total={quality_score.total_score:.2f}, confidence={quality_score.confidence:.1f}%")
            
            scored_results.sort(key=lambda x: x['quality_assessment'].total_score, reverse=True)
            self.logger.info(f"🏁 Ranking complete, returning {len(scored_results)} sorted results")
            return scored_results
            
        except Exception as e:
            import traceback
            self.logger.error(f"❌ Failed to rank results by quality: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return results