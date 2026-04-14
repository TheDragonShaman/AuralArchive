# Search and Metadata

Learn about searching for audiobooks and managing metadata in AuralArchive.

## Metadata Sources

AuralArchive fetches metadata from Audible to ensure accurate information.

### Primary Source

**Audible API**
- Audiobook-specific metadata from Audible catalog
- Narrator information
- Accurate durations and runtime
- Series information and book numbers
- High-quality cover art
- Customer ratings and review counts
- Release dates and publisher information
- Region-specific information
- Always accurate for Audible purchases

The system uses multiple search strategies to find the best metadata match:
1. **ASIN Search** - Direct lookup if ASIN is available
2. **Title + Author Search** - Combined search for best match
3. **Title-Only Search** - Fallback if author information unavailable

Metadata is automatically selected based on confidence matching against your book's existing information.

**Note**: Additional metadata sources (such as Audnexus, OpenLibrary, and others) will be integrated over time to provide more comprehensive metadata coverage and improve matching for non-Audible titles.

## Automatic Metadata Fetching

### On Import

When adding audiobooks, metadata is automatically fetched:

1. File is scanned for embedded metadata (ID3, M4A tags)
2. ASIN or ISBN is extracted (if present)
3. Audible API is queried using search strategies
4. Best match is selected based on confidence
5. Metadata is applied to library entry

### On Sync

When syncing from Audible or AudioBookShelf:
- Metadata is automatically included
- No manual lookup needed
- Can be refreshed later if needed

### Manual Refresh

Update metadata for existing audiobooks:

**Single Book:**
1. Go to **Library** page
2. Click audiobook card to open details modal
3. Click **Update Metadata** button
4. System automatically fetches latest metadata from configured sources
5. Page reloads with updated information

**Bulk Refresh:**
1. Click **Select Books** button in toolbar
2. Select multiple audiobooks using checkboxes
3. Click **Update Metadata** in the selection toolbar
4. Progress modal shows real-time update status
5. Library refreshes when complete

The system automatically selects the best metadata source and updates all fields.

## Cover Art Management

### Automatic Cover Art

- Downloaded automatically with metadata from Audible API
- High-quality images cached locally for performance
- Updated automatically when metadata is refreshed
- Fallback to placeholder if no cover available

### Cover Art Cache

Image caching is managed through backend API endpoints:

- **Cache Statistics**: View total images cached, cache size, and hit rate via API
- **Clear Cache**: Remove all cached images (they will be re-downloaded as needed)
- **Optimize**: Backend automatically manages cache cleanup

Cache management tools are available through the backend API but not exposed in a dedicated Settings UI tab. Images are automatically cached when fetched and cleared when needed.

## Searching for Audiobooks

### Search Page

The **Search** page lets you discover audiobooks from the Audible catalog:

1. Navigate to **Search** from the main menu
2. Enter search terms (title, author, or series)
3. Click **Search** button
4. Browse results in Grid, List, or Table view
5. Filter results:
   - **All Results** - Everything
   - **In Library** - Books you already have
   - **Not in Library** - New discoveries
   - **Wanted** - Books on your wishlist
   - **Downloadable** - Available for download
6. Sort by Relevance, Title, Author, Rating, or Release Date

### Adding Books from Search

From search results, you can:
- View detailed book information
- Add books to your library
- Mark books as "Wanted"
- See which books you already own
- Download owned Audible titles

### Discover Page

Explore curated audiobook recommendations and trending titles on the **Discover** page.

## Series Management

### Automatic Series Detection

AuralArchive automatically detects series from metadata:
- Series name extracted from Audible and metadata sources
- Book position/number identified automatically
- Series information displayed in book details

### Series Page

View and manage your series collection:

1. Go to **Series** page from navigation
2. View all tracked series with:
   - Series title
   - Total books in series
   - Number owned vs missing
   - Completion percentage
3. Switch between Table View and Compact View
4. Sort by title, book count, or completion percentage
5. Search for specific series
6. Click any series to view all books in that series

**Note**: Series information comes from metadata sources and is automatically managed. Manual editing of series assignments is not currently available through the UI.

## Metadata Fields

### Standard Fields

| Field | Description |
|-------|-------------|
| **Title** | Main title of audiobook |
| **Subtitle** | Secondary title or tagline |
| **Author(s)** | Book author(s), comma-separated |
| **Narrator(s)** | Voice actor(s), comma-separated |
| **Publisher** | Publishing company |
| **Release Date** | Publication date |
| **Language** | Primary language (ISO code) |
| **Duration** | Length in hours:minutes:seconds |

### Identifiers

| Field | Description |
|-------|-------------|
| **ASIN** | Amazon Standard Identification Number |
| **ISBN** | International Standard Book Number |
| **ISBN-13** | 13-digit ISBN |
| **Audible ID** | Internal Audible identifier |

### Extended Fields

| Field | Description |
|-------|-------------|
| **Series** | Series name |
| **Series Position** | Book number in series |
| **Description** | Long-form summary |
| **Genres** | Categories/genres, comma-separated |
| **Tags** | Custom user tags |
| **Rating** | User or Audible rating (0-5 stars) |

## Troubleshooting

### Metadata Not Found

**Problem:** No metadata found for audiobook

**Solutions:**
1. Use **Update Metadata** button to retry automatic fetch
2. Check if ASIN is correct in the book details
3. Verify internet connection
4. Check logs for specific errors
5. If book is very new or obscure, metadata may not be available yet

### Wrong Metadata

**Problem:** Incorrect information fetched

**Solutions:**
1. Click **Update Metadata** to re-fetch from sources
2. If book has ASIN, verify it's correct
3. Check logs to see which metadata source was used
4. Some books may have limited metadata available

### Cover Art Not Loading

**Problem:** Cover images don't display

**Solutions:**
1. Refresh metadata to re-download cover art
2. Check browser console for image loading errors
3. Verify internet connection
4. Clear browser cache and reload page
5. Check that image cache service is running (backend)

### Series Order Wrong

**Problem:** Books in wrong order in series

**Solutions:**
1. Update metadata to refresh series information
2. Check Audible catalog for correct order
3. Series order comes from metadata sources - no manual override available
4. Report incorrect series data to Audible if found

### Duplicate Authors/Narrators

**Problem:** Same person listed multiple times with slight variations

**Solutions:**
1. Update metadata to get standardized names
2. Different sources may use different name formats
3. Metadata service attempts to normalize common variations automatically

## Best Practices

### Metadata Accuracy
- Update metadata after importing audiobooks to ensure latest information
- Use the Search page to find correct ASIN for books
- Bulk update metadata periodically to keep library current

### Cover Art
- Cover art is automatically managed by the system
- High-quality images are fetched from Audible API
- Images are cached locally for better performance

### Series Organization
- Series information is automatically detected from metadata
- Use the Series page to track completion and find missing books
- Series order is maintained by metadata sources

### Maintenance
- Periodically use bulk metadata update for older entries
- Use the Search page to discover new audiobooks
- Check Series page to identify gaps in your collections

## Next Steps

If you encounter issues, check the troubleshooting guide:
1. **[Troubleshooting](Troubleshooting)** - Common problems and solutions
