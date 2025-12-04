# Confidence Score System

## Overview

The confidence score is a **0-100 percentage** that helps users identify the most reliable audiobook downloads. It's calculated based on multiple quality factors and displayed prominently in the Interactive Search modal.

## How It Works

### Base Calculation

The confidence score starts with the **total quality score** (0-10 scale) converted to a percentage:

```
Base Confidence = Total Quality Score × 10
```

### Quality Score Components (0-10 scale each)

The total quality score is a weighted average of:

| Component | Weight | Purpose |
|-----------|--------|---------|
| **Format Quality** | 30% | Audiobook-optimized formats score higher |
| **Bitrate Quality** | 25% | Higher bitrate = better audio quality |
| **Source Reputation** | 20% | Indexer reliability (future enhancement) |
| **Metadata Completeness** | 15% | Complete information = more reliable |
| **Availability** | 10% | More seeders = better download success |

### Format Scoring

Formats are ranked by suitability for audiobooks:

| Format | Score | Description |
|--------|-------|-------------|
| **M4B** | 10 | Best - audiobook format with chapters |
| **M4A** | 8 | Good - high quality, common format |
| **FLAC** | 7 | High quality but very large files |
| **MP3** | 6 | Acceptable - widely compatible |
| **AAC** | 5 | Lower quality |
| **OGG** | 4 | Less common, compatibility issues |
| **Unknown** | 1 | Cannot verify format |

### Bitrate Scoring

Audio quality based on bitrate:

| Bitrate | Score | Quality Level |
|---------|-------|---------------|
| ≥ 320 kbps | 10.0 | Maximum (overkill for audiobooks) |
| 128-320 kbps | 8.0-10.0 | Excellent (preferred range) |
| 96-128 kbps | 6.0-8.0 | Good (acceptable) |
| 64-96 kbps | 3.0-6.0 | Fair (minimum for audiobooks) |
| < 64 kbps | 1.0 | Poor (avoid) |
| 0 (unknown) | 0.0 | Cannot verify |

### Availability Scoring

Download reliability based on seeders:

| Seeders | Score | Reliability |
|---------|-------|-------------|
| ≥ 50 | 10.0 | Excellent - very fast download |
| 10-49 | 8.0 | Good - reliable download |
| 5-9 | 6.0 | Fair - may be slower |
| 2-4 | 4.0 | Low - slow download |
| 1 | 2.0 | Very low - may stall |
| 0 | 0.0 | Dead torrent - will fail |

### Metadata Scoring

Information completeness:

- Has title: +4 points
- Has author: +4 points
- Has size info: +2 points
- **Maximum**: 10 points

## Confidence Adjustments

### Penalties (Reduce Confidence)

| Issue | Penalty | Reason |
|-------|---------|--------|
| **No seeders** | -20% | Download will fail |
| **Unknown format** | -15% | Cannot verify compatibility |
| **Very few seeders (1-2)** | -10% | Very slow/unreliable |
| **No bitrate info** | -10% | Cannot verify quality |
| **Missing metadata** | -5 to -15% | Less reliable information |
| **Low bitrate (< 96 kbps)** | -5 to -10% | Poor audio quality |

### Bonuses (Increase Confidence)

| Quality Factor | Bonus | Reason |
|----------------|-------|--------|
| **Many seeders (≥ 50)** | +5% | Very reliable download |
| **M4B format** | +5% | Perfect for audiobooks |
| **High bitrate (≥ 256 kbps)** | +3% | Excellent quality |
| **Complete metadata** | +2% | Verified information |

## Confidence Ratings

The final score is grouped into four ratings:

### Excellent (90-100)
- **Color**: Green
- **Characteristics**:
  - M4B or M4A format
  - 128+ kbps bitrate
  - 10+ seeders
  - Complete metadata
- **Recommendation**: **Best choice** - Download immediately

### Good (75-89)
- **Color**: Blue
- **Characteristics**:
  - M4A, MP3, or FLAC format
  - 96+ kbps bitrate
  - 5+ seeders
  - Most metadata present
- **Recommendation**: **Reliable choice** - Good quality and availability

### Fair (50-74)
- **Color**: Amber
- **Characteristics**:
  - MP3 or acceptable format
  - 64+ kbps bitrate
  - 2-5 seeders
  - Some metadata missing
- **Recommendation**: **Use with caution** - May work but could be slow

### Poor (<50)
- **Color**: Red
- **Characteristics**:
  - Unknown format or very low quality
  - No bitrate information
  - 0-1 seeders
  - Missing critical metadata
- **Recommendation**: **Avoid** - Likely to fail or have quality issues

## Example Calculations

### Example 1: Perfect Download
```
Input:
- Format: M4B (score: 10)
- Bitrate: 128 kbps (score: 8)
- Seeders: 50 (score: 10)
- Metadata: Complete (score: 10)
- Source: Default (score: 7)

Calculation:
Total Score = (10×0.3 + 8×0.25 + 7×0.2 + 10×0.15 + 10×0.1) = 8.9
Base Confidence = 8.9 × 10 = 89%
Bonuses = +5% (M4B) +5% (50 seeders) +2% (complete metadata) = +12%
Final Confidence = 89 + 12 = 101% → capped at 100%

Result: 100% - Excellent
```

### Example 2: Decent MP3
```
Input:
- Format: MP3 (score: 6)
- Bitrate: 96 kbps (score: 6.2)
- Seeders: 10 (score: 8)
- Metadata: Complete (score: 10)
- Source: Default (score: 7)

Calculation:
Total Score = (6×0.3 + 6.2×0.25 + 7×0.2 + 10×0.15 + 8×0.1) = 7.05
Base Confidence = 7.05 × 10 = 70.5%
Penalties = -5% (MP3 format) -5% (low bitrate) = -10%
Bonuses = +2% (complete metadata) = +2%
Final Confidence = 70.5 - 10 + 2 = 62.5% → rounds to 63%

Result: 63% - Fair
```

### Example 3: Dead Torrent
```
Input:
- Format: M4B (score: 10)
- Bitrate: 128 kbps (score: 8)
- Seeders: 0 (score: 0)
- Metadata: Complete (score: 10)
- Source: Default (score: 7)

Calculation:
Total Score = (10×0.3 + 8×0.25 + 7×0.2 + 10×0.15 + 0×0.1) = 7.9
Base Confidence = 7.9 × 10 = 79%
Penalties = -20% (no seeders) = -20%
Bonuses = +5% (M4B) +2% (complete metadata) = +7%
Final Confidence = 79 - 20 + 7 = 66%

Result: 66% - Fair (avoid due to no seeders)
```

## UI Display

The confidence score is displayed in the **Interactive Search** modal:

### Column Layout
```
┌────────────┬─────────────────┬─────────┬──────┬────────┬─────────┐
│ Confidence │ Title & Author  │ Details │ Size │ Health │ Actions │
├────────────┼─────────────────┼─────────┼──────┼────────┼─────────┤
│    95      │ Book Title      │ M4B     │ 450  │ ↑ 25   │ Download│
│ Excellent  │ Author Name     │ Indexer │ MB   │ ↓ 10   │         │
└────────────┴─────────────────┴─────────┴──────┴────────┴─────────┘
```

### Color Coding
- **90-100**: Green text (Excellent)
- **75-89**: Blue text (Good)
- **50-74**: Amber text (Fair)
- **0-49**: Red text (Poor)

## Decision Making Guide

### When to Download

✅ **Confidence ≥ 90 (Excellent)**
- Download immediately
- Highest quality and reliability
- Best user experience

✅ **Confidence 75-89 (Good)**
- Safe to download
- Good quality and availability
- Minor compromises acceptable

⚠️ **Confidence 50-74 (Fair)**
- Consider other options first
- May be slow or lower quality
- Use if no better alternatives

❌ **Confidence < 50 (Poor)**
- Avoid if possible
- High risk of failure
- Poor quality or availability

### Priority Sorting

Results are automatically sorted by confidence score (highest first), helping users quickly identify the best downloads.

## Technical Implementation

**Location**: `/services/search_engine/quality_assessor.py`

**Key Methods**:
- `assess_result_quality()` - Main assessment entry point
- `_calculate_confidence()` - Confidence calculation with penalties/bonuses
- `_assess_format_quality()` - Format scoring
- `_assess_bitrate_quality()` - Bitrate scoring
- `_assess_availability_quality()` - Seeder scoring
- `_assess_metadata_quality()` - Metadata completeness

**Data Flow**:
1. Search results returned from indexers
2. Each result assessed by `QualityAssessor`
3. Quality scores + confidence calculated
4. Results sorted by confidence
5. Sent to frontend for display
6. User sees confidence in Interactive Search modal

## Future Enhancements

### Planned Improvements

1. **Source Reputation** (Currently 7.0 default)
   - Track indexer reliability
   - Historical success rates
   - Penalty for problematic sources

2. **Match Quality**
   - Fuzzy matching score vs search query
   - Exact title/author match bonus
   - Series detection and ordering

3. **Historical Performance**
   - Track successful downloads
   - User feedback integration
   - Learn from download outcomes

4. **User Preferences**
   - Customizable weight factors
   - Preferred formats (e.g., prefer FLAC)
   - Minimum confidence threshold

5. **Advanced Penalties**
   - Suspicious file sizes
   - Unverified uploaders
   - Known fake/incomplete releases

## Version History

**v1.0** (Current)
- Initial confidence score implementation
- Basic quality assessment (format, bitrate, availability, metadata)
- Penalty and bonus system
- UI integration with color-coded display
