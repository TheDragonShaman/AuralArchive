# Download Workflow Verification

## Manual Download Workflow (User-Selected Torrents)

**Path:** UI → API → qBittorrent (DIRECT)

### Flow:
1. **User clicks "Download" button** on search result in `library.html`
   - JavaScript `downloadRelease(encodedResult)` function called
   - Payload created with result data (magnet/URL, title, metadata)

2. **POST to `/api/search/manual/download`** in `search_api.py`
   - No queue involvement at all
   - Extracts download link from result
   - Connects to qBittorrent directly via `QBittorrentClient`
   - Sends torrent/magnet to qBittorrent
   - Returns success/error to UI

3. **qBittorrent handles download**
   - qBittorrent manages its own download queue
   - No AuralArchive tracking or intervention
   - User manages via qBittorrent Web UI

### Key Points:
- ✅ **NO** interaction with `download_queue` table
- ✅ **NO** involvement from `DownloadManagementService`
- ✅ **NO** monitoring or state tracking
- ✅ Clean, direct submission to download client

---

## Automatic Search Workflow (Scheduled/Requested Book Downloads)

**Path:** API → Queue → Search → Download Client

### Flow:
1. **Add book to queue via `/api/downloads/queue`**
   - Creates entry in `download_queue` table with `status='QUEUED'`
   - Includes `book_asin`, `priority`, optional `search_result_id`

2. **Monitoring loop processes queue** (`_process_queue()` every 2 seconds)
   - Finds items with `status='QUEUED'`
   - **If `search_result_id` exists:** Skip to `FOUND` state
   - **If no search result:** Transition to `SEARCHING`, trigger search

3. **Search phase** (`_start_search()`)
   - Uses SearchEngineService to find torrents/NZBs
   - Selects best result based on quality/seeds
   - Updates queue entry with result, transitions to `FOUND`

4. **Download phase** (`_start_download()`)
   - Sends selected result to download client (qBittorrent)
   - Transitions to `DOWNLOADING`
   - Monitors progress via polling

5. **Post-download pipeline**
   - `DOWNLOADING` → `COMPLETE` (download finished)
   - **Audible downloads (AAX/AAXC):**
     - `COMPLETE` → `CONVERTING` (FFmpeg conversion to M4B)
     - `CONVERTING` → `CONVERTED`
     - `CONVERTED` → `IMPORTING` (to AudioBookShelf)
   - **Torrent/NZB downloads (M4B/MP3):**
     - `COMPLETE` → `IMPORTING` (skip conversion, already in correct format)
   - `IMPORTING` → `IMPORTED` (complete)

### Key Points:
- ✅ Queue is for **automatic search task ordering**
- ✅ Determines **which book to search for next** based on priority
- ✅ Tracks complete pipeline from search → download → import
- ✅ **Smart conversion**: Only converts Audible downloads (AAX/AAXC), skips for torrents/NZBs
- ✅ Monitoring service processes queue continuously

---

## Critical Distinctions

### Manual Downloads:
- User-initiated from search results
- Already have download link (no search needed)
- Go **directly to download client**
- **Zero queue involvement**

### Automatic Downloads:
- System-initiated (scheduled, requested, wishlist sync)
- Need to **search for download links first**
- Queue determines **search order** by priority
- Full pipeline tracking through all stages

---

## Queue Purpose Clarification

The `download_queue` table is **NOT** a download tracking system. It is:

1. **Search Task Queue**: Determines order of books to search for
2. **Priority Queue**: Higher priority books searched first
3. **Pipeline Tracker**: Tracks complete journey from search → import
4. **State Machine**: Manages transitions between pipeline stages

The queue **does not control downloads** - it controls **search ordering** and tracks the **complete automation pipeline**.

---

## Verification Checklist

### Manual Download Path:
- [x] No `add_to_queue()` calls in manual download API
- [x] No queue_manager interaction
- [x] Direct qBittorrent client usage
- [x] No monitoring service involvement
- [x] Clean error handling without state transitions

### Automatic Download Path:
- [x] Queue entry created with QUEUED status
- [x] Monitoring loop processes QUEUED items
- [x] Search triggered for items without search_result_id
- [x] Download client called after search completes
- [x] **Conversion detection**: Audible downloads (AAX/AAXC) go through conversion
- [x] **Conversion skip**: Torrent/NZB downloads (M4B/MP3) skip directly to import
- [x] State transitions tracked through pipeline

### Separation of Concerns:
- [x] Manual downloads bypass all automation
- [x] Queue only used for automatic operations
- [x] No overlap between manual and automatic paths
- [x] Each path fully independent

---

## Conclusion

**The workflows are properly separated:**

1. **Manual downloads** use a simple, direct path to qBittorrent
2. **Automatic downloads** use the queue to manage search ordering and pipeline tracking
3. The monitoring service **only processes queue entries** - it cannot interfere with manual downloads
4. No shared code paths between manual and automatic workflows

✅ **Verification Complete** - Both workflows function correctly without interference.
