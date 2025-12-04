# Indexer Parser Enhancement

## Summary

Enhanced the Jackett indexer parser to extract **format**, **bitrate**, and **author** information from torrent titles, enabling accurate confidence scores.

## Problem

Previously, search results had:
- ❌ Format: `UNKNOWN`
- ❌ Bitrate: `0`
- ❌ Author: `Unknown Author`
- ❌ Confidence: `0%` (Poor)

This happened because the raw torrent titles like `"Crash Test - Amy James [M4B] [128 Kbps]"` weren't being parsed.

## Solution

Added three extraction methods to `/services/indexers/jackett_indexer.py`:

### 1. Format Extraction (`_extract_format_from_title`)

Extracts audio format from title patterns:

**Supported Formats:**
- `[M4B]`, `[m4b]`, `(M4B)`, `M4B` → m4b (best for audiobooks)
- `[M4A]`, `[m4a]`, `(M4A)`, `M4A` → m4a
- `[MP3]`, `[mp3]`, `(MP3)`, `MP3` → mp3
- `[FLAC]`, `[flac]` → flac
- `[AAC]`, `[aac]` → aac
- `[OGG]`, `[ogg]` → ogg

**Examples:**
```
"Book Title [M4B] [128 Kbps]" → format: m4b
"Another Book (MP3) (64kbps)" → format: mp3
"High Quality FLAC Audio"     → format: flac
```

### 2. Bitrate Extraction (`_extract_format_from_title`)

Extracts bitrate from various patterns:

**Supported Patterns:**
- `[128 Kbps]`, `[128kbps]`, `128 KBPS` → 128
- `(64 kbps)`, `(64kbps)` → 64
- `320 KB/s`, `[320 KB/s]` → 320

**Examples:**
```
"Book [M4B] [128 Kbps]"   → bitrate: 128
"Audio (64kbps)"          → bitrate: 64
"High Quality 320 kbps"   → bitrate: 320
```

### 3. Author Extraction (`_extract_author_from_title`)

Extracts author from common title patterns:

**Pattern 1: Dash Separator**
```
"Title - Author [Format]" → Author
Example: "Crash Test - Amy James [M4B]" → "Amy James"
```

**Pattern 2: "by" Keyword**
```
"Title by Author [Format]" → Author
Example: "The Book by John Smith [MP3]" → "John Smith"
```

## Results

### Before Enhancement
```json
{
  "title": "Crash Test - Amy James [M4B] [128 Kbps]",
  "format": "UNKNOWN",
  "bitrate": 0,
  "author": "Unknown Author",
  "quality_assessment": {
    "total_score": 2.5,
    "confidence": 0,
    "format_score": 1.0,
    "bitrate_score": 0.0
  }
}
```

### After Enhancement
```json
{
  "title": "Crash Test - Amy James [M4B] [128 Kbps]",
  "format": "m4b",
  "bitrate": 128,
  "author": "Amy James",
  "quality_assessment": {
    "total_score": 8.1,
    "confidence": 78,
    "format_score": 10.0,
    "bitrate_score": 8.0
  }
}
```

## Confidence Score Impact

The extraction improvements dramatically increase confidence scores:

| Format | Bitrate | Seeders | Old Confidence | New Confidence | Rating |
|--------|---------|---------|----------------|----------------|--------|
| UNKNOWN | 0 | 1 | 0% | → | **Not possible** |
| M4B | 128 | 1 | 0% | → | **78%** (Good) |
| M4B | 128 | 10 | 0% | → | **88%** (Good) |
| M4B | 128 | 50 | 0% | → | **100%** (Excellent) |
| MP3 | 64 | 5 | 0% | → | **53%** (Fair) |
| MP3 | 320 | 1 | 0% | → | **64%** (Fair) |

## Test Results

### M4B Format (Best)
```
Title: Crash Test - Amy James [M4B] [128 Kbps]
Format: M4B | Bitrate: 128 kbps | Seeders: 1
Quality: 8.1/10 | Confidence: 78% (Good)
Format Score: 10.0 (M4B = 10/10, best for audiobooks!)
Author: Amy James ✅
```

### MP3 Format (Acceptable)
```
Title: Life in the UK Test 2024 - GreatBrit Education [MP3] [320 Kbps]
Format: MP3 | Bitrate: 320 kbps | Seeders: 1
Quality: 7.4/10 | Confidence: 64% (Fair)
Format Score: 6.0 (MP3 = 6/10)
Author: GreatBrit Education ✅
```

## Implementation Details

### File Modified
`/services/indexers/jackett_indexer.py`

### Changes Made

1. **Added format/bitrate extraction** in `_parse_search_results()`:
```python
# Extract format and bitrate from title
format_info = self._extract_format_from_title(title)
result['format'] = format_info['format']
result['bitrate'] = format_info['bitrate']
```

2. **Added author extraction**:
```python
# Extract author from title if possible
author_info = self._extract_author_from_title(title)
if author_info:
    result['author'] = author_info
```

3. **Added `size` field** for compatibility:
```python
result['size'] = size_bytes  # Used by some components
result['size_bytes'] = size_bytes  # Used by quality assessor
```

## Benefits

✅ **Accurate Confidence Scores**: Users can now trust the 0-100% confidence rating  
✅ **Better Decision Making**: Clear indicators of download quality and reliability  
✅ **Format Awareness**: System knows M4B is best for audiobooks  
✅ **Bitrate Detection**: Can assess audio quality automatically  
✅ **Author Extraction**: Better metadata for library organization  
✅ **No Breaking Changes**: Backward compatible with existing code  

## Future Enhancements

Potential improvements:

1. **Series Detection**: Extract series name and book number
2. **Edition Detection**: Identify "Unabridged", "Special Edition", etc.
3. **Narrator Detection**: Extract narrator names from titles
4. **Language Detection**: Identify non-English audiobooks
5. **Duration Estimation**: Estimate audiobook length from file size

## Testing

To test the parser:

```bash
# Test basic search
curl -X POST http://localhost:5000/api/search/manual/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' | python3 -m json.tool

# Verify format extraction
# Check that "format" is no longer "UNKNOWN"
# Check that "bitrate" is no longer 0
# Check that "confidence" is no longer 0
```

## Version

- **Implementation Date**: October 14, 2025
- **Version**: 1.0
- **Status**: ✅ Complete and Tested
