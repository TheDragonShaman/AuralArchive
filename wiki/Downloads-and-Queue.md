# Downloads and Queue

Manage audiobook downloads, conversions, and download queue in AuralArchive.

## Download Sources

AuralArchive supports multiple download sources:

### Audible Downloads
- Direct downloads from your Audible library
- Quality options: High (128kbps) or Standard (64kbps)
- Encrypted AAX format (requires conversion/activation bytes)

### Download Client Downloads
- Requires configured download client (currently qBittorrent)
- Supports copyright-free and open-source audiobooks
- Typically unencrypted M4B or MP3 format

## Download Queue

The **Downloads** page provides real-time monitoring of your download pipeline.

### Dashboard Overview

The Downloads dashboard shows:
- **Active Queue**: Items currently in-flight
- **Downloading**: Client transfers in progress
- **Converting**: Audible post-processing
- **Seeding**: Downloads currently seeding

### Queue Statuses

Your downloads progress through various states:

**Search & Setup:**
- **QUEUED** - Waiting for download pipeline slot
- **SEARCHING** - Locating the best source
- **FOUND** - Preparing the client to start downloading

**Downloading:**
- **DOWNLOADING** - Transfer in progress via client
- **AUDIBLE_DOWNLOADING** - Fetching directly from Audible
- **DOWNLOAD_COMPLETE** - Download complete, waiting on next stage
- **PAUSED** - Temporarily stopped

**Processing:**
- **CONVERTING** - Transcoding Audible media to library format
- **CONVERTED** - Conversion finished, ready to import
- **IMPORTING** - Moving to library
- **IMPORTED** - Complete and in library
- **SEEDING** - Torrent seeding (if enabled)
- **SEEDING_COMPLETE** - Seeding finished

**Failed States:**
- **SEARCH_FAILED** - No suitable source found (can retry)
- **DOWNLOAD_FAILED** - Download failed (can retry with different source)
- **AUDIBLE_DOWNLOAD_FAILED** - Audible transfer failed (will retry if allowed)
- **CONVERSION_FAILED** - Conversion error (can retry)
- **IMPORT_FAILED** - Import error (can retry)
- **CANCELLED** - User cancelled

## Download Client Configuration

### qBittorrent (Currently Supported)

1. Go to **Settings** → **Download Clients**
2. Click **Add** to create a new client
3. Select **qBittorrent** from the dropdown
4. Enter configuration:
   - **Host**: IP or hostname (e.g., `127.0.0.1`)
   - **Port**: Web UI port (default: `8080`)
   - **Username**: Your qBittorrent web UI username
   - **Password**: Your qBittorrent web UI password
   - **Category**: Optional category for organization (e.g., `auralarchive`)
5. **Path Mappings** (if needed): Map qBittorrent's internal paths to paths accessible by AuralArchive
6. Click **Test Connection** to verify
7. Click **Save Client**

**Note**: Deluge and Transmission support is currently in development and not yet available.

## Media Management Settings

Configure download workflow and Audible direct download settings in **Settings** → **Media Management**.

### Download Workflow

**Seeding and Cleanup:**
- **Enable Seeding**: Keep downloads seeding in client after completion
- **Delete Source After Import**: Remove source files after importing to library
- **Overwrite Existing**: Replace existing library files during import

**Queue Management:**
- **Max Concurrent Downloads**: Limit simultaneous active downloads (1-10)
- **Default Queue Priority**: Set default priority for new downloads (0-10)
- **Polling Interval**: How often to check download status (seconds)

**Automatic Monitoring:**
- **Auto Start Monitoring**: Automatically monitor new downloads
- **Monitor Seeding Downloads**: Continue monitoring while seeding

**Retry Settings:**
- **Search Retry Attempts**: How many times to retry failed searches
- **Download Retry Attempts**: How many times to retry failed downloads
- **Conversion Retry Attempts**: How many times to retry failed conversions
- **Import Retry Attempts**: How many times to retry failed imports
- **Retry Backoff**: Minutes to wait between retry attempts

### Audible Direct Downloads

Configure settings for downloading owned Audible titles:
- **Default Format**: Choose output format for Audible downloads
- **Quality Settings**: Configure bitrate and audio quality
- **Activation Bytes**: Required for decrypting Audible AAX files
- **Safety Options**: Configure download behavior and validation

## Monitoring Downloads

### Real-Time Updates

The Downloads page automatically updates using WebSocket connections:
- Live progress for active downloads
- Status changes appear instantly
- No manual refresh needed
- Polling interval displayed at top (typically 2 seconds)

### Download Information

For each active download, you can see:
- **Title** and **Author**
- **Current Status** with icon and description
- **Progress Bar** - Visual percentage complete
- **Download Speed** - Current transfer rate (KB/s or MB/s)
- **ETA** - Estimated time remaining
- **Size Information** - Downloaded vs total size
- **Indexer/Source** - Where the download came from

### Recently Imported

The sidebar shows:
- Latest 5 completed imports
- Recent seeding activity
- Quick access to completed items

### Queue Management Actions

**Clear Queue:**
- Button to clear all completed items from the queue
- Removes finished downloads from the active view

**Refresh:**
- Manual refresh button to reload queue status
- Useful if WebSocket connection is interrupted

**View Tabs:**
- **Downloads** - Active downloads and pending items
- **Seeding** - Items currently seeding (torrents only)

## Troubleshooting

### Download Fails

**Problem:** Download starts but fails

**Solutions:**
1. Check internet connection
2. Verify Audible authentication (for Audible downloads)
3. Check download client connection (for client downloads)
4. Review error message in Downloads page
5. Try manual retry
6. Check disk space

### Slow Downloads

**Problem:** Downloads are very slow

**Solutions:**
1. Check internet speed
2. Reduce concurrent downloads in Settings → Media Management
3. For client downloads: Check seeders/leechers ratio
4. Verify no bandwidth limits set in download client
5. Check network congestion
6. Try different time of day

### Import Fails

**Problem:** Import to library errors occur

**Solutions:**
1. Verify source file is complete and not corrupted
2. Check available disk space
3. Verify library path is writable
4. Check Media Management settings for path configuration
5. Review logs in `/logs` directory
6. Verify file naming template is valid

### Download Client Connection Issues

**Problem:** Can't connect to download client

**Solutions:**
1. Verify download client (qBittorrent) is running
2. Check host and port are correct in Settings → Download Clients
3. Verify credentials (username/password)
4. Check firewall rules
5. For Docker: ensure containers can communicate (use host networking or Docker network)
6. Use **Test Connection** button in download client settings
7. Check path mappings if client is on different machine/container

### Queue Stuck

**Problem:** Downloads not progressing

**Solutions:**
1. Check if paused: Click **Resume All**
2. Verify concurrent download limit isn't 0
3. Check for errors in individual items
4. Clear and re-add items to queue
5. Restart application if necessary

## Best Practices

### Queue Management
- Monitor the Downloads page for real-time status
- Use Clear Queue to remove completed items regularly
- Check failed items and retry if needed
- Review retry settings in Media Management

### Storage
- Configure auto-delete source files after import in Media Management
- Monitor disk space regularly
- Set appropriate path mappings for download clients

### Performance
- Adjust max concurrent downloads based on your system resources
- Configure appropriate retry backoff times
- Use the polling interval setting to balance performance vs real-time updates
- Enable seeding only if you have bandwidth to spare

### Troubleshooting
- Check the Downloads page for specific error messages
- Review logs in `/logs` directory for detailed errors
- Verify download client is running and accessible
- Ensure paths are correctly configured in Media Management

## Next Steps

Learn about finding and managing audiobook metadata:
1. **[Search and Metadata](Search-and-Metadata)**
2. **[Troubleshooting](Troubleshooting)**
