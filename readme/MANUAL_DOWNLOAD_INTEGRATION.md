# Manual Download Integration with Download Management Service

## Overview
Integrated manual downloads (user-selected search results) with the full download management service pipeline. Manual downloads now follow the same workflow as automatic downloads, just skipping the search phase.

## Changes Made

### 1. **api/search_api.py** - Manual Download Endpoint
**File**: `/api/search_api.py`

**Before**: Manual downloads went directly to qBittorrent, bypassing the download management system entirely.

**After**: Manual downloads now:
1. Add to download queue via `DownloadManagementService.add_to_queue()`
2. Transition to `FOUND` state (skipping `SEARCHING` since user selected the source)
3. Trigger `_start_download()` to begin the pipeline
4. Flow through: DOWNLOADING → COMPLETE → CONVERTING → CONVERTED → IMPORTING → IMPORTED

**Key Features**:
- Generates pseudo-ASIN for non-library books (manual searches)
- Replaces localhost with host IP for Docker compatibility
- Supports both torrent and NZB downloads
- Properly tracks download metadata (title, author, quality, indexer, etc.)

### 2. **services/download_management/download_management_service.py** - Start Download Method
**File**: `/services/download_management/download_management_service.py`

**Updates**:
- Modified `_start_download()` to work with qBittorrent's actual API
- Properly captures torrent hash for monitoring
- Falls back to finding torrent by name/category if hash not returned
- Uses torrent hash as `download_client_id` for progress tracking
- Added `datetime` import for timestamps

**Key Features**:
- Reads qBittorrent category from config
- Creates temp directory for each download
- Handles torrent hash retrieval (direct or by search)
- Updates database with client info and started timestamp
- Emits SocketIO events for real-time updates

### 3. **app.py** - Service Initialization
**File**: `/app.py`

**Updates**:
- Added download management service initialization on startup
- Starts monitoring thread automatically
- Monitors every 2 seconds for active downloads

**Initialization Flow**:
```python
dm_service = get_download_management_service()
dm_service.start_monitoring()
```

### 4. **services/download_clients/qbittorrent_client.py** - Enhanced Client
**File**: `/services/download_clients/qbittorrent_client.py` (previous session)

**Already Enhanced**:
- Improved `add_torrent()` method with better multipart handling
- Support for optional parameters (tags, limits, sequential download, etc.)
- Added `Path` import for file handling
- Better error messaging

## Complete Download Flow

### Manual Download Flow
```
User selects search result
       ↓
POST /api/search/manual/download
       ↓
Add to download_queue (QUEUED state)
       ↓
Transition to FOUND (skip search)
       ↓
_start_download() → qBittorrent
       ↓
DOWNLOADING (monitor polls every 2s)
       ↓
COMPLETE (100% progress)
       ↓
CONVERTING (FFmpeg to M4B)
       ↓
CONVERTED
       ↓
IMPORTING (to library)
       ↓
IMPORTED (or SEEDING if enabled)
```

### Database Schema (download_queue)
```sql
- id (PRIMARY KEY)
- book_asin (ASIN or pseudo-ASIN)
- book_title
- book_author
- download_url
- download_client ('qbittorrent')
- download_client_id (torrent hash)
- download_type ('torrent' or 'nzb')
- status (QUEUED → FOUND → DOWNLOADING → COMPLETE → etc.)
- download_progress (0-100%)
- quality_score
- match_score
- file_format
- file_size
- indexer
- started_at
- completed_at
- temp_file_path
- converted_file_path
- final_file_path
```

## Frontend Integration

### Downloads Tab
**File**: `templates/downloads.html`

**JavaScript**:
- Polls `/api/downloads/queue` every 3 seconds
- Displays download status, progress, speed, ETA
- Shows controls: pause, resume, cancel
- Real-time updates via SocketIO events

**Display Fields**:
- Book title
- Status (QUEUED, DOWNLOADING, COMPLETE, etc.)
- Progress percentage
- Download speed (MB/s)
- Downloaded / Total size
- ETA
- Seeding ratio (if applicable)

## API Endpoints

### Download Management API
**Endpoint**: `/api/downloads/*`

**Available Operations**:
- `GET /api/downloads/queue` - Get all downloads
- `GET /api/downloads/queue/<id>` - Get specific download
- `POST /api/downloads/queue` - Add to queue (used by manual download)
- `DELETE /api/downloads/queue/<id>` - Cancel download
- `POST /api/downloads/queue/<id>/pause` - Pause download
- `POST /api/downloads/queue/<id>/resume` - Resume download
- `POST /api/downloads/queue/<id>/retry` - Retry failed download
- `GET /api/downloads/status` - Get service status
- `POST /api/downloads/service/start` - Start monitoring
- `POST /api/downloads/service/stop` - Stop monitoring

## Monitoring System

### Download Monitor
**File**: `services/download_management/download_monitor.py`

**Features**:
- 2-second polling interval
- Tracks active downloads in DOWNLOADING state
- Monitors seeding torrents
- Updates progress, speed, ETA in database
- Emits SocketIO events for frontend
- Detects completion (100% progress)
- Triggers state transitions

**Monitor Loop**:
1. Process queued items (QUEUED → FOUND or SEARCHING)
2. Monitor active downloads (poll qBittorrent)
3. Process completed stages (COMPLETE → conversion, etc.)
4. Handle seeding completion

## Configuration

### config/config.txt
```ini
[qbittorrent]
qb_host = 172.19.0.1
qb_port = 8080
qb_username = peronabg
qb_password = "01181236"
category = auralarchive

[download_management]
seeding_enabled = true
delete_source_after_import = false
temp_download_path = /tmp/aural_archive/downloads
temp_conversion_path = /tmp/aural_archive/converting
polling_interval_seconds = 2
max_concurrent_downloads = 2
retry_search_max = 3
retry_download_max = 2
retry_conversion_max = 1
retry_import_max = 2
```

## Benefits

### Before
- Manual downloads went directly to qBittorrent
- No tracking in AuralArchive database
- No progress monitoring
- No automatic conversion or library import
- User had to manually manage files

### After
- Full pipeline integration
- Real-time progress tracking
- Automatic conversion (AAX/AAXC/M4A → M4B)
- Automatic library import
- Seeding support with configurable goals
- Automatic cleanup
- Retry logic for failures
- Complete audit trail in database

## Testing

### Test Manual Download
1. Search for an audiobook
2. Click download button on search result
3. Check Downloads tab - should show download with status
4. Monitor progress in real-time
5. Verify transitions: QUEUED → FOUND → DOWNLOADING → COMPLETE → etc.
6. Check final file in library after import

### Verify in Database
```sql
SELECT * FROM download_queue ORDER BY id DESC LIMIT 10;
```

### Check Logs
```bash
tail -f logs/auralarchive_web.log | grep -E "(Download|manual_download)"
```

## Troubleshooting

### Downloads Not Appearing
1. Check if monitoring service is running: `GET /api/downloads/status`
2. Verify database connection
3. Check logs for errors

### Torrents Not Starting
1. Verify qBittorrent connection
2. Check localhost→IP replacement
3. Verify category exists in qBittorrent
4. Check qBittorrent logs

### Progress Not Updating
1. Verify torrent hash was captured
2. Check monitoring thread is running
3. Verify qBittorrent API responding
4. Check polling interval in config

## Future Enhancements

### Planned Features
1. NZB/Usenet support (SABnzbd, NZBGet)
2. Additional torrent clients (Deluge, Transmission)
3. Quality profiles and automatic selection
4. Download speed limits per download
5. Scheduled downloads
6. Bandwidth management
7. Multi-file audiobook handling
8. Automatic metadata enhancement
9. Cover art extraction and enhancement
10. Chapter marker preservation

## Related Files

### Core Services
- `services/download_management/download_management_service.py` - Main coordinator
- `services/download_management/queue_manager.py` - Database operations
- `services/download_management/download_monitor.py` - Progress tracking
- `services/download_management/state_machine.py` - State transitions
- `services/download_management/client_selector.py` - Client selection
- `services/download_management/event_emitter.py` - SocketIO events

### Download Clients
- `services/download_clients/qbittorrent_client.py` - qBittorrent integration
- `services/download_clients/base_torrent_client.py` - Base class

### API Endpoints
- `api/search_api.py` - Manual download endpoint
- `api/download_management_api.py` - Download queue API

### Frontend
- `templates/downloads.html` - Downloads page
- `routes/downloads.py` - Downloads route

### Database
- `services/database/migrations.py` - Schema migrations
- `services/database/database_service.py` - Database service

## Documentation
- `DOWNLOAD_MANAGEMENT_ARCHITECTURE.md` - Architecture overview
- `.github/copilot-instructions.md` - Project guidelines
- `DOWNLOAD_DEBUG_SUMMARY.md` - Previous debugging session
