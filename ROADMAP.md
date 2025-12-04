# AuralArchive Development Roadmap

A living document tracking feature implementations and future development plans

---

## Current Status
- **Last Updated**: November 4, 2025
- **Current Branch**: `dev`
- **Recent Major Completions**:
  - Search & Download Phase 1 - Search engine, Jackett integration, real indexer support
  - Series Management Complete - Full series tracking, deduplication, auto-sync
  - Download Clients Phase 2 Week 1 - qBittorrent integration, base torrent client
  - CSS Architecture Refactor - Modular CSS system, responsive design
  - Import Service Implementation - ASIN-based file import with automatic organization
- **Current Work**: Unified Download Pipeline Architecture - Integrating Audible downloads with queue-based pipeline

---

## Upcoming UI & Import Enhancements (November 16, 2025)

1. **Authors Tab Cleanup**  
    - Convert the Authors page to a single, table-style list view and remove the outdated card layout.  
    - Drop the export buttons from both the list and the author detail screen.  
    - Restore the missing author biography panel.  
    - Implement alias/pen-name deduplication so entries like *Shirtaloon* and *Travis Devrell* resolve to a single author profile while retaining searchable aliases.

2. **Downloads Tab Simplification**  
    - Remove the non-functional Audible streaming tracker widget and its accompanying stat block.  
    - Rename "Pipeline Downloads" to simply "Downloads" and trim the explanatory polling copy.  
    - Limit the "Recently Imported" list to a concise number of rows and reduce noise.  
    - Increase the download status poll cadence from 5s to 2s to keep progress current.

3. **Discover Tab Parity**  
    - Reuse the modern search results card + modal pattern for the Discover tab so fields (ratings, runtime, quality badges, etc.) match the Search experience.  
    - Remove the "Fresh Arrivals" section that currently appears beneath Discover since those entries now belong in the unified Discover feed.

4. **Manual Book Import Tab**  
    - Introduce a first-class **Import** tab dedicated to manual audiobook ingestion.  
    - Allow users to select a single file, a folder, or an entire directory tree; the service should inspect metadata (file tags, filename patterns, embedded cues) to identify the correct book.  
    - Apply the user-selected naming template, rename/organize the file, and relocate it into the configured library path—mirroring the automated pipeline but with manual source selection.  
    - Surface progress and results (success, conflicts, metadata decisions) directly within the tab.

---

## 1. Unified Download Management Pipeline

### Overview
**Status**: PLANNING (Design Phase)
**Priority**: Critical
**Goal**: Integrate Audible downloads with existing queue-based pipeline for automatic conversion and library import

### Current Problem
Two separate download systems operating independently:

**System A: Queue Pipeline (Torrents/NZB)**
- Database-tracked queue with state machine
- Automatic import to library
- Progress monitoring via Downloads tab
- Status: Working for torrent/NZB downloads only

**System B: Audible Streaming (Standalone)**
- Direct download from Audible API
- SocketIO progress updates
- Files saved to temp directory
- Status: No conversion, no import, orphaned files

**Result**: Audible downloads require manual conversion and organization

### Proposed Solution
Merge both systems into unified pipeline that handles all download types through single queue:

```
UNIFIED DOWNLOAD QUEUE
├── Audible Downloads
│   └── FOUND → DOWNLOADING → COMPLETE → CONVERTING → CONVERTED → IMPORTING → IMPORTED
│
└── Torrent/NZB Downloads
    └── FOUND → DOWNLOADING → COMPLETE → (skip conversion) → IMPORTING → IMPORTED
                                  │
                                  └→ SEEDING (optional) → cleanup after ratio/time goals
```

### Architecture Components

#### 1.1 Working Directory Structure
**Unified temporary workspace** (Docker-compatible):

```
/data/working/              # WORKING_DIR (configurable)
├── downloads/              # Active downloads
│   ├── 1/                 # Download ID folders
│   │   ├── book.aaxc      # Audible: AAX/AAXC files
│   │   └── book.voucher   # Audible: Voucher files
│   ├── 2/                 # Torrent: Files from qBittorrent
│   │   └── book.m4b       # (stays here while seeding)
│   └── 3/
└── converting/            # FFmpeg processing
    ├── 1/
    │   └── book.m4b       # Converted M4B output
    └── 3/
```

**Configuration**:
```ini
[download_management]
working_dir = /data/working              # Docker: /data/working, Dev: /tmp/aural_archive
temp_download_path = /data/working/downloads
temp_conversion_path = /data/working/converting
seeding_enabled = true
seeding_ratio_goal = 2.0
seeding_time_goal_hours = 72
delete_source_after_import = false
```

#### 1.2 Database Schema Updates
**New columns for `download_queue` table**:

```sql
ALTER TABLE download_queue ADD COLUMN download_type TEXT DEFAULT 'torrent';
ALTER TABLE download_queue ADD COLUMN temp_file_path TEXT;
ALTER TABLE download_queue ADD COLUMN converted_file_path TEXT;
ALTER TABLE download_queue ADD COLUMN final_file_path TEXT;
ALTER TABLE download_queue ADD COLUMN voucher_file_path TEXT;
ALTER TABLE download_queue ADD COLUMN indexer TEXT;
ALTER TABLE download_queue ADD COLUMN priority INTEGER DEFAULT 5;
```

**Purpose**:
- `download_type`: Distinguish 'audible', 'torrent', 'nzb'
- `temp_file_path`: Track downloaded file location
- `converted_file_path`: Track M4B after FFmpeg conversion
- `final_file_path`: Track final library location
- `voucher_file_path`: Store AAXC voucher for Audible
- `indexer`: Which indexer provided the result
- `priority`: Queue ordering (1-10, lower = higher priority)

#### 1.3 Download Type Branching
**Enhanced `_start_download()` with type detection**:

```python
def _start_download(self, download_id: int, source_info: Dict[str, Any]):
    download = self.queue_manager.get_download(download_id)
    download_type = download.get('download_type', 'torrent')
    
    if download_type == 'audible':
        self._start_audible_download(download_id)
    elif download_type in ('torrent', 'magnet'):
        self._start_torrent_download(download_id, source_info)
    elif download_type == 'nzb':
        self._start_usenet_download(download_id, source_info)
```

**New `_start_audible_download()` method**:
- Instantiate AudibleDownloadHelper
- Download AAX/AAXC to `working_dir/downloads/{id}/`
- Save voucher file for AAXC format
- Update queue with file paths
- Emit progress via SocketIO (reuse existing events)
- Transition to COMPLETE when done

#### 1.4 Conversion Detection (Enhanced)
**Explicit type checking added**:

```python
needs_conversion = (
    download_type == 'audible' or              # Explicit type check
    file_format in ('aax', 'aaxc') or         # Format check
    (temp_file_path and temp_file_path.endswith(('.aax', '.aaxc')))  # Extension check
)

if needs_conversion:
    self._start_conversion(download_id)       # AAX/AAXC → M4B
else:
    self.state_machine.transition(download_id, 'IMPORTING')  # Skip for M4B/MP3
    self._start_import(download_id)
```

#### 1.5 Import Phase (Type-Aware)
**Enhanced import with copy vs move logic**:

```python
def _start_import(self, download_id: int):
    download = self.queue_manager.get_download(download_id)
    download_type = download.get('download_type', 'torrent')
    
    # Determine source file
    if download_type == 'audible':
        source_file = download.get('converted_file_path')
        use_move = True  # Move file (no seeding for Audible)
    elif download_type == 'torrent':
        source_file = self._find_torrent_files(download_id)
        use_move = (download.get('status') != 'SEEDING')  # Copy if seeding, move otherwise
    
    # Import with appropriate method
    import_service = self._get_import_service()
    success, message, final_path = import_service.import_book(
        source_file_path=source_file,
        book_data=book_data,
        move=use_move  # True = move, False = copy
    )
```

**ImportService enhancement needed**:
- Add `move` parameter (default True for backward compatibility)
- Support copy mode for seeding torrents
- Implement `copy_file_atomic()` in FileOperations

#### 1.6 Cleanup Strategy
**Type-specific cleanup logic**:

**Audible Cleanup**:
1. After conversion: Delete AAX/AAXC source, delete voucher
2. After import: Delete converted M4B from converting/
3. Delete download folder

**Torrent Cleanup (No Seeding)**:
1. After import: Remove from qBittorrent
2. Delete download folder immediately

**Torrent Cleanup (With Seeding)**:
1. After import: COPY file to library (original stays in downloads/)
2. Continue seeding from downloads/ folder
3. Monitor ratio/time goals
4. When seeding complete: Remove from qBittorrent, delete downloads/ folder

#### 1.7 State Machine Flow

**Audible Downloads**:
```
FOUND → DOWNLOADING → COMPLETE → CONVERTING → CONVERTED → IMPORTING → IMPORTED → Cleanup
           ↓              ↓           ↓           ↓            ↓           ↓
      (download AAX) (save voucher) (FFmpeg) (delete AAX) (move M4B) (cleanup temp)
```

**Torrent (Seeding Disabled)**:
```
FOUND → DOWNLOADING → COMPLETE → IMPORTING → IMPORTED → Cleanup
           ↓              ↓           ↓           ↓
      (qBittorrent)  (detect M4B) (move file) (delete temp)
```

**Torrent (Seeding Enabled)**:
```
FOUND → DOWNLOADING → COMPLETE → SEEDING → IMPORTING → IMPORTED → Monitor Seeding
           ↓              ↓          ↓          ↓           ↓
      (qBittorrent)  (detect M4B) (continue) (copy file) (still in downloads/)
                                      ↓
                                  Monitor ratio/time
                                      ↓
                                  Seeding Complete → Cleanup
```

### Implementation Plan

**Phase 1: Database Migration**
- Add new columns to download_queue table
- Create migration script
- Update database service

**Phase 2: Audible Integration**
- Modify `/api/stream-download` to create queue entries
- Implement `_start_audible_download()` method
- Update ClientSelector to recognize 'audible' type
- Wire up AudibleDownloadHelper with progress callbacks

**Phase 3: Import Enhancement**
- Add copy mode to ImportService
- Implement copy_file_atomic() in FileOperations
- Update import logic to handle seeding torrents

**Phase 4: Cleanup Logic**
- Implement type-specific cleanup in CleanupManager
- Add voucher deletion after conversion
- Handle seeding completion cleanup

**Phase 5: UI Updates**
- Remove/hide streaming widget from Audible Library page
- Update Downloads page to show all types
- Add download type indicator in UI
- Redirect users to Downloads tab after initiating download

**Phase 6: Testing**
- Test Audible download → convert → import flow
- Test torrent with seeding enabled
- Test torrent with seeding disabled
- Verify cleanup for all scenarios
- Test error recovery and retry logic

### Key Design Decisions

**Seeding Implementation**:
- Files stay in downloads/ during seeding (cannot move while seeding)
- Import COPIES file to library while seeding continues
- Cleanup happens after seeding goals met

**Working Directory**:
- Docker-compatible path: /data/working
- Development fallback: /tmp/aural_archive
- User-configurable in settings

**Voucher Management**:
- Delete after successful conversion (not needed for re-conversion)
- Conversion service can extract keys directly from AAXC files

**Priority System**:
- Audible: Default priority 5 (same as torrents)
- User can adjust priority per download
- Lower number = higher priority in queue

### Benefits

**For Users**:
- One-click Audible downloads (no manual conversion)
- Automatic library organization
- Unified progress tracking
- Same workflow for all download types

**For System**:
- Reuse existing services (Conversion, Import, FileNaming)
- Consistent error handling and retry logic
- Single source of truth for download state
- Easier maintenance and debugging

---

## 2. Advanced Search & Download Management System

### Overview
**Status**: Phase 1 COMPLETED (100% Complete) | Phase 2 - Import Workflow Designed
**Completion Date**: Phase 1 - October 11, 2025 | Phase 2 Design - October 20, 2025

A comprehensive audiobook search and download management system inspired by Readarr and Sonarr, featuring intelligent fuzzy matching, quality assessment, automated download coordination, and reliable AudiobookShelf import.

**Phase 1 Completion Date**: October 11, 2025
**Phase 2 Import Design**: October 20, 2025

### Architecture Foundation

#### 2.1 COMPLETED - Search Engine Service Architecture
- **Location**: `services/search_engine/` (Flat structure following AuralArchive patterns)
- **Pattern**: Singleton service with operation helpers (following DatabaseService model)
- **Implementation**: Complete with 7 modules

**Core Components:**
- `search_engine_service.py` - Main singleton service with thread-safe initialization
- `search_operations.py` - Core search functionality and coordination
- `indexer_operations.py` - Indexer management and health monitoring
- `result_operations.py` - Result processing coordination layer
- `fuzzy_matcher.py` - Advanced fuzzy string matching using Readarr's Bitap algorithm
- `quality_assessor.py` - Quality scoring system (M4B>M4A>MP3, bitrate preferences)
- `result_processor.py` - Result filtering, deduplication, and ranking

**Key Features Implemented:**
- Singleton pattern with thread safety
- Manual and automatic search modes
- Readarr's Bitap algorithm for fuzzy matching
- Quality preferences (M4B: 10pts, M4A: 8pts, MP3: 6pts)
- Bitrate scoring (64kbps minimum, 128kbps preferred)
- Mock results for testing with "Anima" and "The Primal Hunter"
- Result deduplication and similarity detection
- Service status and health monitoring

#### 2.2 **COMPLETED** - Indexer Manager Service
- **Location**: `services/indexer_manager/indexer_manager_service.py`
- **Pattern**: Singleton service for indexer coordination
- **Integration**: Ready for Prowlarr and custom indexer support

**Features Implemented:**
- Health monitoring and failover logic
- Parallel search execution framework
- Rate limiting and throttling capabilities
- Mock indexer support for Phase 1 testing
- Indexer refresh and configuration management

#### 2.3 **COMPLETED** - Database Schema Implementation
- **Status**: Completed October 11, 2025
- **Scope**: Search-related database tables and schema
- **Database**: Fresh SQLite database with complete schema

**Implemented Tables:**
- `search_results` - Search history and result caching (19 columns)
- `indexer_status` - Indexer health and performance tracking (17 columns)
- `search_preferences` - Quality and format preferences (7 columns with defaults)
- `download_queue` - Automated download management (21 columns)

**Default Preferences Loaded:**
```
min_bitrate: 64 kbps
preferred_bitrate: 128 kbps
preferred_format: M4B
format_priority: M4B,M4A,MP3,FLAC
min_quality_score: 7.0
min_match_score: 80%
auto_download_enabled: false (for testing)
max_search_results: 50
search_timeout: 30 seconds
```

**Implementation Details:**
- Fresh database created (old backed up to `backups/`)
- All indexes created for performance
- Foreign key constraints properly defined
- Default preferences pre-populated

#### 2.4 **COMPLETED** - Search API Implementation
- **Status**: Completed October 11, 2025
- **Location**: `api/search_api.py`
- **Pattern**: Flask Blueprint at `/api/search`

**Implemented Endpoints:**
- `GET /api/search/health` - Service health check
- `GET /api/search/test` - Test search with "Anima" and "The Primal Hunter"
- `POST /api/search/manual` - Manual search interface
- `GET /api/search/status` - Service status and health
- `GET /api/search/indexers/status` - Indexer health monitoring

**API Features:**
- Proper error handling with status codes
- JSON response formatting
- Service availability checks
- Logging integration
- Test endpoints for validation

**Legacy API Status:**
- Old `manual_download_api.py` import removed
- Legacy endpoints deprecated
- Clean migration to new architecture

#### 2.5 **COMPLETED** - Service Manager Integration
- **Status**: Completed October 11, 2025
- **Location**: `services/service_manager.py`
- **Pattern**: Singleton pattern with lazy loading

**Implemented Updates:**
- `get_search_engine_service()` - SearchEngineService singleton access
- `get_indexer_manager_service()` - IndexerManagerService singleton access
- Lazy import pattern to avoid circular dependencies
- Service status tracking updated
- Convenience functions added

**Application Integration:**
- Services initialized in `app.py` startup
- Search API initialized with service dependencies
- Blueprint registered and routes active
- Health checks passing

### Technical Implementation Details

#### Quality Assessment System
**Format Scoring Matrix:**
```
M4B (Audiobook): 10 points - Best for audiobooks
M4A (AAC):       8 points  - Good quality
MP3:             6 points  - Acceptable
FLAC:            7 points  - High quality but large
AAC:             5 points  - Lower quality
OGG:             4 points  - Less common
Unknown:         1 point   - Unknown format
```

**Bitrate Scoring Algorithm:**
- Below 64kbps: 1.0 points (poor quality)
- 64-128kbps: Linear scale 3.0-8.0 points
- 128-320kbps: Linear scale 8.0-10.0 points
- Above 320kbps: 10.0 points (diminishing returns)

#### Fuzzy Matching Implementation
**Readarr's Bitap Algorithm Features:**
- Edit distance calculation with dynamic programming
- Word boundary detection and bonus scoring
- Title cleaning and normalization
- Multiple matching strategies (exact → substring → fuzzy)
- Configurable match thresholds (80% default)

#### Search Architecture Pattern
**Multi-layered Search Strategy:**
1. **Exact Match** - Direct title/author comparison
2. **Inexact Match** - Fuzzy matching with high threshold
3. **Fallback Fuzzy** - Lower threshold with broader matching
4. **Quality Filtering** - Remove results below minimum standards
5. **Ranking & Selection** - Quality-weighted result ordering

### Phase 1 Testing Requirements COMPLETED

**Test Audiobooks:**
- "Anima" by Blake Crouch - Mock results working
- "The Primal Hunter" by Zogarth - Mock results working

**Quality Preferences:**
- Minimum bitrate: 64kbps (configured)
- Preferred format: M4B > M4A > MP3 (scoring implemented)
- Auto-download only if quality score ≥ 7.0 and match score ≥ 80% (enforced)

**User Experience:**
- No user-accessible search settings (admin-configured)
- Manual search results show quality breakdown
- Automatic search silent with notification on success/failure

**Test Results:**
```json
Health Check: {
  "status": "healthy",
  "services": {
    "search_engine": true,
    "indexer_manager": true,
    "database": true
  }
}

Test Endpoint: {
  "success": true,
  "individual_tests": {
    "Anima_by_Blake Crouch": {
      "search_successful": true,
      "result_count": 2,
      "indexers_searched": 1
    },
    "The Primal Hunter_by_Zogarth": {
      "search_successful": true,
      "result_count": 2,
      "indexers_searched": 1
    }
  },
  "indexer_status": {
    "total_indexers": 2,
    "healthy_indexers": 2
  }
}
```

### Phase 1 Summary

**Completion**: 100% (All tasks completed)
**Completion Date**: October 11, 2025

**Files Created:**
- 7 search engine service modules
- 1 indexer manager service
- 1 search API module
- 4 database tables with indexes
- PHASE1_COMPLETION_SUMMARY.md

**Files Modified:**
- services/database/migrations.py
- services/service_manager.py
- app.py
- .github/copilot-instructions.md
- ROADMAP.md (this file)

**Architecture Compliance:**
- Flat service structure (DatabaseService pattern)
- Singleton pattern with thread safety
- Composition and delegation patterns
- Proper service manager integration
- Clean API design

**Testing Status:**
- Health checks passing
- Test endpoints functional
- Mock data working
- Services initializing correctly
- API responses formatted properly

### Future Phases (Post-Phase 1)

#### Phase 2: Download Client Integration WEEK 1 COMPLETE
**Status**: qBittorrent implemented, base classes created
**Completed**:
- BaseTorrentClient abstract class with standardized interface
- qBittorrent Web API v2 integration (compatible 4.1.0+)
- Torrent state management and health tracking
- Support for magnets, URLs, local files
- Session authentication and connection pooling

**In Progress**:
- Deluge client implementation
- Transmission client implementation  
- Download progress monitoring
- SABnzbd and NZBGet usenet integration

#### Phase 3: Real Indexer Integration COMPLETE
**Status**: Completed October 11, 2025
**Implemented**:
- Jackett/Torznab protocol support
- Priority-based multi-indexer architecture
- Parallel search execution across indexers
- Health monitoring and automatic failover
- Category filtering (Audiobooks = 3030)
- BaseIndexer abstract class for extensibility

**Architecture**:
```
services/indexers/
├── base_indexer.py              # Abstract interface
├── jackett_indexer.py           # Torznab implementation
└── indexer_service_manager.py   # Coordinator with priority system
```

#### Phase 4: Advanced Features
- Series detection and batch downloading
- Release group preferences and scoring
- Custom indexer configuration UI
- Advanced user preferences and filtering

#### Phase 5: Intelligence Features
- Machine learning quality assessment
- Download history analysis and optimization
- Predictive search and pre-caching
- Advanced metadata enhancement

---

## 3. Series Management System

### Status: COMPLETE (October 15, 2025)

A comprehensive series tracking system integrated with Audible API for complete series discovery and management.

### Architecture (Flat Folder Pattern)
```
services/audible/audible_series_service/
├── audible_series_service.py          # Main singleton service
├── series_relationship_extractor.py   # Extract series ASIN from relationships
├── series_data_fetcher.py             # Fetch series data from Audible
├── series_book_processor.py           # Process and deduplicate series books
└── series_database_sync.py            # Sync to database
```

### Database Schema (Migration v5)

**New Tables:**
1. **series_metadata** - Series information (ASIN, title, URL, cover, description)
2. **series_books** - Junction table for ALL books in series (owned + missing)
3. **Enhanced books table** - Added `series_asin` column for linking

### Key Features Implemented

#### 3.1 Series Discovery & Tracking
- Extract series ASIN from Audible API relationships
- Fetch complete series data including all books
- Track owned vs missing books in series
- AudiobookShelf sync status per book
- Sequence ordering and sort management

#### 3.2 Multi-Layer Deduplication System
**Problem**: Audible returns multiple editions (audiobook ASIN + print ISBN) for same book

**Solution**: Three independent protection layers

**Layer 1 - Application Level** (`series_book_processor.py`):
- Groups books by normalized title + sequence
- Scores editions: Audible ASIN (+100), ISBN (-100), metadata quality (+20-50)
- Keeps highest-scoring edition (newest releases prioritized)
- Runs automatically on all series syncs

**Layer 2 - Database Constraint**:
- UNIQUE(series_asin, book_asin) constraint prevents duplicates
- Blocks duplicate inserts at database level

**Layer 3 - Database Trigger** (Migration 9):
- `prevent_series_book_duplicates` trigger
- Blocks inferior editions (ISBNs) if Audible ASIN exists
- Works even if application code modified
- Persists across backups/restores

**Testing**: cleanup_series_duplicates.py script removed 151 duplicate entries

#### 3.3 Series Auto-Sync
- Manual "Sync Library Series" button
- Auto-sync when adding books to library
- Refresh series data from Audible
- Update missing books list
- Series detail pages with book status

### User Experience
- Series pages show complete book lists with owned/missing status
- One-click sync for all series in library
- Automatic deduplication (no user action needed)
- Clean series browsing without duplicate entries

---

## 4. CSS Architecture & UI System

### Status: COMPLETE (October 13, 2025)

Complete CSS refactoring into modular, maintainable architecture with responsive design.

### Architecture - Base CSS Layers (Loaded in base.html)

**Loading Order** (proper cascade):
1. **base.css** (609 lines) - Variables, reset, layouts, animations
2. **components.css** (1,300+ lines) - Buttons, cards, forms, badges
3. **navigation.css** (240 lines) - Top nav, tabs, view controls
4. **utilities.css** (550+ lines) - Spacing, display, colors, responsive
5. **notifications.css** - Toast notifications system

### Page-Specific CSS (Loaded per route)
- **library.css** - Book grid/list views, filters, bulk actions
- **search.css** - Search interface, results, interactive modal
- **settings.css** - Settings pages, forms, tabs
- **authors.css** - Author pages, analytics
- **discover.css** - Discovery interface, recommendations

### Key Features
- CSS variables for theming (colors, shadows, status)
- Responsive breakpoints (mobile, tablet, desktop)
- Custom scrollbars and animations
- Interactive search modal - horizontal rows (6-column layout)
- Grid/list view toggles
- Status badges and indicators
- Form components with validation states

---

## 1. Audible Services Enhancement

### Current State
- Multiple audible services exist in `/services/audible/` folder structure
- Additional audible services may be added in the future
- Current processing pipeline needs standardization for download → conversion → upload workflow

### Planned Features

#### 1.1 Configurable Shared Temp Folder
- **Feature**: Dedicated temporary workspace for all audiobook processing
- **Implementation**: 
  - Configuration setting for shared temp directory location
  - Used by all audible services (current and future additions)
  - Validation for folder permissions and disk space
  - Better organization and easier cleanup
- **Priority**: High
- **Status**: Planning

#### 1.2 FFmpeg Integration Service  
- **Feature**: Sequential audiobook format conversion **COMPLETED**
- **Supported Formats**: AAX, AAXC, MP3 (extensible for future formats)
- **Quality Strategy**: One consistent great quality setting (configurable via settings menu)
- **Processing Mode**: Sequential processing - one book at a time, even for full library downloads
- **Implementation**: 
  - Dedicated conversion service with progress tracking
  - Metadata preservation during conversion
  - Automatic temp file cleanup
  - Uses shared temp folder area
  - Configurable quality settings through settings API
- **Dependencies**: FFmpeg installation, shared temp folder configuration
- **Priority**: High
- **Status**: **Completed** - Service created with helper modules and settings API

#### 1.3 Universal Upload Service
- **Feature**: Standardized upload mechanism to AudiobookShelf
- **Integration**: Works with any download service (current and future)
- **Processing Strategy**: Process aborts on upload failure (no retry/skip logic)
- **Metadata Handling**: Services provide only metadata needed by AudiobookShelf upload API
- **Implementation**: 
  - Consistent upload workflow for all services
  - Real-time progress tracking with popup side window display
  - Automatic temp file management
  - Sequential processing with user-configurable concurrent limits (for future)
- **Priority**: Medium
- **Status**: Planning

---

## 1.b AudiobookShelf Service Refactor

### Current State
*[To be documented - current audiobook service implementation]*

### Planned Improvements

#### 1.b.1 Resource Optimization & Code Cleanup
- **Objective**: Refactor existing audiobook service for better resource utilization
- **Scope**: 
  - Memory management improvements
  - Connection pooling
  - Error handling standardization
  - Code deduplication
- **Priority**: Medium
- **Status**: Planning

#### 1.b.2 Centralized Service Architecture
- **Objective**: Create central service area similar to Audible services
- **Scope**: 
  - Unified service manager
  - Consistent API patterns
  - Shared helper utilities
  - Standardized configuration management
- **Priority**: Medium
- **Status**: Planning

---

## Outstanding Planning Questions

*These questions need to be addressed during implementation planning to finalize the service architecture and user experience.*

### Service Architecture & Integration
**21. Download Service Coordination**: Are you planning to add more download services beyond what currently exists? (e.g., direct downloads, different torrent clients, additional sources?)

**22. Progress Tracking Strategy**: For sequential processing (download → convert → upload), should progress tracking show:
   - Individual step progress (e.g., "Converting: 45% complete")
   - Overall pipeline progress (e.g., "Book 3 of 10: Converting...")  
   - Both with different UI elements?

**23. Configuration Scope**: For pipeline settings (temp folder, quality, concurrent limits), should these be:
   - Global settings affecting all operations
   - Per-service overrides with inheritance patterns
   - Both options available?

### Error Handling & Recovery
**24. Partial Failure Recovery**: If process fails at conversion step, should the system:
   - Keep downloaded file for manual retry later
   - Clean up and start fresh on retry
   - Offer both options to user?

**25. Disk Space Management**: For shared temp folder, should the system:
   - Monitor available disk space and warn/abort if insufficient
   - Automatically clean up old temp files after successful uploads
   - Have configurable retention policies for temp files?

### User Experience & Interface  
**26. Processing Queue Visibility**: When multiple books are processing sequentially, should users see:
   - Just the currently processing item
   - A queue of pending items
   - Detailed history of completed items?

**27. Background Processing**: Should the entire pipeline:
   - Block the UI until complete (user waits)
   - Run in background with notifications
   - Be interruptible/pausable by the user?

### Technical Implementation Details
**28. Service Communication**: How should the three services communicate:
   - Direct method calls between services
   - Event-driven architecture (publish/subscribe)
   - Queue-based processing with job status tracking?

**29. Metadata Flow**: When metadata flows from download service to upload, should it be:
   - Stored temporarily in the database
   - Passed directly in memory between services
   - Written to temporary metadata files alongside audio files?

**30. Testing Strategy**: For validating this pipeline, priority focus on:
   - Unit testing each service individually
   - Integration testing the full pipeline flow
   - Manual testing with real audiobook files
   - All approaches with different priorities?

---

## Service Architecture Standards

### **UPDATED** - Flat Service Structure Pattern
**Adopted**: October 1, 2025 based on actual AuralArchive database service patterns

All services follow a **flat folder structure** with **descriptive naming conventions**:

```
services/
└── service_domain/
    ├── service_domain_service.py    # Main service (singleton pattern)
    ├── operation_1.py               # Operation helper class
    ├── operation_2.py               # Operation helper class
    ├── helper_utility_1.py          # Utility helper class
    ├── helper_utility_2.py          # Utility helper class
    └── shared_utilities.py          # Shared utilities
```

#### Real Implementation Examples

**Database Service Pattern (Reference):**
```
services/database/
├── database_service.py             # Main DatabaseService (singleton)
├── connection.py                    # DatabaseConnection helper
├── migrations.py                    # DatabaseMigrations helper
├── books.py                         # BookOperations helper
├── authors.py                       # AuthorOperations helper
├── audible_library.py              # AudibleLibraryOperations helper
├── stats.py                         # DatabaseStats helper
└── error_handling.py               # Error handling utilities
```

**Search Engine Service Implementation:**
```
services/search_engine/
├── search_engine_service.py        # Main SearchEngineService (singleton)
├── search_operations.py            # SearchOperations helper
├── indexer_operations.py           # IndexerOperations helper
├── result_operations.py            # ResultOperations helper
├── fuzzy_matcher.py                # FuzzyMatcher helper
├── quality_assessor.py             # QualityAssessor helper
└── result_processor.py             # ResultProcessor helper
```

**Multi-Service Domains (Legacy):**
Complex domains like Audible maintain existing nested structure:
```
services/audible/
├── audible_service_manager.py       # Root-level service manager
├── audible_wishlist_service/
│   ├── audible_wishlist_service.py
│   └── audible_wishlist_service_helpers/
├── audible_catalog_service/
│   ├── audible_catalog_service.py
│   └── audible_catalog_service_helpers/
└── audible_recommendations_service/
    ├── audible_recommendations_service.py
    └── audible_recommendations_service_helpers/
```

#### Service Organization Rules
1. **Flat Structure**: New services use flat folder structure with descriptive naming
2. **Singleton Pattern**: Main service follows DatabaseService singleton pattern
3. **Composition Pattern**: Main service composes operation and helper classes
4. **Delegation Pattern**: Service methods delegate to appropriate helper classes
5. **Good Naming**: Use descriptive names instead of nested folders for organization
6. **Legacy Support**: Existing complex domains (like Audible) maintain current structure
7. **Thread Safety**: Singleton services use threading.Lock for initialization
8. **Dependency Injection**: Helper classes receive dependencies via constructor

#### Implementation Patterns

**Main Service Structure:**
```python
class ServiceNameService:
    _instance: Optional['ServiceNameService'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        # Singleton implementation
        
    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    # Initialize helper components
                    self.helper1 = Helper1()
                    self.helper2 = Helper2()
                    # Service initialization
                    ServiceNameService._initialized = True
    
    def _initialize_service(self):
        # Service-specific initialization
        pass
    
    def service_method(self):
        # Delegate to appropriate helper
        return self.helper1.operation()
```

**Helper Class Structure:**
```python
class HelperOperations:
    def __init__(self, dependency1, dependency2):
        self.logger = logging.getLogger("ServiceName.HelperOperations")
        self.dependency1 = dependency1
        self.dependency2 = dependency2
    
    def operation(self):
        # Implementation logic
        pass
```

---

## Critical Planning & Testing Requirements

### Priority 1: FFmpeg Conversion Testing - COMPLETED
**Status**: **Service implemented and tested**  
**Completion Date**: October 20, 2025

**Testing Implementation**:
- `test_universal_conversion.py` - Universal AAX/AAXC testing framework
- `test_conversion_aaxc.py` - AAXC-specific test suite
- Real audiobook file testing (AAX and AAXC formats)

**Validated Features**:
1. **Format Conversion**:
   - AAX → M4B (activation bytes method)
   - AAXC → M4B (voucher keys method)
   - Automatic format detection
   - Method selection and fallback logic
   
2. **Metadata Preservation**:
   - Metadata tags preserved through conversion
   - Chapter markers maintained
   - Narrator/author/title accuracy validated
   - FFprobe verification implemented

3. **Error Handling**:
   - Voucher file discovery and validation
   - Key extraction from voucher files
   - Activation bytes fallback for AAX
   - Command building validation
   - Output file integrity checks

4. **Performance Validation**:
   - Conversion timing tracked
   - File size comparison and validation
   - Output file format verification (FFprobe)
   - Audio properties validation (duration, bitrate, codec)

**Test Results** (from test_universal_conversion.py):
- Format detection working correctly (AAX vs AAXC)
- Voucher file discovery and key extraction functional
- Command building for both decryption methods validated
- Conversion execution successful with real audiobook files
- Output validation confirms proper M4B files created
- Metadata and chapter preservation verified

**Test Files Location**: `/debug/test_universal_conversion.py`, `/debug/test_conversion_aaxc.py`

---

### Priority 2: Download Tracking & Management Architecture 📋 PLANNING REQUIRED

**Current State**: 
- Download queue database table exists (`download_queue` - 21 columns)
- qBittorrent client can add/monitor torrents
- No orchestration layer connecting search → download → status tracking

**Critical Questions to Answer**:

#### 2.1 Download Lifecycle Management
**Question**: How should we track downloads through their complete lifecycle?

**Proposed States**:
```
QUEUED → SEARCHING → FOUND → DOWNLOADING → DOWNLOAD_COMPLETE → 
PROCESSING → CONVERTING → CONVERTED → IMPORTING → IMPORTED → COMPLETE

Error States: SEARCH_FAILED, DOWNLOAD_FAILED, CONVERSION_FAILED, IMPORT_FAILED
```

**Decisions Needed**:
- Should we support pause/resume at each stage?
- How do we handle retry logic? (max attempts, backoff strategy)
- Should users be able to cancel at any stage?
- What happens to files if process fails mid-pipeline?

#### 2.2 Download Queue Management
**Question**: How should the download queue be managed and prioritized?

**Options**:
1. **FIFO Queue** - Simple first-in-first-out
2. **Priority-based** - User can set priority levels
3. **Smart Queue** - Prioritize by series completion, file size, etc.

**Decisions Needed**:
- Can users manually reorder queue?
- Should series books be auto-grouped and prioritized together?
- How many concurrent downloads? (configurable? per-client?)
- How do we handle queue when adding full series (20+ books)?

#### 2.3 Progress Tracking & Notifications
**Question**: What level of detail should progress tracking provide?

**Tracking Levels**:
1. **High-Level**: "Downloading 3 of 10 books"
2. **Detailed**: "Book X: Downloading 45%, 2.3GB/5.1GB, ETA 15min"
3. **Granular**: Show each pipeline stage with individual progress

**Decisions Needed**:
- Real-time updates via SocketIO? Polling? Both?
- Notification triggers (download complete, all complete, errors only?)
- Should we track download history? (for statistics/analytics)
- Log level detail (debug logs vs user-facing status)?

#### 2.4 Multi-Source Download Strategy
**Question**: How do we handle multiple search results for same book?

**Scenarios**:
- Indexer A has M4B at 320kbps
- Indexer B has M4A at 128kbps  
- Indexer C has MP3 at 64kbps

**Options**:
1. **Best Quality First** - Try highest scoring result, fallback on failure
2. **Parallel Attempts** - Try multiple sources, keep first to complete
3. **User Choice** - Present options, user selects
4. **Automatic Fallback** - Try best, auto-fallback on timeout/failure

**Decisions Needed**:
- Timeout values for failed downloads?
- Should we blacklist bad indexers/sources?
- Track success rate per indexer for scoring?
- How to handle duplicate downloads (same book, different sources)?

#### 2.5 Download Client Selection
**Question**: With multiple download clients configured, how do we choose?

**Selection Strategies**:
1. **Priority-based** - User sets client priority (1-10)
2. **Round-robin** - Distribute load evenly
3. **Capability-based** - Use torrent client for magnets, usenet for NZBs
4. **Health-based** - Avoid clients with high failure rates

**Decisions Needed**:
- Can user override automatic selection?
- Should we support client-specific quotas/limits?
- Failover behavior when primary client unavailable?
- How to handle client going offline mid-download?

#### 2.6 Storage & Cleanup Management
**Question**: How do we manage downloaded files through the pipeline?

**Pipeline Flow**:
```
Download → Temp Storage → Conversion → Converted Storage → 
Import to ABS → Cleanup Original → Cleanup Temp
```

**Decisions Needed**:
- Separate temp folders per pipeline stage?
- Retention policy for failed downloads?
- Disk space monitoring and warnings?
- Should we keep original after successful import? (configurable?)
- Cleanup timing (immediate vs scheduled vs manual)?

**Proposed Architecture**:
```
services/download_orchestrator/
├── download_orchestrator_service.py    # Main coordinator
├── download_queue_manager.py           # Queue management
├── download_state_machine.py           # State transitions
├── progress_tracker.py                 # Progress monitoring
├── client_selector.py                  # Client selection logic
└── cleanup_manager.py                  # File cleanup coordination
```

**Action Items**:
- [ ] Define complete state machine with transitions
- [ ] Design database schema updates needed
- [ ] Create download orchestrator service structure
- [ ] Document retry/fallback strategies
- [ ] Plan SocketIO event architecture for real-time updates

---

### Priority 3: AudiobookShelf Import Workflow IMPLEMENTATION COMPLETE

**Status**: **COMPLETE** | **Completed**: October 27, 2025
**Implementation**: ASIN-based file import with automatic folder organization

#### Completed Implementation

**Services Created**:
1. `services/file_naming/` - Path generation and sanitization (4 modules)
   - Template-based filename generation (6 templates)
   - Author/Series/Book folder structure
   - Path sanitization with absolute path support
   - Template parser with database field compatibility

2. `services/import_service/` - Audiobook import management (5 modules)
   - ASIN-based import workflow
   - Atomic file operations with SHA256 verification
   - Database tracking of imports
   - Filename ASIN extraction
   - Book search capabilities for manual import

**Database Schema** (Migration 9):
```sql
-- Added to books table
file_path TEXT,              -- Path to imported file
file_size INTEGER,           -- File size in bytes
file_format TEXT,            -- M4B, MP3, etc.
file_quality TEXT,           -- Quality assessment
imported_to_library INTEGER, -- Boolean flag
import_date TEXT,            -- Import timestamp
naming_template TEXT         -- Template used
```

**Naming Templates Implemented**:
```
Author/Series/Book/Book [ASIN].m4b structure:

standard:      {author}/{series}/{title}/{series_number} - {title} ({year}) - {narrator}
standard_asin: {author}/{series}/{title}/{series_number} - {title} ({year}) [{asin}] - {narrator}
simple:        {author}/{series}/{title}/{title}
simple_asin:   {author}/{series}/{title}/{title} [{asin}]  ← DEFAULT
flat:          {author}/{title}/{title}
flat_asin:     {author}/{title}/{title} [{asin}]
```

**Configuration Settings**:
```ini
[audiobookshelf]
library_path = /media/MS_TV2/Audiobooks/Audiobooks
naming_template = simple_asin
include_asin_in_path = false
create_author_folders = false  # Handled by templates
create_series_folders = false  # Handled by templates

[import]
verify_after_import = false
create_backup_on_error = true
```

**Key Features**:
- ASIN extraction from filename `[B0XXXXXXXXX]` format
- Database lookup by ASIN for metadata
- Template-based path generation
- Automatic folder creation (Author/Series/Book)
- Atomic file moves with verification
- SHA256 integrity checking
- Database field name compatibility (AuthorName, SeriesName, etc.)
- Absolute path preservation in sanitization
- Circular dependency resolution (lazy config loading)

**Import Workflow**:
```python
# 1. Extract ASIN from filename or provide explicitly
import_service.auto_import_file("/path/to/Book [B0ABC123DE].m4b")

# 2. Service extracts ASIN: B0ABC123DE
# 3. Looks up book in database by ASIN
# 4. Generates path using template:
#    /media/.../Dakota Krout/The Completionist Chronicles/Tenacity/Tenacity [B0CK4ZRWMY].m4b
# 5. Moves file atomically
# 6. Updates database with import info
```

**Testing**:
- `debug/test_import_service.py` - Full import workflow test
- `debug/test_auto_import.py` - ASIN-based auto-import test
- Successfully imported 638MB test file
- Verified folder structure creation
- Verified database updates

**Files Created**:
```
services/file_naming/
├── file_naming_service.py (256 lines)
├── template_parser.py (268 lines)
├── path_generator.py (275 lines)
└── sanitizer.py (331 lines)

services/import_service/
├── import_service.py (452 lines)
├── file_operations.py
├── database_operations.py
├── validation.py (240 lines)
└── filename_matcher.py (with ASIN extraction)

debug/
├── test_import_service.py (313 lines)
└── test_auto_import.py (automated ASIN-based testing)
```

**TODO - Future Enhancements**:
- [ ] Audio file metadata extraction (mutagen/ffprobe)
- [ ] Extract ASIN from M4B/AAX metadata tags
- [ ] Manual book selection UI for files without ASIN
- [ ] Batch import support
- [ ] Import progress tracking via SocketIO
- [ ] Import history and statistics
- [ ] AudiobookShelf library scan trigger after import
- [ ] Duplicate detection before import

**Next Step**: Proceed to Download Management Architecture (Priority 2)

#### Design Decision: File Placement + ABS Scan Approach

**Chosen Strategy**: **File Placement + Library Scan + Quick Match**
- User concern: *"most reliable, and not resource intensive way to get a book into the audiobookshelf library and ensure it is properly identified by abs"*
- Solution: Leverage ABS's native scan workflow with ASIN-assisted matching

**Why This Approach**:
1. **Most Reliable**: Natural ABS workflow (how users manually add books)
2. **Not Resource Intensive**: No complex upload API, just file system operations
3. **Best Identification**: ASIN ensures accurate Audible matching
4. **Simplest Integration**: ABS handles everything after file placement
5. **Atomic Operations**: Move file → scan → verify (clean failure modes)

#### AudiobookShelf API Research Summary

**Key API Capabilities Discovered**:

1. **Library Scanning** (`POST /api/libraries/{ID}/scan`)
   - Discovers new/changed files automatically
   - Returns: `{added, updated, missing}` counts
   - Can force rescan with `force=1` parameter
   - Natural way books enter ABS

2. **Quick Match** (`POST /api/items/{ID}/match`)
   - Searches metadata providers (Google, OpenLibrary, Audible, etc.)
   - Parameters: `provider`, `title`, `author`, `isbn`, `asin`, `overrideDefaults`
   - **ASIN provides highest accuracy** (direct Audible lookup)
   - Fills missing details by default, can override with settings
   - Response: `{updated: boolean, libraryItem: object}`

3. **Metadata Providers Supported**:
   - `audible`, `audible.ca`, `audible.uk`, `audible.au`, `audible.fr`, `audible.de`, `audible.jp`, `audible.it`, `audible.in`, `audible.es`
   - `google` (Google Books), `openlibrary`, `itunes`, `fantlab`

4. **Library Settings Control Matching**:
   - `skipMatchingMediaWithAsin`: Skip books that already have ASIN
   - `skipMatchingMediaWithIsbn`: Skip books that already have ISBN
   - `scannerPreferMatchedMetadata`: Override with matched data (server setting)

5. **Metadata Embedding** (`POST /api/tools/item/{ID}/embed-metadata`)
   - Optional: Can embed after import if needed
   - Updates ID3 tags in audio files
   - Has `backup` and `forceEmbedChapters` options

6. **File Support**:
   - Audio: M4B, MP3, MP4, M4A, FLAC, OGG, OPUS, AAC, WAV, etc.
   - Metadata: Reads ID3 tags, embedded chapters, cover art

#### Recommended Import Workflow

**Pipeline**: `Download → Convert (M4B) → Move to ABS → Scan → Quick Match → Verify`

**Step-by-Step Process**:

```python
# Step 1: Convert to M4B (if needed)
# - FFmpeg conversion with minimal metadata (title, author for filename)
# - No deep metadata embedding required (ABS will handle)
# - Focus: Clean M4B file, good audio quality

# Step 2: Place file in ABS library folder
# - Organized structure: /library/Author Name/Book Title/book.m4b
# - Include cover.jpg if available from Audible
# - Atomic move operation (no partial files)

# Step 3: Trigger ABS library scan
response = requests.post(f"{abs_url}/api/libraries/{library_id}/scan")
# Wait for scan completion (check scan_complete socket event)

# Step 4: Find newly added item
# - Search ABS library for our book (by title/author)
# - Get library item ID

# Step 5: Quick match with ASIN
response = requests.post(
    f"{abs_url}/api/items/{item_id}/match",
    json={
        "provider": "audible",  # Use appropriate region
        "asin": audible_asin,   # Our Audible data
        "title": book_title,
        "author": author_name,
        "overrideDefaults": False  # Fill missing, don't override
    }
)

# Step 6: Verify match success
if response.json()["updated"]:
    # Success: ABS populated metadata from Audible
    # Book now has: cover, description, series, narrator, etc.
    pass
else:
    # Match failed: Log warning, may need manual intervention
    # Book still usable, just missing some metadata
    pass

# Step 7: Optional - Verify metadata quality
item = requests.get(f"{abs_url}/api/items/{item_id}").json()
if not item["media"]["metadata"].get("series"):
    # Missing expected data, could try alternate provider
    pass
```

**Error Handling Strategy**:

```python
# Scenario 1: ASIN match fails
if not quick_match_success:
    # Fallback 1: Try Google Books with title/author
    # Fallback 2: Try Open Library
    # Fallback 3: Leave for user manual matching in ABS UI

# Scenario 2: Scan doesn't detect file
if scan_result["added"] == 0:
    # Check file permissions, path correctness
    # Retry scan with force=1
    # Alert user of import failure

# Scenario 3: Wrong book matched
if matched_asin != expected_asin:
    # Log mismatch for review
    # Option to re-match with different provider
    # Option to manually update via ABS UI
```

#### Metadata Philosophy

**Our Approach**: **Minimal Embedding + ABS Quick Match**

**What We DO**:
- Convert to M4B (clean audio file)
- Organize folder structure (Author/Title)
- Include cover.jpg from Audible
- Provide ASIN to ABS for matching
- Let ABS handle metadata population

**What We DON'T**:
- Deep metadata embedding in M4B (ABS's job)
- Complex ID3 tag manipulation
- Metadata conflict resolution (ABS handles)
- Manual metadata updates (use ABS API)

**Rationale**:
- ABS designed for this workflow
- ASIN-based matching highly accurate
- Simpler conversion (just audio quality)
- Leverages ABS's metadata providers
- Reduces our maintenance burden

#### Implementation Architecture

**New Service**: `services/abs_import/abs_import_service.py`

```python
class ABSImportService:
    """Handles import of converted audiobooks to AudiobookShelf"""
    
    def __init__(self):
        self.abs_url = config.get("abs_url")
        self.abs_token = config.get("abs_token") 
        self.library_id = config.get("abs_library_id")
        self.library_path = config.get("abs_library_path")
    
    def import_audiobook(self, m4b_path, audible_metadata):
        """Complete import workflow"""
        # 1. Organize file structure
        dest_path = self._organize_file(m4b_path, audible_metadata)
        
        # 2. Move cover art
        self._move_cover(audible_metadata["cover_url"], dest_path)
        
        # 3. Scan library
        scan_result = self._scan_library()
        
        # 4. Find new item
        item_id = self._find_item_by_title(audible_metadata["title"])
        
        # 5. Quick match with ASIN
        match_result = self._quick_match(item_id, audible_metadata)
        
        # 6. Verify and return
        return self._verify_import(item_id, audible_metadata)
    
    def _organize_file(self, m4b_path, metadata):
        """Create Author/Title folder structure"""
        author = self._sanitize_filename(metadata["author"])
        title = self._sanitize_filename(metadata["title"])
        dest_dir = Path(self.library_path) / author / title
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        dest_file = dest_dir / f"{title}.m4b"
        shutil.move(m4b_path, dest_file)
        return dest_dir
    
    def _quick_match(self, item_id, metadata):
        """Match using ASIN for accuracy"""
        return requests.post(
            f"{self.abs_url}/api/items/{item_id}/match",
            headers={"Authorization": f"Bearer {self.abs_token}"},
            json={
                "provider": "audible",  # or audible.uk, etc.
                "asin": metadata["asin"],
                "title": metadata["title"],
                "author": metadata["author"],
                "overrideDefaults": False
            }
        )
```

**Integration Points**:
- `services/conversion/` → produces M4B file
- `services/abs_import/` → imports to ABS (NEW)
- `services/database/` → tracks import status

#### Database Updates Needed

**New Fields for `books` or `download_queue` table**:
```sql
-- Track ABS import status
abs_library_item_id VARCHAR(50),  -- ABS's item ID
abs_import_status VARCHAR(20),     -- pending, scanning, matched, verified, failed
abs_import_date INTEGER,           -- timestamp of successful import
abs_match_provider VARCHAR(20),    -- which provider matched (audible, google, etc)
abs_match_confidence FLOAT,        -- how confident was the match
```

**Import Status Flow**:
```
NULL → pending → scanning → matched → verified
       ↓          ↓          ↓
      failed    failed    failed
```

#### Configuration Requirements

**New Config Settings** (`config/config.py`):
```python
# AudiobookShelf Integration
"abs_url": "http://localhost:13378",
"abs_token": "",  # User's ABS API token
"abs_library_id": "",  # Target library ID
"abs_library_path": "/audiobooks",  # ABS library folder
"abs_scan_timeout": 60,  # Seconds to wait for scan
"abs_match_timeout": 30,  # Seconds to wait for match
"abs_verify_metadata": True,  # Check metadata after import
"abs_region": "audible",  # or audible.uk, audible.ca, etc.
```

#### Testing Strategy

**Test Scenarios**:
1. **Happy Path**: Convert → Place → Scan → Match with ASIN → Verify
2. **Match Failure**: ASIN match fails → fallback to Google Books
3. **Scan Miss**: File not detected → check permissions → retry
4. **Wrong Match**: Matched different book → log for review
5. **Partial Metadata**: Some fields missing → acceptable, mark verified
6. **Network Error**: ABS offline → queue for retry
7. **Duplicate Detection**: Book already in ABS → skip import

**Metrics to Track**:
- Import success rate (%)
- Average import time (seconds)
- Match accuracy (ASIN vs title matched)
- Fallback usage rate (%)
- Metadata completeness (% of expected fields)

#### Action Items

**Phase 1: Core Import** (Highest Priority):
- [ ] Create `abs_import_service.py` with basic workflow
- [ ] Implement file organization (Author/Title structure)
- [ ] Implement library scan + wait for completion
- [ ] Implement quick match with ASIN
- [ ] Add basic error handling and logging

**Phase 2: Verification & Monitoring**:
- [ ] Implement metadata verification checks
- [ ] Add import status tracking to database
- [ ] Create import progress SocketIO events
- [ ] Build retry logic for failed imports
- [ ] Add import history tracking

**Phase 3: Advanced Features**:
- [ ] Implement fallback provider chain (Audible → Google → OpenLibrary)
- [ ] Add duplicate detection (check if already in ABS)
- [ ] Build metadata quality scoring
- [ ] Create manual review queue for low-confidence imports
- [ ] Add batch import support

**Phase 4: User Interface**:
- [ ] Create import status dashboard
- [ ] Add manual retry/review interface
- [ ] Show ABS metadata preview before import
- [ ] Allow provider override for manual imports
- [ ] Display import statistics and metrics

---

## Development Resources

### Test Files
All test files moved to `/debug/` folder for organization:
- `test_audible_implementation.py` - Audible API integration tests
- `test_author_extraction.py` - Author parsing tests
- `test_book_number_impact.py` - Book numbering tests
- `test_confidence_score.py` - Search confidence scoring
- `test_deduplication_trigger.py` - Series deduplication trigger validation
- `test_enhanced_audible_service.py` - Enhanced Audible service tests
- `test_indexer_integration.py` - Indexer integration tests
- `test_number_extraction.py` - Number extraction validation
- `test_polling_system.py` - Polling system tests
- `test_qbittorrent_client.py` - qBittorrent client tests
- `test_query_cleaning.py` - Query cleaning tests
- `test_series_asin_extraction.py` - Series ASIN extraction tests
- `test_series_extraction.py` - Series metadata extraction tests

### Documentation Archive
Technical documentation consolidated into ROADMAP.md. Individual feature docs archived to `/debug/` for reference:
- Series management (deduplication, auto-sync, ASIN extraction)
- Search & indexer integration (Jackett, Torznab, fuzzy matching)
- CSS architecture (modular system, components, utilities)
- Download clients (qBittorrent, base classes, torrent management)
- Phase completion summaries

---

## Implementation Guidelines

### Git Workflow
- Update this roadmap with every feature completion
- Include roadmap updates in all significant commits
- Use feature branches for major implementations
- Document breaking changes and migration paths

### Documentation Requirements
- Update service documentation with each implementation
- Include usage examples for new services
- Document configuration options and requirements
- Maintain API documentation for shared services

---

*This roadmap will be updated after each feature implementation and with every significant git push.*