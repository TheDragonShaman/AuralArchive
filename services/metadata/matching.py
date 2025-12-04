import logging
from typing import List, Dict, Optional

class MetadataMatching:
    """Handles text matching and similarity algorithms for metadata updates"""
    
    def __init__(self):
        self.logger = logging.getLogger("MetadataUpdateService.Matching")
    
    def find_best_match(self, search_results: List[Dict], target_title: str, target_author: str) -> Optional[Dict]:
        """Find the best matching book from search results"""
        try:
            if not search_results:
                return None
            
            target_title_lower = target_title.lower().strip()
            target_author_lower = target_author.lower().strip() if target_author else ""
            
            best_match = None
            best_score = 0
            
            self.logger.debug(f"Matching against target: '{target_title}' by '{target_author}'")
            
            for result in search_results:
                score = self._calculate_match_score(result, target_title_lower, target_author_lower)
                
                self.logger.debug(f"Match score {score}: '{result.get('Title', 'Unknown')}' by '{result.get('Author', 'Unknown')}'")
                
                if score > best_score:
                    best_score = score
                    best_match = result
            
            # Only return matches with reasonable confidence
            if best_score >= 10:
                self.logger.info(f"Best match found with score {best_score}: '{best_match.get('Title')}'")
                return best_match
            
            # If no good match, return first result as fallback
            if search_results:
                self.logger.info(f"No confident match (best score: {best_score}), using first result as fallback")
                return search_results[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding best match: {e}")
            return search_results[0] if search_results else None
    
    def _calculate_match_score(self, result: Dict, target_title: str, target_author: str) -> float:
        """Calculate match score for a search result"""
        try:
            result_title = result.get('Title', '').lower().strip()
            result_author = result.get('Author', '').lower().strip()
            
            score = 0
            
            # Title matching (most important - up to 20 points)
            title_score = self._calculate_title_score(target_title, result_title)
            score += title_score
            
            # Author matching (important - up to 10 points)
            if target_author and result_author:
                author_score = self._calculate_author_score(target_author, result_author)
                score += author_score
            
            # Bonus for exact matches
            if target_title == result_title:
                score += 15
                self.logger.debug(f"Exact title match bonus: +15")
            
            if target_author and target_author == result_author:
                score += 10
                self.logger.debug(f"Exact author match bonus: +10")
            
            return score
            
        except Exception as e:
            self.logger.debug(f"Error calculating match score: {e}")
            return 0
    
    def _calculate_title_score(self, target: str, candidate: str) -> float:
        """Calculate title matching score"""
        if not target or not candidate:
            return 0
        
        score = 0
        
        # Exact match
        if target == candidate:
            return 20
        
        # Substring match
        if target in candidate or candidate in target:
            score += 15
            self.logger.debug(f"Title substring match: +15")
        
        # Word-based similarity
        word_similarity = self._calculate_word_similarity(target, candidate)
        score += word_similarity * 5  # Up to 5 points for word similarity
        
        # Character-based similarity for fuzzy matching
        char_similarity = self._calculate_character_similarity(target, candidate)
        if char_similarity > 0.8:
            score += 5
            self.logger.debug(f"High character similarity: +5")
        
        return score
    
    def _calculate_author_score(self, target: str, candidate: str) -> float:
        """Calculate author matching score"""
        if not target or not candidate:
            return 0
        
        score = 0
        
        # Exact match
        if target == candidate:
            return 10
        
        # Substring match
        if target in candidate or candidate in target:
            score += 8
            self.logger.debug(f"Author substring match: +8")
        
        # Word-based similarity (authors often have different name orders)
        word_similarity = self._calculate_word_similarity(target, candidate)
        score += word_similarity * 3  # Up to 3 points for word similarity
        
        return score
    
    def _calculate_word_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity based on common words"""
        try:
            # Split into words and normalize
            words1 = set(self._normalize_text(str1).split())
            words2 = set(self._normalize_text(str2).split())
            
            if not words1 or not words2:
                return 0.0
            
            # Calculate Jaccard similarity (intersection over union)
            intersection = len(words1 & words2)
            union = len(words1 | words2)
            
            similarity = intersection / union if union > 0 else 0.0
            
            if similarity > 0.5:
                self.logger.debug(f"Word similarity {similarity:.2f}: '{str1}' vs '{str2}'")
            
            return similarity
            
        except Exception as e:
            self.logger.debug(f"Error calculating word similarity: {e}")
            return 0.0
    
    def _calculate_character_similarity(self, str1: str, str2: str) -> float:
        """Calculate character-level similarity using Levenshtein-like approach"""
        try:
            if not str1 or not str2:
                return 0.0
            
            # Simple character-based similarity
            max_len = max(len(str1), len(str2))
            if max_len == 0:
                return 1.0
            
            # Count matching characters in similar positions
            matches = 0
            min_len = min(len(str1), len(str2))
            
            for i in range(min_len):
                if str1[i] == str2[i]:
                    matches += 1
            
            # Add bonus for matching characters in different positions
            remaining1 = str1[min_len:]
            remaining2 = str2[min_len:]
            
            for char in remaining1:
                if char in remaining2:
                    matches += 0.5
            
            similarity = matches / max_len
            return similarity
            
        except Exception as e:
            self.logger.debug(f"Error calculating character similarity: {e}")
            return 0.0
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        
        # Remove common words that don't help with matching
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 
            'for', 'of', 'with', 'by', 'book', 'volume', 'vol', 'part'
        }
        
        # Clean and split
        normalized = text.lower()
        normalized = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in normalized)
        words = [word for word in normalized.split() if word not in common_words and len(word) > 1]
        
        return ' '.join(words)
    
    def is_similar_strings(self, str1: str, str2: str, threshold: float = 0.5) -> bool:
        """Check if two strings are similar based on word overlap"""
        try:
            similarity = self._calculate_word_similarity(str1, str2)
            return similarity > threshold
        except:
            return False
    
    def find_exact_asin_match(self, search_results: List[Dict], target_asin: str) -> Optional[Dict]:
        """Find exact ASIN match in search results"""
        try:
            if not target_asin or target_asin == 'N/A':
                return None
            
            for result in search_results:
                result_asin = result.get('ASIN', '')
                if result_asin == target_asin:
                    self.logger.info(f"Found exact ASIN match: {target_asin}")
                    return result
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error finding exact ASIN match: {e}")
            return None

# Global instance for easy access
matcher = MetadataMatching()
