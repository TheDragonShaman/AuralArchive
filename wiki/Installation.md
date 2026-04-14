# Installation

AuralArchive can be installed using Docker (recommended) or as a bare metal Python application.

## Docker Installation (Recommended)

### Prerequisites
- Docker 20.10 or higher
- Docker Compose 2.0 or higher
- Sufficient storage for your audiobook library

### Quick Start

1. **Create a directory for AuralArchive:**
```bash
mkdir -p ~/auralarchive
cd ~/auralarchive
```

2. **Create a `docker-compose.yml` file:**
```yaml
version: '3.8'

services:
  auralarchive:
    image: ghcr.io/thedragonshaman/auralarchive:latest
    container_name: auralarchive
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
    ports:
      - "8765:5000"
    volumes:
      - ./config:/config
      - ./downloads:/downloads
      - ./import:/import
    restart: unless-stopped
```

3. **Set your PUID and PGID:**

Find your user ID and group ID:
```bash
id -u  # Your PUID
id -g  # Your PGID
```

Update the `PUID` and `PGID` values in `docker-compose.yml`.

4. **Start the container:**
```bash
docker compose up -d
```

5. **Access AuralArchive:**
Open your browser to `http://localhost:8765`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `UTC` | Timezone (e.g., `America/New_York`) |
| `ABS_SYNC_PAGE_SIZE` | `500` | Items per page for AudioBookShelf sync |

### Volume Mounts

| Path | Description |
|------|-------------|
| `/config` | Configuration files, database, and logs |
| `/downloads` | Downloaded audiobooks and conversions |
| `/import` | Import directory for existing audiobooks |

## Bare Metal Installation

### Prerequisites
- Python 3.11 or higher
- pip package manager
- Git (for cloning the repository)

### Installation Steps

1. **Clone the repository:**
```bash
git clone https://github.com/TheDragonShaman/AuralArchive.git
cd AuralArchive
```

2. **Create a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Create required directories:**
```bash
mkdir -p config downloads import logs
```

5. **Run the application:**
```bash
python app.py
```

6. **Access AuralArchive:**
Open your browser to `http://localhost:8765`

## NAS Installation (Synology, TrueNAS, Unraid)

When running on a NAS system, proper PUID/PGID configuration is critical for file permissions.

### Finding Your PUID and PGID

**On Synology:**
```bash
id your_username
```

**On TrueNAS:**
```bash
id your_username
```

**On Unraid:**
- PUID: `99` (default nobody user)
- PGID: `100` (default users group)

### Example docker-compose.yml for NAS

```yaml
version: '3.8'

services:
  auralarchive:
    image: ghcr.io/thedragonshaman/auralarchive:latest
    container_name: auralarchive
    environment:
      - PUID=1026  # Your NAS user ID
      - PGID=100   # Your NAS group ID
      - TZ=America/New_York
    ports:
      - "8765:5000"
    volumes:
      - /volume1/docker/auralarchive/config:/config
      - /volume1/audiobooks:/downloads
      - /volume1/audiobooks/import:/import
    restart: unless-stopped
```

## Updating

### Docker Update
```bash
cd ~/auralarchive
docker compose pull
docker compose up -d
```

### Bare Metal Update
```bash
cd AuralArchive
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

## Next Steps

After installation, proceed to **[First Time Setup](First-Time-Setup)** to configure your instance.
