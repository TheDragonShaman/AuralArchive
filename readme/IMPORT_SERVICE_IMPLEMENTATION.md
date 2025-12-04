# Import Service Implementation - Complete

## Summary

Implemented a complete audiobook import system for AuralArchive following the Readarr/Sonarr file management pattern. The system handles moving audiobooks to the library directory with proper naming conventions and database tracking.

**Implementation Date**: October 27, 2025  
**Status**: ✅ Complete

## Components Created

### 1. File Naming Service (`services/file_naming/`)

**Purpose**: Generate AudioBookShelf-compatible file paths with user-configurable templates.

**Files Created**:
- `file_naming_service.py` - Main singleton service coordinator
- `template_parser.py` - Template validation and variable substitution
- `path_generator.py` - Complete path generation logic
- `sanitizer.py` - Linux-focused path sanitization
- `__init__.py` - Package exports

**Features**:
- User-configurable naming templates (standard, standard_asin, simple, flat, etc.)
- ASIN bracket notation support `[B0C7GX8Z9P]`
- Template variables: `{author}`, `{title}`, `{series}`, `{series_number}`, `{year}`, `{narrator}`, `{asin}`, `{publisher}`, `{runtime}`
- Linux-first path sanitization (minimal restrictions, optional Windows compatibility)
- Path parsing to extract metadata from existing paths
- Author/Series folder organization
- Template preview functionality

**Example Usage**:
```python
naming_service = get_file_naming_service()
path = naming_service.generate_file_path(
    book_data={'Title': 'Anima', 'Author': 'Blake Crouch', 'ASIN': 'B0C7GX8Z9P'},
    base_path='/mnt/audiobooks',
    template_name='standard_asin',
    file_extension='m4b'
)
# Returns: /mnt/audiobooks/Blake Crouch/Standalone/Anima [B0C7GX8Z9P].m4b
```

### 2. Import Service (`services/import_service/`)

**Purpose**: Move audiobook files to library and track them in the database.

**Files Created**:
- `import_service.py` - Main singleton service coordinator
- `file_operations.py` - Atomic file moves with verification
- `database_operations.py` - Import tracking database operations
- `validation.py` - Import validation and quality detection
- `__init__.py` - Package exports

**Features**:
- Atomic file moving (uses `os.rename` when on same filesystem)
- SHA256 checksum verification
- Disk space validation (with 10% buffer)
- File quality detection via ffprobe
- Database tracking of imports
- Batch import support
- Import verification and rollback
- Import statistics and history

**Example Usage**:
```python
import_service = get_import_service()
success, message, dest_path = import_service.import_book(
    source_file_path='/tmp/converted/book.m4b',
    book_data={'Title': 'Anima', 'Author': 'Blake Crouch', 'ASIN': 'B0C7GX8Z9P'},
    template_name='standard_asin'
)
# Moves file, updates database with tracking info
```

### 3. Database Migration

**Changes to `services/database/migrations.py`**:

Added Migration 9 - Import tracking columns to `books` table:
- `file_path TEXT` - Full path to imported file
- `file_size INTEGER` - File size in bytes
- `file_format TEXT` - File format (M4B, MP3, etc.)
- `file_quality TEXT` - Quality descriptor (e.g., "M4B 128kbps Stereo")
- `imported_to_library BOOLEAN DEFAULT 0` - Import status flag
- `import_date INTEGER` - Unix timestamp of import
- `naming_template TEXT` - Template used for naming
- Index on `imported_to_library` for efficient queries

**Migration runs automatically on service startup.**

### 4. Configuration

**Changes to `services/config/defaults.py`**:

**AudioBookShelf section additions**:
```ini
[audiobookshelf]
library_path = /mnt/audiobooks
naming_template = standard
include_asin_in_path = false
create_author_folders = true
create_series_folders = true
```

**New import section**:
```ini
[import]
import_directory = /downloads/import
verify_after_import = true
create_backup_on_error = true
delete_source_after_import = false
use_hardlinks = false
```

### 5. Service Manager Integration

**Changes to `services/service_manager.py`**:

Added two new service getters:
- `get_file_naming_service()` - Returns FileNamingService singleton
- `get_import_service()` - Returns ImportService singleton

## Service Architecture

Both services follow the established **AuralArchive service pattern**:

```
services/
├── file_naming/                    # Flat folder structure
│   ├── file_naming_service.py     # Main singleton service
│   ├── template_parser.py         # Helper: Template operations
│   ├── path_generator.py          # Helper: Path generation
│   ├── sanitizer.py               # Helper: Path sanitization
│   └── __init__.py
│
└── import_service/                 # Flat folder structure
    ├── import_service.py           # Main singleton service
    ├── file_operations.py          # Helper: File move operations
    ├── database_operations.py      # Helper: Database tracking
    ├── validation.py               # Helper: Validation & quality
    └── __init__.py
```

**Pattern Features**:
- ✅ Singleton pattern (thread-safe)
- ✅ Flat folder structure (no nested helpers)
- ✅ Descriptive naming (operation purpose in filename)
- ✅ Composition pattern (main service uses helper classes)
- ✅ Lazy loading of dependencies
- ✅ Comprehensive error handling and logging

## Naming Templates

### Built-in Templates

1. **standard**: `{author}/{series}/{series_number} - {title} ({year}) - {narrator}`
   - Example: `Blake Crouch/Standalone/Anima (2024) - Jon Lindstrom.m4b`

2. **standard_asin**: `{author}/{series}/{series_number} - {title} ({year}) [{asin}] - {narrator}`
   - Example: `Blake Crouch/Standalone/Anima (2024) [B0C7GX8Z9P] - Jon Lindstrom.m4b`

3. **simple**: `{author}/{series}/{title}`
   - Example: `Blake Crouch/Standalone/Anima.m4b`

4. **simple_asin**: `{author}/{series}/{title} [{asin}]`
   - Example: `Blake Crouch/Standalone/Anima [B0C7GX8Z9P].m4b`

5. **flat**: `{author} - {title}`
   - Example: `Blake Crouch - Anima.m4b`

6. **flat_asin**: `{author} - {title} [{asin}]`
   - Example: `Blake Crouch - Anima [B0C7GX8Z9P].m4b`

### Custom Templates

Users can add custom templates via config or API:
```python
naming_service.add_custom_template(
    'my_template',
    '{series}/{series_number} - {title} - {narrator}'
)
```

## Import Workflow

### Complete Import Flow

```
1. User triggers import (via API/UI)
   ↓
2. ImportService.import_book(source_path, book_data)
   ↓
3. ImportValidator validates:
   - Source file exists and is readable
   - File format supported
   - Book metadata present
   - File size > 0
   ↓
4. FileNamingService generates destination path
   ↓
5. FileOperations performs atomic move:
   - Calculate source checksum (SHA256)
   - Check disk space (110% of file size)
   - Create destination directories
   - Move file (atomic if same filesystem)
   - Verify destination checksum
   ↓
6. Detect file quality (ffprobe)
   ↓
7. ImportDatabaseOperations updates books table:
   - file_path, file_size, file_format
   - file_quality, imported_to_library=1
   - import_date, naming_template
   ↓
8. Return success/failure to caller
```

## Linux-First Design

### Path Sanitization

**Linux Restrictions** (minimal):
- Invalid chars: `/` (path separator), `\x00` (null byte)
- Problematic chars replaced: tabs, newlines → spaces
- Max filename: 255 bytes (ext4/XFS standard)
- Max path: 4096 bytes

**Optional Windows Compatibility**:
```python
sanitizer = PathSanitizer(windows_compatible=True)
# Adds restrictions: < > : " | ? * \
```

**Why Linux-first?**
- Most characters valid on Linux (colons, quotes, special chars)
- Simpler rules = less data mangling
- Better preserves original titles
- Can enable Windows mode if needed for network shares

## Database Schema

### Books Table Import Columns

```sql
ALTER TABLE books ADD COLUMN file_path TEXT;
ALTER TABLE books ADD COLUMN file_size INTEGER;
ALTER TABLE books ADD COLUMN file_format TEXT;
ALTER TABLE books ADD COLUMN file_quality TEXT;
ALTER TABLE books ADD COLUMN imported_to_library BOOLEAN DEFAULT 0;
ALTER TABLE books ADD COLUMN import_date INTEGER;
ALTER TABLE books ADD COLUMN naming_template TEXT;

CREATE INDEX idx_books_imported_to_library ON books(imported_to_library);
```

### Query Examples

**Get all imported books**:
```sql
SELECT * FROM books WHERE imported_to_library = 1 ORDER BY import_date DESC;
```

**Get import statistics**:
```sql
SELECT 
    COUNT(*) as total_imported,
    SUM(file_size) as total_size_bytes,
    file_format,
    COUNT(*) as count_by_format
FROM books 
WHERE imported_to_library = 1 
GROUP BY file_format;
```

**Find book file path**:
```sql
SELECT file_path FROM books WHERE asin = 'B0C7GX8Z9P';
```

## API Integration

#### Import Staging Directory APIs

To keep browsers out of the loop, the server now exposes read-only endpoints for the configured staging directory (`import_directory`):

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/import/staging?path=relative/subdir` | GET | Lists immediate files and folders below the requested path. Returns breadcrumbs plus metadata (size, modified time, whether a file is importable). |
| `/api/import/staging/scan?recursive=true&extensions=m4b,mp3` | GET | Returns a flattened list of files under the requested path, filtered by extension and limited (default 500). Useful for bulk preview UIs. |

Both endpoints honor the `Import staging directory` setting from Media Management, refuse traversal outside that root, and surface friendly errors if the path is missing or unreadable.

### Import Service API Methods

```python
import_service = get_import_service()

# Import single book
success, msg, path = import_service.import_book(source, book_data)

# Import multiple books (batch)
results = import_service.import_multiple_books([
    {'source_file_path': '/tmp/book1.m4b', 'book_data': {...}},
    {'source_file_path': '/tmp/book2.m4b', 'book_data': {...}}
])

# Check import status
status = import_service.get_import_status('B0C7GX8Z9P')
# Returns: {'file_path': '...', 'file_size': 123456, 'imported_to_library': True, ...}

# Verify import still valid
is_valid, msg = import_service.verify_import('B0C7GX8Z9P')

# Get file path
file_path = import_service.get_file_path('B0C7GX8Z9P')

# Remove import (optionally delete file)
success, msg = import_service.remove_import_record('B0C7GX8Z9P', delete_file=True)
```

### File Naming Service API Methods

```python
naming_service = get_file_naming_service()

# Generate complete path
path = naming_service.generate_file_path(book_data, base_path, template_name, extension)

# Generate just folder path
folder = naming_service.generate_folder_path(book_data, base_path)

# Generate just filename
filename = naming_service.generate_filename(book_data, template_name, extension)

# Parse existing path
metadata = naming_service.parse_abs_path('/path/to/Author/Series/Book 01 - Title [ASIN].m4b')

# Template management
templates = naming_service.get_available_templates()
naming_service.add_custom_template('my_template', '{author}/{title}')
is_valid, error = naming_service.validate_template('{author}/{invalid_var}')

# Preview template
preview = naming_service.get_template_preview('standard_asin', sample_book_data)
```

## Testing Recommendations

### Manual Testing

1. **Create test book data**:
```python
test_book = {
    'Title': 'Test Audiobook',
    'Author': 'Test Author',
    'ASIN': 'B0TEST1234',
    'Series': 'Test Series',
    'BookNumber': '1',
    'Year': '2024',
    'Narrator': 'Test Narrator'
}
```

2. **Test file naming**:
```python
from services.service_manager import get_file_naming_service
naming = get_file_naming_service()
path = naming.generate_file_path(test_book, '/tmp/test', 'standard_asin', 'm4b')
print(path)
# Should output: /tmp/test/Test Author/Test Series/Book 01 - Test Audiobook (2024) [B0TEST1234] - Test Narrator.m4b
```

3. **Test import** (with actual M4B file):
```python
from services.service_manager import get_import_service
import_svc = get_import_service()
success, msg, path = import_svc.import_book('/tmp/test.m4b', test_book)
print(f"Success: {success}, Message: {msg}, Path: {path}")
```

4. **Verify database**:
```sql
SELECT asin, title, file_path, file_size, imported_to_library FROM books WHERE asin = 'B0TEST1234';
```

### Integration Points

The import service integrates with:
- **Download Service** (future): After conversion, call import_service.import_book()
- **Manual Import UI**: User selects file → import_book()
- **Batch Processing**: Process multiple downloads → import_multiple_books()
- **Library Management**: Query imported books, verify files exist
- **AudioBookShelf**: After import, ABS auto-scan detects new files

## Next Steps

### Future Enhancements (Not Implemented)

1. **Hardlink Support**: Option to hardlink instead of move (preserve downloads)
2. **Import Queue**: Queue imports for background processing
3. **Automatic Cleanup**: Delete old/orphaned files
4. **Re-import**: Change naming template and move existing files
5. **Import Monitoring**: Watch folder for new files
6. **File Deduplication**: Detect and skip duplicate files
7. **Import Notifications**: SocketIO events for real-time UI updates

### Download Service Integration

When Download Service is implemented, the workflow will be:

```
Download Complete
    ↓
Conversion Service (AAX/AAXC → M4B)
    ↓
Import Service (Move to library)
    ↓
Database Update (imported_to_library = 1)
    ↓
AudioBookShelf Auto-Scan (detects new file)
```

## Files Modified/Created

### Created
- `services/file_naming/file_naming_service.py` (267 lines)
- `services/file_naming/template_parser.py` (249 lines)
- `services/file_naming/path_generator.py` (253 lines)
- `services/file_naming/sanitizer.py` (281 lines)
- `services/file_naming/__init__.py` (9 lines)
- `services/import_service/import_service.py` (355 lines)
- `services/import_service/file_operations.py` (234 lines)
- `services/import_service/database_operations.py` (270 lines)
- `services/import_service/validation.py` (231 lines)
- `services/import_service/__init__.py` (9 lines)

### Modified
- `services/service_manager.py` - Added get_file_naming_service() and get_import_service()
- `services/database/migrations.py` - Added Migration 9 for import tracking columns
- `services/config/defaults.py` - Added import config section and naming settings

**Total Lines of Code**: ~2,400 lines across 15 files

## Success Criteria

✅ File naming service generates ABS-compatible paths  
✅ Import service moves files atomically with verification  
✅ Database tracks all import metadata  
✅ Configuration supports user-customizable templates  
✅ Service manager integration complete  
✅ Linux-first design with optional Windows compatibility  
✅ Follows established AuralArchive service patterns  
✅ Database migration runs automatically  
✅ Comprehensive error handling and logging  
✅ Ready for integration with download workflow  

---

**Implementation Complete**: All planned features implemented and ready for testing.
