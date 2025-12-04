# Download Integration Debug Summary

## Issue Overview
Implementing manual download functionality to add torrents from Jackett indexer to qBittorrent. The API returns success ("Ok.") but torrents don't appear in qBittorrent UI.

## System Architecture

### Components
1. **AuralArchive** - Flask web app running on host machine (172.19.0.1)
2. **Jackett** - Torznab indexer proxy running on host at `http://localhost:9117`
3. **qBittorrent** - Torrent client running in Docker container
   - Host: `172.19.0.1:8080`
   - Network mode: Likely bridge or host mode
   - Username: `peronabg`
   - Password: `01181236`

### Network Flow
```
User → AuralArchive → Jackett → Returns torrent URL
                    ↓
                qBittorrent (Docker) → Attempts to download from URL
```

## Technical Details

### qBittorrent API
- **Version**: Web API v2
- **Authentication**: Cookie-based (POST /api/v2/auth/login)
- **Add Torrent**: POST /api/v2/torrents/add
  - Supports: magnet links, HTTP URLs, torrent file upload
  - Uses multipart/form-data encoding
  - Parameters: `urls`, `category`, `paused`, `savepath`

### Current Implementation

**File**: `api/search_api.py` - `manual_download()` endpoint

**Flow**:
1. Extract download link from search result (magnet or URL)
2. Load qBittorrent config from `config/config.txt`
3. Replace `localhost` with host IP (172.19.0.1) for Docker compatibility
4. Initialize QBittorrentClient and connect
5. Call `add_torrent()` with download link

**qBittorrent Client**: `services/download_clients/qbittorrent_client.py`

**add_torrent() Method**:
```python
def add_torrent(torrent_data: str, ...):
    # Determines if torrent_data is:
    # 1. Magnet link (starts with 'magnet:')
    # 2. HTTP/HTTPS URL (starts with 'http://' or 'https://')
    # 3. Local file path
    
    if magnet or HTTP URL:
        data['urls'] = torrent_data
        files = {'_dummy': (None, '_dummy')}  # Force multipart/form-data
    else:
        # Read file and upload as multipart
        files = {'torrents': (filename, content, 'application/x-bittorrent')}
```

### Observed Behavior

**Logs show**:
```
2025-10-29 22:28:05 - qBittorrent request - URL: http://172.19.0.1:8080/api/v2/torrents/add
2025-10-29 22:28:05 - qBittorrent request - Data: {
    'paused': 'false',
    'category': 'auralarchive',
    'urls': 'http://localhost:9117/dl/audiobookbay/?jackett_apikey=XXX&path=...'
}
2025-10-29 22:28:05 - qBittorrent response - Status: 200, Text: 'Ok.'
2025-10-29 22:28:05 - Successfully added torrent to qBittorrent
```

**Results**:
- ✅ API returns HTTP 200 "Ok."
- ✅ Connection successful
- ✅ Authentication successful
- ❌ Torrent does NOT appear in qBittorrent UI
- ❌ No error messages in logs

## Root Cause Analysis

### Primary Issue: Docker Networking
qBittorrent is running inside a Docker container. When it receives a URL with `localhost:9117`, it tries to download from `localhost` **inside the container**, not the host machine where Jackett is running.

**Problem URL**:
```
http://localhost:9117/dl/audiobookbay/?jackett_apikey=XXX&path=...
```

**What qBittorrent sees**:
- `localhost` = the Docker container itself (not the host)
- Port 9117 is not exposed inside the container
- Download fails silently (qBittorrent may not log these errors to API responses)

### Fix Implemented
Replace `localhost` with host IP in download URLs:

```python
if 'localhost' in download_link or '127.0.0.1' in download_link:
    host_ip = config.get('qbittorrent', 'qb_host', fallback='172.19.0.1')
    download_link = download_link.replace('localhost', host_ip)
    download_link = download_link.replace('127.0.0.1', host_ip)
```

**Corrected URL**:
```
http://172.19.0.1:9117/dl/audiobookbay/?jackett_apikey=XXX&path=...
```

## Historical Context

### Old Implementation (August 2025 Backup)
The previous working implementation followed this pattern:

**File**: `services/download/service.py`
```python
def add_to_download_client(result: Dict, client_name: str = None):
    magnet_link = result.get('magnet', '')
    download_url = result.get('download_url', '')
    
    if magnet_link:
        return client_manager.add_torrent(magnet_link=magnet_link, ...)
    elif download_url:
        if download_url.endswith('.torrent'):
            return client_manager.add_torrent(torrent_url=download_url, ...)
```

**Key Pattern**: Pass URLs directly to qBittorrent - let it handle downloading

**File**: `services/download/clients/qbittorrent_client.py`
```python
def add_torrent(self, magnet_link: str = None, torrent_url: str = None, **kwargs):
    if magnet_link:
        data["urls"] = magnet_link
    elif torrent_url:
        data["urls"] = torrent_url
    
    response = self.session.post(url, data=data, timeout=30)
```

### Migration Changes
1. **Removed**: Pre-download logic (we tried downloading torrent files with `requests.get()`)
2. **Kept**: Direct URL pass-through to qBittorrent
3. **Added**: Localhost → host IP replacement for Docker compatibility

## Current Status

### What's Working
- ✅ Jackett search returns results
- ✅ qBittorrent API authentication
- ✅ qBittorrent API accepts requests (returns "Ok.")
- ✅ URL replacement logic implemented

### What's Not Working
- ❌ Torrents don't appear in qBittorrent UI
- ❌ Unknown if latest fix (localhost replacement) has been tested
- ❌ No verification that qBittorrent is actually downloading

### Potential Issues Still Outstanding

1. **Localhost replacement not tested yet**
   - Code was just updated
   - Need to test with new download attempt
   - Should see "Replaced localhost with host IP" in logs

2. **Docker network configuration**
   - qBittorrent container network mode unknown
   - May need to verify Docker networking setup
   - Host IP (172.19.0.1) may not be reachable from container

3. **Jackett URL accessibility**
   - Jackett may not be accessible at port 9117 from Docker
   - May need to check Jackett configuration
   - May need to verify firewall rules

4. **qBittorrent silent failures**
   - qBittorrent may fail to download without reporting errors
   - API returns "Ok." even if download fails later
   - Need to check qBittorrent logs inside container

5. **Category configuration**
   - Category "auralarchive" may not exist in qBittorrent
   - qBittorrent may reject torrents with invalid categories
   - Should verify category exists or create it

## Testing Plan

### Immediate Tests Needed

1. **Test localhost replacement**
   ```bash
   # Check logs after download attempt
   tail -50 logs/auralarchive_web.log | grep "Replaced localhost"
   ```

2. **Check qBittorrent container logs**
   ```bash
   sudo docker logs qbittorrent --tail 100 | grep -i "error\|download\|torrent"
   ```

3. **Verify network connectivity**
   ```bash
   # From inside qBittorrent container
   sudo docker exec qbittorrent curl -I http://172.19.0.1:9117
   ```

4. **Check categories**
   ```bash
   # List categories via API
   curl -X GET "http://172.19.0.1:8080/api/v2/torrents/categories" \
     --cookie "SID=YOUR_SESSION_ID"
   ```

5. **Manual test with known working magnet**
   ```python
   # Try adding a known-good magnet link
   download_link = "magnet:?xt=urn:btih:..."  # Public domain torrent
   ```

### Debug Steps

1. **Enable verbose logging**
   - Add more detailed logging in qbittorrent_client.py
   - Log full request/response details
   - Log Docker network configuration

2. **Test direct qBittorrent API**
   ```bash
   # Manually add torrent via curl to isolate issue
   curl -X POST "http://172.19.0.1:8080/api/v2/torrents/add" \
     -H "Cookie: SID=..." \
     -F "urls=http://172.19.0.1:9117/dl/..."
   ```

3. **Check Jackett from Docker**
   ```bash
   # Verify Jackett is accessible from container
   sudo docker exec qbittorrent wget -O- "http://172.19.0.1:9117" 2>&1 | head
   ```

## Configuration Files

### config/config.txt
```ini
[qbittorrent]
qb_host = 172.19.0.1
qb_port = 8080
qb_username = peronabg
qb_password = "01181236"
category = auralarchive
```

### Jackett Configuration
- Base URL: `http://localhost:9117`
- Indexer: audiobookbay
- API Key: `swevycr8r1d4ig2rortm0x63bj63em1z`

## Files Modified

1. **api/search_api.py** - Manual download endpoint
   - Removed torrent file pre-download logic
   - Added localhost → host IP replacement
   - Simplified to direct URL pass-through

2. **services/download_clients/qbittorrent_client.py** - qBittorrent API client
   - Already had correct implementation
   - Uses dummy file for multipart/form-data encoding
   - Handles magnet links and URLs

3. **services/indexers/jackett_indexer.py** - Jackett integration
   - Extracts magnet links from Torznab attributes
   - Returns both download_url and magnet_link fields

## Recommended Next Steps

1. **Test the latest fix** - Try downloading again to see if localhost replacement works
2. **Check qBittorrent logs** - Look for download errors in container logs
3. **Verify network connectivity** - Ensure Jackett is accessible from Docker container
4. **Test with magnet link** - Try a magnet link instead of HTTP URL to isolate issue
5. **Check qBittorrent categories** - Verify "auralarchive" category exists
6. **Manual API test** - Use curl to add torrent directly and compare behavior

---

## GPT-4 Prompt for Further Assistance

**Prompt**:

I'm implementing torrent download functionality in a Flask application that integrates Jackett (indexer) with qBittorrent (download client running in Docker). The qBittorrent API returns HTTP 200 "Ok." when adding torrents, but they don't appear in the UI.

**Setup**:
- Flask app on host (172.19.0.1)
- Jackett on host at localhost:9117
- qBittorrent in Docker container at 172.19.0.1:8080

**Current behavior**:
- API authentication: ✅ Successful
- Add torrent request: ✅ Returns "Ok."
- Torrent appears in UI: ❌ Failed

**Implementation**:
```python
# Add torrent with URL replacement for Docker
if 'localhost' in download_link:
    download_link = download_link.replace('localhost', '172.19.0.1')

qb_client.add_torrent(
    torrent_data=download_link,  # HTTP URL or magnet link
    category='auralarchive'
)
```

**qBittorrent client uses**:
- multipart/form-data with `data['urls'] = download_link`
- Dummy file to force multipart encoding
- Cookie-based authentication

**Jackett returns**:
```
http://localhost:9117/dl/audiobookbay/?jackett_apikey=XXX&path=...
```

**Questions**:
1. Why would qBittorrent return "Ok." but not add the torrent?
2. Is the localhost→host IP replacement sufficient for Docker networking?
3. Could qBittorrent be failing silently after accepting the request?
4. How can I verify the torrent download is actually being attempted?
5. What qBittorrent configuration might cause torrents to be accepted but not queued?

**Already tried**:
- ✅ Direct URL pass-through (not pre-downloading files)
- ✅ Localhost replacement for Docker compatibility
- ✅ Verified qBittorrent API responds correctly
- ✅ Compared with old working implementation

**Need help with**:
- Debugging why torrents aren't appearing despite "Ok." response
- Verifying Docker network connectivity from container to host
- Understanding qBittorrent's behavior when it accepts but doesn't queue torrents
- Best practices for Jackett→qBittorrent integration in Docker environments
