# Home

Welcome to **AuralArchive** - a comprehensive audiobook library management system that integrates with Audible, AudioBookShelf, and various indexers to help you build and manage your audiobook collection.

## What is AuralArchive?

AuralArchive is a self-hosted web application that serves as a central hub for:
- **Syncing** your Audible library and downloading audiobooks
- **Integrating** with AudioBookShelf for playback and library management
- **Searching** multiple indexers for copyright-free and open-source audiobooks
- **Managing** downloads through various download clients
- **Converting** audiobooks between formats (AAX to M4B, MP3, etc.)
- **Organizing** metadata, cover art, and file naming

## Quick Start

1. **[Installation](Installation)** - Set up AuralArchive using Docker or bare metal
2. **[First Time Setup](First-Time-Setup)** - Configure your instance and create admin account
3. **[Audible Integration](Audible-Integration)** - Connect your Audible account
4. **[AudioBookShelf Sync](AudioBookShelf-Sync)** - Sync with your AudioBookShelf server
5. **[Library Management](Library-Management)** - Browse and manage your collection

## Key Features

### Library Management
- Sync your entire Audible library
- Two-way sync with AudioBookShelf
- Browse by title, author, series, or narrator
- Advanced filtering and sorting
- Bulk operations (download, mark as read, etc.)

### Download Management
- Download audiobooks directly from Audible
- Search and download from multiple indexers
- Queue management with priority control
- Progress tracking and notifications
- Automatic conversion to preferred formats

### Metadata & Organization
- Automatic metadata fetching from Audnexus
- Cover art management and caching
- Flexible file naming templates
- Series tracking and organization
- Author and narrator management

### Integration
- **Audible**: Direct downloads with authentication
- **AudioBookShelf**: Two-way sync with progress tracking
- **Download Clients**: qBittorrent, Deluge, Transmission

## Documentation

- **[Installation](Installation)** - Docker and bare metal setup instructions
- **[First Time Setup](First-Time-Setup)** - Initial configuration guide
- **[Audible Integration](Audible-Integration)** - Connect and sync Audible library
- **[AudioBookShelf Sync](AudioBookShelf-Sync)** - Configure AudioBookShelf integration
- **[Library Management](Library-Management)** - Manage your audiobook collection
- **[Downloads and Queue](Downloads-and-Queue)** - Download management and conversion
- **[Search and Metadata](Search-and-Metadata)** - Search sources and metadata management
- **[Troubleshooting](Troubleshooting)** - Common issues and solutions

## System Requirements

- **Docker**: Recommended method (Docker 20.10+, Docker Compose 2.0+)
- **Python**: 3.11+ (for bare metal installation)
- **Storage**: Varies based on library size (plan for ~500MB per audiobook average)
- **RAM**: 2GB minimum, 4GB+ recommended for large libraries
- **CPU**: Modern multi-core processor recommended for conversions

## Getting Help

If you encounter issues:
1. Check the **[Troubleshooting](Troubleshooting)** page
2. Review application logs in the Settings page
3. Open an issue on GitHub with relevant log excerpts

## Contributing

Contributions are welcome! Please open an issue or pull request on the GitHub repository.

---

**Ready to get started?** Head to the **[Installation](Installation)** page to set up your instance.
