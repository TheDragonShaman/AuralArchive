# AudioBookShelf Sync

Integrate AuralArchive with AudioBookShelf for playback and two-way library synchronization.

## What is AudioBookShelf?

AudioBookShelf is a self-hosted audiobook and podcast server with apps for iOS and Android. Integration allows:
- Two-way library synchronization
- Progress tracking
- Metadata sharing
- Automated library updates

## Prerequisites

- AudioBookShelf server installed and running
- Admin access to AudioBookShelf
- Network connectivity between AuralArchive and AudioBookShelf

## Initial Setup

### 1. Configure AudioBookShelf

In your AudioBookShelf server:

1. Create a library folder (if not already done)
2. Note the library path
3. Configure library settings

### 2. Obtain API Token

#### From AudioBookShelf:
1. Go to **Settings** → **API Keys**
2. Click **Add API Key**
3. In Name box put **AuralArchive**, leave expires box blank
4. Select user
5. Click **Submit**
6. Copy the token
7. Paste into AuralArchive

#### In AuralArchive:
1. Go to **Settings** → **AudioBookShelf Integration**
2. Enter your AudioBookShelf URL (e.g., `http://localhost:13378`)
3. Paste the API token
4. Click **Save Configuration**
5. Click **Test Connection** to verify

### 3. Configure Library Mapping

Map AuralArchive's download folder to AudioBookShelf:

1. Ensure AudioBookShelf can access AuralArchive's download directory
2. In AudioBookShelf, add library with path to downloads
3. Configure library to scan for audiobooks

## Syncing Libraries

### NOTE ###

When performing an initial sync to ABS it is best to do a manual sync and it will take a few moments depending on libary size. After the inital sycn perform a bulk metadata update via the libary page and the select books option. Depending on the size on the library this could take a while. This will grab all the metadata AuralArchive needs for your library. 

### Manual Sync from AuralArchive to AudioBookShelf

1. Go to **Settings** → **AudioBookShelf Integration**
2. Click **Sync to AudioBookShelf**
3. Monitor sync progress
4. Refresh AudioBookShelf library when complete

### Manual Sync from AudioBookShelf to AuralArchive

1. Go to **Library** page
2. Click **Sync from AudioBookShelf**
3. Wait for sync to complete
4. New items will appear in your library

### Automatic Sync

Configure automatic two-way synchronization:

1. Go to **Settings** → **AudioBookShelf Integration**
2. Enable **Auto-sync**
3. Set sync interval (hourly, daily, weekly)
4. Enable desired sync directions:
   - **Push to ABS** - Send new items to AudioBookShelf
   - **Pull from ABS** - Import items from AudioBookShelf
5. Click **Save Settings**

## Large Library Sync

For libraries with thousands of items, pagination improves performance.

### Configure Pagination

Set the `ABS_SYNC_PAGE_SIZE` environment variable in docker-compose.yml:

```yaml
services:
  auralarchive:
    environment:
      - ABS_SYNC_PAGE_SIZE=500  # Items per page (default)
```

**Recommended page sizes:**
- **Small libraries (<1000 items)**: 1000
- **Medium libraries (1000-5000 items)**: 500 (default)
- **Large libraries (5000-20000 items)**: 250
- **Very large libraries (>20000 items)**: 100

### Background Sync

Syncing runs in the background with real-time progress updates:

1. Start sync from Settings or Library page
2. Progress bar displays current status
3. You can continue using AuralArchive
4. Notification appears when complete
5. Click **Refresh Library** to see new items

### Monitoring Sync Progress

Real-time progress information:
- **Items Processed**: X / Y
- **Current Status**: Fetching page N, Processing items, Complete
- **Progress Bar**: Visual percentage complete
- **Time Estimate**: Calculated based on current speed

## Sync Behavior

### What Gets Synced?

**From AuralArchive to AudioBookShelf:**
- Title, author, narrator
- Series information
- Cover art
- File metadata
- File location

**From AudioBookShelf to AuralArchive:**
- Title, author, narrator
- Series information
- Progress/completion status
- Last played timestamp
- Cover art URL

### Conflict Resolution

When the same book exists in both systems:
- Metadata from Audible takes priority
- Cover art uses highest quality available

## Troubleshooting

### Connection Fails

**Problem:** Can't connect to AudioBookShelf

**Solutions:**
1. Verify AudioBookShelf is running: `docker ps`
2. Check URL format: `http://ip:13378` (not https unless configured)
3. Verify API token is valid
4. Test connectivity: `curl http://audiobookshelf-url`
5. Check firewall rules

### Sync Times Out

**Problem:** Sync fails with timeout for large libraries

**Solutions:**
1. Reduce `ABS_SYNC_PAGE_SIZE` to 250 or 100
2. Check network bandwidth between servers
3. Increase timeout in Settings → System → API Timeout
4. Monitor system resources during sync
5. Sync during low-usage periods

### Metadata Doesn't Update

**Problem:** Changes in AuralArchive don't appear in AudioBookShelf

**Solutions:**
1. Manually trigger scan in AudioBookShelf
2. Verify file permissions (PUID/PGID)
3. Check that files are in AudioBookShelf library path
4. Review AudioBookShelf logs for scanning errors
5. Force metadata refresh in AudioBookShelf

### Duplicate Entries

**Problem:** Same audiobook appears twice

**Solutions:**
1. Match audiobooks by ASIN in both systems
2. Delete duplicate in one system
3. Re-sync to merge entries
4. Check for different file formats (AAX vs M4B) creating duplicates

### Permission Errors

**Problem:** AudioBookShelf can't access files

**Solutions:**
1. Verify PUID/PGID matches in both containers
2. Check directory permissions: `ls -la audiobooks/`
3. Ensure both containers use same user
4. Restart both containers after permission changes

## Best Practices

### File Organization
- Use consistent naming in both systems
- Convert to M4B before adding to AudioBookShelf
- Organize by author/series for best AudioBookShelf experience

### Sync Schedule
- Enable auto-sync for hands-free operation
- Sync after bulk downloads
- Schedule syncs during low-usage hours for large libraries

### Performance
- Use appropriate page size for your library
- Monitor sync progress via real-time updates
- Keep both servers on same network for best speed

### Backup
- Backup AudioBookShelf metadata regularly
- Keep AuralArchive database backed up
- Both can be rebuilt, but progress tracking is valuable

## Next Steps

After configuring AudioBookShelf sync:
1. **[Manage Your Library](Library-Management)** - Organize your collection
2. **[Set Up Downloads](Downloads-and-Queue)** - Configure download workflows
3. **[Configure Metadata](Search-and-Metadata)** - Fine-tune metadata sources
