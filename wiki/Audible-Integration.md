# Audible Integration

Connect your Audible account to AuralArchive to sync your library and download audiobooks.

## Prerequisites

- Active Audible account
- Valid Audible credentials
- Chrome or Chromium browser (for authentication)

## Authentication Process

AuralArchive uses a secure modal-based authentication flow:

### How It Works

1. Go to **Settings** → **Audible**
2. Click **Authenticate**
3. A dialog appears asking for:
   - **Email**: Your Audible account email
   - **Password**: Your Audible password
   - **Marketplace**: Select your region (US, UK, CA, AU, DE, FR, IT, ES)
4. Click **Continue**
5. **If you have 2FA enabled** (recommended):
   - A second dialog will appear asking for your OTP code
   - Check your authenticator app or SMS
   - Enter the 6-digit code
   - Click **Verify**
6. **Success!**
   - Your credentials are exchanged for a device token
   - The token is stored securely
   - Your password is **never** stored
7. You'll see a success message confirming authentication

### Important Notes

- **Your password is not stored** - only the device token is saved
- **2FA is strongly recommended** for better security
- **Select the correct marketplace** matching your Audible account region
- The authentication uses the official Audible API library

## Library Management

Once authenticated, your Audible library is automatically cached.

### Viewing Your Library

1. Go to **Library** page
2. Your Audible audiobooks appear automatically
3. Filter by source to show only Audible titles

### Refreshing Library Cache

Update your library cache with new purchases:

1. Go to **Settings** → **Audible**
2. Click **Refresh Library Cache**
3. Wait for the cache to update
4. New titles will appear in your library

### Metadata Sync

Enrich your library with detailed metadata:

**Quick Sync** - Update recently added or modified books:
1. Go to **Settings** → **Audible**
2. Click **Quick Sync**
3. Background process enriches recent additions

**Full Sync** - Refresh metadata for entire library:
1. Go to **Settings** → **Audible**
2. Click **Full Sync**
3. Background process updates all books (may take time for large libraries)

### Bulk Download Entire Library

Download all your Audible audiobooks at once:

1. Go to **Settings** → **Audible**
2. Configure download preferences:
   - **Format**: AAXC (recommended) or AAX
   - **Quality**: Best, High, or Normal
   - **Include PDF**: Companion PDFs if available
   - **Include Cover**: Download cover art
   - **Include Chapters**: Chapter information
   - **Concurrent Downloads**: How many simultaneous downloads (1-5)
3. Click **Download Entire Library**
4. Monitor progress in **Downloads** page

## Downloading Audiobooks

### Single Download

1. Go to **Library** page
2. Find the audiobook you want
3. Click the **Download** button
4. Select quality:
   - **High Quality** - Best quality, larger files
   - **Standard Quality** - Good quality, smaller files
5. Monitor progress in **Downloads** page

### Bulk Download

Download multiple audiobooks at once:

1. Go to **Library** page
2. Select audiobooks using checkboxes
3. Click **Bulk Actions** → **Download Selected**
4. Confirm download
5. Monitor progress in **Downloads** page

## Download Quality Options

| Quality | Bitrate | Format | File Size (per hour) |
|---------|---------|--------|---------------------|
| High | 128 kbps | AAX | ~55 MB |
| Standard | 64 kbps | AAX | ~28 MB |

**Note:** AAX files are encrypted and require conversion to play in most applications.

## Managing Downloaded Files

### Conversion

Downloaded AAX files can be automatically converted:

1. Go to **Settings** → **Conversion**
2. Enable **Auto-convert after download**
3. Select output format:
   - **M4B** - Recommended for audiobooks (chapter support)
   - **MP3** - Universal compatibility
   - **FLAC** - Lossless quality (large files)
4. Set qualiCache Won't Refresh

**Problem:** New purchases don't appear in library

**Solutions:**
1. Check authentication status: **Settings** → **Audible**
2. Re-authenticate if needed
3. Click **Refresh Library Cache** in Settings → Audible
4. Check internet connection
5. Review logs: **Settings** → **Logs**
6. Verify purchases appear in your Audible account onlinversion**
4. Set destination folder

## Troubleshooting

### Authentication Fails

**Problem:** Can't authenticate with Audible

**Solutions:**
1. Clear browser cache and cookies
2. Try a different browser
3. Disable VPN/proxy
4. Check Audible account status
5. Verify correct marketplace is selected

### Library Won't Sync

**Problem:** Sync fails or times out

**Solutions:**
1. Check authentication status: **Settings** → **Audible Integration**
2. Re-authenticate if needed
3. Check internet connection
4. Review logs: **Settings** → **Logs**
5. Try manual sync from Library page

### Download Fails

**Problem:** Downloads fail or are incomplete

**Solutions:**
1. Verify authentication is still valid
2. Check disk space availability
3. Ensure download directory is writable
4. Review error in Downloads page
5. Try downloading again
6. Download not possible due to ownership permissions

### Region/Marketplace Issues

**Problem:** Wrong books appear or books are missing

**Solutions:**
1. Verify correct marketplace in settings
2. Re-authenticate with correct marketplace
3. Some books are region-specific and won't appear in other marketplaces


## Next Steps

After setting up Audible integration:
1. **[Configure AudioBookShelf](AudioBookShelf-Sync)** - Set up playback server
2. **[Manage Downloads](Downloads-and-Queue)** - Learn about download management
3. **[Explore Library Features](Library-Management)** - Organize your collection
