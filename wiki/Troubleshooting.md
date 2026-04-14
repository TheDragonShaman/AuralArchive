# Troubleshooting

Common issues and solutions for AuralArchive.

## Installation Issues

### Docker Container Won't Start

**Problem:** Container fails to start or exits immediately

**Check Logs:**
```bash
docker compose logs auralarchive
```

**Common Solutions:**

1. **Port Conflict:**
   - Change port in docker-compose.yml: `"8766:5000"`
   - Check what's using port: `sudo lsof -i :8765`

2. **Permission Issues:**
   - Verify PUID/PGID: `id -u` and `id -g`
   - Check volume permissions: `ls -la config/ downloads/`
   - Fix permissions: `sudo chown -R $USER:$USER config/ downloads/ import/`

3. **Volume Mount Errors:**
   - Ensure directories exist before starting
   - Use absolute paths in docker-compose.yml
   - Check SELinux context (add `:z` to volume mounts if needed)

### Database Errors on Startup

**Problem:** "Database initialization failed" or similar errors

**Solutions:**

1. **Corrupted Database:**
```bash
docker compose down
rm config/auralarchive.db
docker compose up -d
```

2. **Permission Issues:**
```bash
docker compose down
sudo chown -R 1000:1000 config/
docker compose up -d
```

3. **Locked Database:**
```bash
# Check for stale lock files
rm config/auralarchive.db-lock
docker compose restart
```

## Authentication Issues

### Audible Login Fails

**Problem:** Can't authenticate with Audible

**Solutions:**

1. **Use Correct Authentication Flow:**
   - Go to **Settings** → **Audible** tab
   - Click **Authenticate** button
   - Enter email and password in modal dialog
   - Complete OTP (one-time password) if prompted
   - Wait for success confirmation

2. **2FA Issues:**
   - Check email/SMS for OTP code
   - Enter code in the OTP modal when prompted
   - Don't close the modal until authentication completes

3. **Region/Marketplace:**
   - Verify correct marketplace selected
   - Use marketplace matching your account (US, UK, etc.)
   - Some books are region-locked

4. **Re-authentication:**
   - If authentication fails, click **Revoke** to clear old credentials
   - Try authenticating again
   - Check for typos in email/password

### AudioBookShelf Connection Fails

**Problem:** Can't connect to AudioBookShelf

**Solutions:**

1. **Verify AudioBookShelf is Running:**
```bash
docker ps | grep audiobookshelf
```

2. **Check URL Format:**
   - Use `http://` not `https://` (unless you configured SSL)
   - Include port: `http://localhost:13378`
   - For Docker: Use container name or IP

3. **Network Connectivity:**
   - Ping AudioBookShelf server
   - Check firewall rules
   - Ensure containers on same network

4. **API Token Issues:**
   - Regenerate token in AudioBookShelf
   - Verify token copied correctly (no extra spaces)
   - Check token hasn't expired

## Permission Errors

### Can't Write to Volumes (NAS/Docker)

**Problem:** "Permission denied" errors when downloading or importing

**Diagnosis:**
```bash
docker compose exec auralarchive ls -la /downloads
docker compose exec auralarchive touch /downloads/test.txt
```

**Solutions:**

1. **Fix PUID/PGID:**
   - Find your user ID: `id -u` and `id -g`
   - Update docker-compose.yml:
   ```yaml
   environment:
     - PUID=1026  # Your user ID
     - PGID=100   # Your group ID
   ```
   - Recreate container: `docker compose up -d --force-recreate`

2. **Fix Directory Permissions:**
```bash
sudo chown -R 1000:1000 config/ downloads/ import/
sudo chmod -R 755 config/ downloads/ import/
```

3. **NAS-Specific (Synology/TrueNAS):**
   - Set folder permissions in NAS UI
   - Add Docker user to file share permissions
   - Check SMB/NFS mount options

## Sync Issues

### Audible Sync Timeout

**Problem:** "Sync timed out" or hangs indefinitely

**Solutions:**

1. **Re-authenticate:**
   - Go to **Settings** → **Audible** tab
   - Click **Revoke** to clear credentials
   - Click **Authenticate** and login again

2. **Use Different Sync Method:**
   - Try **Quick Sync** (delta updates) instead of Full Sync
   - Or use **Refresh Library Cache** for just metadata

3. **Check Internet:**
   - Verify connection to audible.com
   - Check for ISP throttling
   - Try again later if Audible API is slow

### AudioBookShelf Sync Takes Forever

**Problem:** Sync with large library is extremely slow

**Solutions:**

1. **Reduce Page Size:**
   - Edit docker-compose.yml:
   ```yaml
   environment:
     - ABS_SYNC_PAGE_SIZE=250  # Reduce from 500
   ```
   - Restart: `docker compose up -d`

2. **Network Performance:**
   - Run containers on same host
   - Use wired connection instead of WiFi
   - Check for network congestion

3. **Monitor Progress:**
   - Watch real-time progress in UI
   - Check logs for errors: **Settings** → **Logs**
   - Be patient - large libraries take time

### Duplicate Audiobooks After Sync

**Problem:** Same audiobook appears multiple times

**Solutions:**

1. **Delete Duplicates:**
   - Go to Library page
   - Identify duplicate entries
   - Select and delete extra copies
   - Keep version with best metadata

2. **Prevent Future Duplicates:**
   - Ensure you're not syncing from multiple sources with same content
   - Verify ASIN/identifiers are correct

## Download Issues

### Download Fails Repeatedly

**Problem:** Downloads start but fail every time

**Solutions:**

1. **Audible Downloads:**
   - Re-authenticate with Audible in Settings → Audible
   - Check Audible library online - verify you own the book
   - Try different quality setting

2. **Download Client Downloads:**
   - Verify download client (qBittorrent) is running and accessible
   - Test connection in Settings → Download Clients
   - Check download client logs
   - Verify download has seeders available

3. **Disk Space:**
   - Check available space: `df -h`
   - Free up space or change download directory in Settings → Media Management

### Import Fails

**Problem:** Files won't import to library

**Solutions:**

1. **Verify Source File:**
   - Check file is complete and not corrupted
   - Play in VLC or media player to verify it works
   - Check file size matches expected

2. **Check File Format:**
   - Supported: M4B, M4A, MP3, FLAC, AAX
   - Verify file extension matches actual format

3. **Check Logs:**
   - View logs in `/logs` directory or `docker compose logs`
   - Look for specific error messages
   - Check for permission errors

4. **Path Configuration:**
   - Verify paths in Settings → Media Management
   - Ensure import directory is correct and writable

## Performance Issues

### Web UI is Slow

**Problem:** Pages load slowly or freeze

**Solutions:**

1. **Clear Browser Cache:**
   - Clear browser cache and reload page
   - Try incognito/private mode
   - Try different browser

2. **Reduce Library Display:**
   - Use filters to narrow results
   - Adjust card density slider for smaller thumbnails
   - Search for specific books instead of browsing all

3. **System Resources:**
   - Check CPU/RAM usage: `docker stats`
   - Increase Docker memory limit
   - Close other applications
   - Restart container: `docker compose restart`

### Downloads are Very Slow

**Problem:** Download speeds are much slower than expected

**Solutions:**

1. **Reduce Concurrent Downloads:**
   - Go to **Settings** → **Media Management**
   - Reduce "Max Concurrent Downloads" to 1-3

2. **Network Issues:**
   - Test internet speed
   - Check for bandwidth limits in download client
   - Try different time of day

3. **For Download Client:**
   - Check seeders/leechers ratio for downloads
   - Configure bandwidth limits in qBittorrent
   - Verify network connectivity to client

## Database Issues

### Database is Locked

**Problem:** "Database is locked" error

**Solutions:**

```bash
# Stop the container
docker compose down

# Remove lock file
rm config/auralarchive.db-lock

# Start container
docker compose up -d
```

### Database Corruption

**Problem:** "Database disk image is malformed"

**Solutions:**

1. **Backup and Recreate:**
```bash
# Backup old database
cp config/auralarchive.db config/auralarchive.db.backup

# Let AuralArchive recreate
rm config/auralarchive.db
docker compose restart

# Re-sync libraries from Audible/AudioBookShelf
```

2. **Restore from Backup:**
```bash
# If you have manual backups
cp config/backups/auralarchive.db.YYYYMMDD config/auralarchive.db
docker compose restart
```

## Logging and Diagnostics

### View Application Logs

Logs are stored in the `/logs` directory:

**Docker:**
```bash
# View live logs
docker compose logs -f auralarchive

# Last 100 lines
docker compose logs --tail=100 auralarchive

# Save to file
docker compose logs auralarchive > logs.txt
```

**Bare Metal:**
```bash
# View latest log
tail -f logs/auralarchive_web.log

# View older logs
cat logs/auralarchive_web.log.1
```

## Getting Help

If you can't resolve an issue:

1. **Check Documentation:**
   - Review relevant wiki pages
   - Search existing GitHub issues

2. **Gather Information:**
   - Application logs
   - Docker logs (if applicable)
   - Steps to reproduce
   - Expected vs. actual behavior

3. **Open GitHub Issue:**
   - Go to: https://github.com/TheDragonShaman/AuralArchive/issues
   - Include all gathered information
   - Use issue template if provided

4. **Community Support:**
   - Check Discord/forum if available
   - Search for similar issues
   - Provide detailed information

## Preventive Maintenance

### Regular Tasks

**Weekly:**
- Review error logs
- Clear completed downloads
- Check disk space

**Monthly:**
- Optimize database
- Clear image cache
- Update to latest version
- Backup database

**Quarterly:**
- Review and refresh metadata
- Clean up unused files
- Verify all integrations working
- Update Docker images

### Backup Strategy

**Manual Backup:**
```bash
# Backup entire config directory
tar -czf auralarchive-backup-$(date +%Y%m%d).tar.gz config/

# Or just database
cp config/auralarchive.db config/auralarchive.db.backup
```

**Restore from Backup:**
```bash
docker compose down
cp config/auralarchive.db.backup config/auralarchive.db
docker compose up -d
```

**Recommended Schedule:**
- Backup database weekly
- Keep at least 3 recent backups
- Store backups outside the container/workspace

---

**Still Having Issues?**

Open an issue on [GitHub](https://github.com/TheDragonShaman/AuralArchive/issues) with:
- Detailed description of the problem
- Steps to reproduce
- Error messages from logs
- Your environment (Docker/bare metal, OS, version)
