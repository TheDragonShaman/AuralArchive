# First Time Setup

After installing AuralArchive, you'll need to complete the initial setup process.

## Initial Configuration

### 1. Access the Setup Page

When you first access AuralArchive at `http://localhost:8765`, you'll be redirected to the setup page.

### 2. Create Admin Account

**Fields:**
- **Username**: Your admin username
- **Password**: Strong password (min 8 characters)
- **Confirm Password**: Re-enter password

Click **Create Account** to proceed.

### 3. Basic Configuration

After creating your account, configure the basic settings:

#### Application Settings
- **Application Name**: Display name for your instance
- **Library Path**: Path where audiobooks will be stored
- **Import Path**: Path for importing books downloaded from sources external to AuralArchive
#### Download Settings
- **Concurrent Downloads**: Number of simultaneous downloads (default: 3)
- **Download Path**: Where to save downloaded files
- **Temporary Path**: Working directory for conversions

## Optional Integrations

You can configure these integrations now or later from the Settings page:

### Audible Integration
See **[Audible Integration](Audible-Integration)** for detailed setup instructions.

### AudioBookShelf Integration
See **[AudioBookShelf Sync](AudioBookShelf-Sync)** for detailed setup instructions.

### Download Client Integration
Configure qBittorrent in Settings → Download Clients. (Deluge and Transmission support coming soon)

## Verifying Your Setup

### 1. Check System Status

System health monitoring is available through the backend API. The UI displays system status in the dashboard.

### 2. Test Download Client Connection

1. Go to **Settings** → **Download Clients**
2. Click **Test Connection** on your configured client
3. Verify the connection is successful

### 3. Review Application Logs

Logs are stored in the `/logs` directory (Docker) or `./logs` (bare metal).
You can view them using:
```bash
# Docker
docker compose logs -f

# Bare metal
tail -f logs/auralarchive_web.log
```

## Common Post-Setup Tasks

### Configure File Naming and Media Management

1. Go to **Settings** → **Media Management**
2. **Naming Template**: Choose from predefined templates:
   - Templates organize how files are structured in your library
   - Use the preview to see example filenames
3. **Path Configuration**:
   - Library Path: Where organized audiobooks are stored
   - Import Path: Staging area for manual imports  
   - Downloads Path: Where download clients save files
4. **Download Workflow**: Configure seeding, auto-import, retry settings
5. **Audible Direct Downloads**: Set format and quality for Audible titles

The Media Management tab combines file naming, path configuration, download workflow, and Audible download settings in one place.


## Troubleshooting Setup Issues

### Permission Errors

If you see permission errors:
1. Stop the container: `docker compose down`
2. Verify PUID/PGID in docker-compose.yml matches your user
3. Check directory ownership: `ls -la`
4. Restart: `docker compose up -d`

### Database Errors

If the database fails to initialize:
1. Check logs: `docker compose logs`
2. Ensure `/config` volume is writable
3. Remove corrupt database: `rm config/auralarchive.db`
4. Restart to recreate: `docker compose restart`

### Port Conflicts

If port 8765 is already in use:
1. Edit docker-compose.yml
2. Change `"8765:5000"` to `"8766:5000"` (or another port)
3. Restart: `docker compose up -d`
4. Access at `http://localhost:8766`

## Next Steps

Once setup is complete:
1. **[Connect Audible](Audible-Integration)** - Sync your Audible library
2. **[Configure AudioBookShelf](AudioBookShelf-Sync)** - Set up two-way sync
3. **[Explore Library Management](Library-Management)** - Browse and organize your collection
