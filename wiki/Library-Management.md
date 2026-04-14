# Library Management

Learn how to browse, organize, and manage your audiobook collection in AuralArchive.

## Library Overview

The Library page is your main interface for viewing and managing audiobooks.

## Browsing Your Library

### View Modes

The Library displays audiobooks in a responsive card grid:
- **Card Size Adjustment**: Use the density slider to adjust card size
- Cards show cover art, title, author, and status
- Responsive layout adapts to screen size

### Sorting Options

Sort your library using the **Sort By** dropdown:
- **Title** - Alphabetical by title
- **Author** - Alphabetical by author
- **Rating** - By audiobook rating
- **Date Added** - By date added to library

### Filtering

Filter audiobooks using the toolbar controls:

#### Search Bar
- Search by title, author, or series
- Real-time filtering as you type

#### By Status
- **All Status** - Show everything
- **Owned** - Books you own
- **Audible Library** - Synced from Audible
- **Wanted** - Books on your wishlist
- **Downloading** - Currently downloading

#### By Genre
- Filter by genre categories
- Includes Fiction, Non-Fiction, Self-Help, Science, History, and more

## Book Details

Click any audiobook card to open a detailed modal with:

### Metadata Display
- **Title** and **Author**
- **Series** name and book number (if applicable)
- **Narrator(s)**
- **Runtime** 
- **Rating** and review count
- **Release Date**
- **Publisher** and **Language**
- **Status** (Owned, Audible Library, Wanted, etc.)
- **Source** (where the book came from)
- **File Location** (if downloaded)
- **ASIN**
- **Summary/Description**

### Available Actions
From the book details modal:
- **Update Metadata** - Refresh metadata from configured sources
- **Interactive Download** - Search for and select specific downloads
- **Auto Download** - Automatically find and download best match
- **Delete** - Remove from library

### Quick Actions from Card
Hover over any audiobook card to access quick action buttons:
- **Info button** (i) - Open book details modal
- **Download button** - Interactive download search
- **Bolt button** - Auto download

## Bulk Operations

Perform actions on multiple audiobooks:

### Selecting Items

1. Click **Select Books** button in toolbar
2. Check boxes appear on each audiobook card
3. Click checkboxes to select audiobooks
4. Use **Select All** to select all visible books
5. Use **Clear Selection** to deselect all

### Bulk Actions Menu

Available bulk actions when books are selected:
- **Update Metadata** - Refresh metadata for selected books
- **Change Status** - Update status for all selected
- **Delete Selected** - Remove selected books from library

## Series and Authors

### Series Pages

AuralArchive tracks series information from metadata:
- View series details on the **Series** page
- See all books in a series
- Series information is pulled from Audible and other metadata sources

### Author Pages

View all audiobooks by an author:
1. Click any author name or navigate to **Authors** page
2. View author page with:
   - All audiobooks by that author
   - Sorting and filtering options
   - Author bio (when available from metadata)

## Importing Existing Audiobooks

Add audiobooks you already own using the dedicated Import page. See the **[Import Guide](import.md)** for detailed instructions.

### Quick Import Overview

1. Place audiobook files in `/import` directory
2. Go to **Import** page
3. The system will scan for new files
4. Review detected audiobooks and metadata
5. Import selected files to library

### Supported Formats
- M4B, M4A (chapter support)
- MP3 (ID3 tags)
- FLAC (metadata support)
- AAX (Audible format - requires activation bytes)

## Troubleshooting

### Missing Audiobooks

**Problem:** Audiobooks don't appear in library

**Solutions:**
1. Sync from Audible: Go to **Settings** → **Audible** tab, use Quick Sync or Full Sync
2. Sync from AudioBookShelf: Check AudioBookShelf integration settings
3. Check filters - click **Clear Filters** to reset all filters
4. Verify database connection and check logs

### Incorrect Metadata

**Problem:** Wrong information displayed

**Solutions:**
1. Select the audiobook
2. Click **Update Metadata** (for single book or use bulk actions)
3. System will refresh metadata from configured sources
4. Manually edit if auto-refresh doesn't fix it

### Slow Library Loading

**Problem:** Library takes long to load

**Solutions:**
1. Adjust card density using the slider
2. Use filters to narrow down results
3. Check network connection to AuralArchive server
4. Review system resources if running locally

## Best Practices

### Organization
- Keep series information accurate by refreshing metadata
- Use status filters to organize your library (Owned, Wanted, etc.)
- Utilize genre filters to browse by category

### Maintenance
- Regularly refresh metadata for new audiobooks using bulk operations
- Clean up imported files after adding to library
- Use the search bar to quickly find specific books

### Performance
- Adjust card density using the slider for your preference
- Use filters and search to narrow results instead of browsing all books
- Clear browser cache if the library loads slowly

## Next Steps

Learn about downloading and managing audiobook files:
1. **[Downloads and Queue Management](Downloads-and-Queue)**
2. **[Search and Metadata](Search-and-Metadata)**
3. **[Troubleshooting](Troubleshooting)**
