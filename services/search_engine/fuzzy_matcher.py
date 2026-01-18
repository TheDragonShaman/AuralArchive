"""
Module Name: fuzzy_matcher.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Enhanced fuzzy string matching combining token-based and character-level
    strategies for audiobook title/author matching. Provides aggressive
    normalization and multi-strategy scoring for search relevance.

Location:
    /services/search_engine/fuzzy_matcher.py

"""

from typing import Dict, List, Any, Optional, Tuple, Set
import re
from dataclasses import dataclass

from utils.logger import get_module_logger

_LOGGER = get_module_logger("Service.SearchEngine.FuzzyMatcher")


@dataclass
class MatchResult:
    """Result of a fuzzy match operation."""
    score: float
    matched: bool
    exact: bool
    word_boundary: bool
    algorithm_used: str
    normalized_match: bool = False  # NEW: Was this a normalized exact match?
    token_overlap: float = 0.0      # NEW: Token set overlap ratio
    

class FuzzyMatcher:
    """
    Enhanced fuzzy string matching combining multiple strategies.
    
    Features:
    - Aggressive normalization (remove punctuation, spaces, articles)
    - Token set matching (LazyLibrarian style)
    - Character-level Bitap algorithm (Readarr style)
    - Multi-strategy scoring with fallbacks
    - Configurable match thresholds
    """
    
    def __init__(self, *, logger=None):
        """Initialize the fuzzy matcher."""
        self.logger = logger or _LOGGER
        
        # Bitap algorithm configuration
        self.max_distance = 2  # Maximum edit distance
        self.match_threshold = 0.8  # Minimum score for a match
        self.word_boundary_bonus = 0.2  # Bonus for word boundary matches
        
        # Compile regex patterns for efficiency
        self._compile_patterns()
        
        self.initialized = False
        self._initialize()
    
    def _compile_patterns(self):
        """Compile regex patterns for title cleaning."""
        try:
            # Pattern for cleaning titles (remove special chars, extra spaces)
            self.clean_pattern = re.compile(r'[^\w\s]')
            self.space_pattern = re.compile(r'\s+')
            
            # Pattern for word boundaries
            self.word_boundary_pattern = re.compile(r'\b')
            
            # Pattern for removing articles and common words
            self.article_pattern = re.compile(r'\b(the|a|an)\b', re.IGNORECASE)
            
            # NEW: Pattern for removing ALL non-alphanumeric (aggressive normalization)
            self.alphanumeric_only = re.compile(r'[^\w]')
            
            # NEW: Pattern for removing content in brackets/parens
            self.brackets_pattern = re.compile(r'[\[\(].*?[\]\)]')
            
            # NEW: Pattern for removing content after dash
            self.dash_pattern = re.compile(r'\s*[-–—]\s*.*$')
            
        except Exception as e:
            self.logger.error(
                "Failed to compile regex patterns",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
    
    def _initialize(self):
        """Initialize the fuzzy matcher."""
        try:
            self.logger.debug("Initializing FuzzyMatcher", extra={"max_distance": self.max_distance})
            
            # Test regex patterns
            test_result = self.clean_pattern.sub('', 'test-string')
            if test_result != 'teststring':
                raise Exception("Regex pattern test failed")
            
            self.initialized = True
            self.logger.debug("FuzzyMatcher initialized successfully")
            
        except Exception as e:
            self.logger.error(
                "Failed to initialize FuzzyMatcher",
                extra={"error": str(e)},
                exc_info=True,
            )
            self.initialized = False
    
    def is_initialized(self) -> bool:
        """Check if the fuzzy matcher is properly initialized."""
        return self.initialized
    
    def normalize_author(self, author: str) -> str:
        """
        Aggressively normalize author name for matching.
        Based on LazyLibrarian's approach - remove ALL punctuation and spaces.
        
        Examples:
            "SouppatchHero" -> "sourpatchhero"
            "Sourpatch Hero" -> "sourpatchhero"
            "O'Brien, Patrick" -> "obrienpatrick"
            "Tommy Kerper" -> "tommykerper"
        
        Args:
            author: Author name to normalize
            
        Returns:
            Normalized author string (lowercase alphanumeric only)
        """
        if not author:
            return ""
        
        # Remove ALL non-alphanumeric characters (spaces, punctuation, etc)
        normalized = self.alphanumeric_only.sub('', author.lower())
        
        return normalized
    
    def normalize_title(self, title: str) -> str:
        """
        Normalize title for matching.
        Based on Readarr's approach - remove brackets, articles, extra spaces.
        Less aggressive than author normalization (keeps spaces for tokenization).
        
        Examples:
            "I'm Not the Hero: An Isekai LitRPG" -> "im not hero isekai litrpg"
            "Secrets and Strife [Audiobook]" -> "secrets and strife"
            "The Hero of Ages" -> "hero of ages"
        
        Args:
            title: Title to normalize
            
        Returns:
            Normalized title (lowercase, cleaned, spaces preserved)
        """
        if not title:
            return ""
        
        cleaned = title.lower()
        
        # Remove content in brackets/parens
        cleaned = self.brackets_pattern.sub('', cleaned)
        
        # Remove content after dash (often metadata)
        cleaned = self.dash_pattern.sub('', cleaned)
        
        # Remove leading articles (the, a, an)
        cleaned = self.article_pattern.sub('', cleaned)
        
        # Replace punctuation with spaces (preserve word boundaries)
        cleaned = self.clean_pattern.sub(' ', cleaned)
        
        # Normalize whitespace
        cleaned = self.space_pattern.sub(' ', cleaned)
        
        # Strip
        cleaned = cleaned.strip()
        
        return cleaned
    
    def tokenize(self, text: str) -> Set[str]:
        """
        Tokenize text into word set (for token set matching).
        
        Args:
            text: Text to tokenize
            
        Returns:
            Set of lowercase words
        """
        if not text:
            return set()
        
        # Split on whitespace and filter empty strings
        tokens = set(text.lower().split())
        tokens = {t for t in tokens if t}  # Remove empty strings
        
        return tokens
    
    def token_set_overlap(self, tokens1: Set[str], tokens2: Set[str]) -> float:
        """
        Calculate token set overlap ratio (LazyLibrarian style).
        
        Args:
            tokens1: First set of tokens
            tokens2: Second set of tokens
            
        Returns:
            Overlap ratio (0.0 to 1.0)
        """
        if not tokens1 or not tokens2:
            return 0.0
        
        # Calculate Jaccard similarity (intersection / union)
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def fuzzy_match(self, text1: str, text2: str) -> MatchResult:
        """
        Perform fuzzy matching between two strings using multiple strategies.
        
        Strategy order (returns first successful match):
        1. Exact match (case-insensitive)
        2. Exact normalized match (after cleaning)
        3. Token set overlap (word-based)
        4. Bitap fuzzy match (character-level)
        
        Args:
            text1: First string to compare
            text2: Second string to compare
            
        Returns:
            MatchResult with score, match status, and metadata
        """
        try:
            if not text1 or not text2:
                return MatchResult(0.0, False, False, False, "empty_input")
            
            # Clean both texts for comparison
            clean1 = text1.lower().strip()
            clean2 = text2.lower().strip()
            
            # Strategy 1: Exact match (case-insensitive)
            if clean1 == clean2:
                return MatchResult(1.0, True, True, True, "exact")
            
            # Strategy 2: Exact normalized match (aggressive cleaning)
            # This catches variations like "SouppatchHero" vs "Sourpatch Hero"
            norm1 = self.normalize_title(text1)
            norm2 = self.normalize_title(text2)
            
            if norm1 == norm2:
                return MatchResult(
                    score=1.0,
                    matched=True,
                    exact=False,
                    word_boundary=True,
                    algorithm_used="normalized_exact",
                    normalized_match=True
                )
            
            # Strategy 3: Token set overlap (word-based matching)
            # This handles word order variations and partial matches
            tokens1 = self.tokenize(norm1)
            tokens2 = self.tokenize(norm2)
            
            if tokens1 and tokens2:
                overlap = self.token_set_overlap(tokens1, tokens2)
                
                # If high overlap, consider it a match
                if overlap >= 0.7:  # 70% token overlap
                    return MatchResult(
                        score=overlap,
                        matched=True,
                        exact=False,
                        word_boundary=True,
                        algorithm_used="token_set",
                        token_overlap=overlap
                    )
            
            # Strategy 4: Bitap algorithm (character-level fuzzy match)
            # Fallback for handling typos and small variations
            bitap_score = self._bitap_search(norm1, norm2)
            
            # Check for word boundary matches
            word_boundary_match = self._check_word_boundary_match(norm1, norm2)
            
            # Calculate final score
            final_score = bitap_score
            if word_boundary_match:
                final_score = min(1.0, final_score + self.word_boundary_bonus)
            
            # Determine if it's a match (lower threshold than before)
            is_match = final_score >= 0.6  # Lowered from 0.8
            
            return MatchResult(
                score=final_score,
                matched=is_match,
                exact=False,
                word_boundary=word_boundary_match,
                algorithm_used="bitap",
                token_overlap=self.token_set_overlap(tokens1, tokens2) if tokens1 and tokens2 else 0.0
            )
            
        except Exception as e:
            self.logger.error(
                "Fuzzy match failed",
                extra={"text1": text1, "text2": text2, "error": str(e)},
                exc_info=True,
            )
            return MatchResult(0.0, False, False, False, "error")
    
    def _bitap_search(self, pattern: str, text: str) -> float:
        """
        Implement Bitap algorithm for fuzzy string matching.
        Based on Readarr's implementation with audiobook-specific optimizations.
        
        Args:
            pattern: Pattern to search for
            text: Text to search in
            
        Returns:
            Match score between 0.0 and 1.0
        """
        try:
            if not pattern or not text:
                return 0.0
            
            # Handle case where pattern is longer than text
            if len(pattern) > len(text):
                pattern, text = text, pattern
            
            # Simple cases
            if pattern == text:
                return 1.0
            
            if pattern in text:
                # Substring match - score based on length ratio
                return len(pattern) / len(text)
            
            # Bitap algorithm implementation
            pattern_length = len(pattern)
            text_length = len(text)
            
            # Calculate edit distance using dynamic programming
            # (Simplified version of Bitap for readability)
            best_score = 0.0
            
            for i in range(text_length - pattern_length + 1):
                substring = text[i:i + pattern_length]
                distance = self._edit_distance(pattern, substring)
                
                # Convert distance to score (lower distance = higher score)
                max_distance = max(len(pattern), len(substring))
                score = 1.0 - (distance / max_distance)
                best_score = max(best_score, score)
            
            return best_score
            
        except Exception as e:
            self.logger.error(
                "Bitap search error",
                extra={"pattern": pattern, "text": text, "error": str(e)},
                exc_info=True,
            )
            return 0.0
    
    def _edit_distance(self, s1: str, s2: str) -> int:
        """Calculate edit distance between two strings."""
        if len(s1) < len(s2):
            return self._edit_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _check_word_boundary_match(self, text1: str, text2: str) -> bool:
        """Check if strings match at word boundaries."""
        try:
            # Split into words and check for common words
            words1 = set(text1.split())
            words2 = set(text2.split())
            
            # Calculate word overlap
            common_words = words1.intersection(words2)
            total_words = words1.union(words2)
            
            if not total_words:
                return False
            
            overlap_ratio = len(common_words) / len(total_words)
            return overlap_ratio >= 0.5  # At least 50% word overlap
            
        except Exception as e:
            self.logger.error(
                "Word boundary check error",
                extra={"text1": text1, "text2": text2, "error": str(e)},
                exc_info=True,
            )
            return False
    
    def clean_title_for_matching(self, title: str) -> str:
        """
        Clean title for better matching accuracy.
        
        Args:
            title: Title to clean
            
        Returns:
            Cleaned title suitable for matching
        """
        try:
            if not title:
                return ""
            
            # Convert to lowercase
            cleaned = title.lower()
            
            # Remove articles
            cleaned = self.article_pattern.sub('', cleaned)
            
            # Remove special characters
            cleaned = self.clean_pattern.sub(' ', cleaned)
            
            # Normalize spaces
            cleaned = self.space_pattern.sub(' ', cleaned)
            
            # Strip whitespace
            cleaned = cleaned.strip()
            
            return cleaned
            
        except Exception as e:
            self.logger.error(
                "Title cleaning failed",
                extra={"title": title, "error": str(e)},
                exc_info=True,
            )
            return title.lower() if title else ""