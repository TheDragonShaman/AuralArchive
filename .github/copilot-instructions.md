# Copilot Instructions for AuralArchive

## Final Review Directions
- Every file must include the standardized header block.
- Research each file before refactoring to preserve intent.
- Remove unused imports and dead code along the way.
- Clean up logging statements for consistency.
- Loggers need to follow the format: self.logger = get_module_logger("Service.Audible.CatalogCover")
- Remove any comments or text that implies AI authorship.
- Function-level comments are allowed when they explain behavior from the dev team’s perspective.
- Ask questions before making assumptions or major changes.
- Work one file at a time (including helper modules); verify the result before proceeding to the next file.
- Use the file services_logging_progress.md to track your progress. Only do one file at a time and mark it complete when done. 
- Ensure log statements are meaningful and consistent across the codebase. Avoid excessive or redundant logging.
- Use this format for the header block in each file:
```python

"""
Module Name: example_module.py
Author: TheDragonShaman
Created: 
Last Modified: 
Description:
    This module demonstrates the standard Python file header format.
    It includes metadata and a docstring at the top of the file to
    describe the purpose, usage, and important details of the script.

Location:
    /utils/example_module.py

"""

- Add this style of header block to each file that is an API.

Download Management API
=======================

REST API endpoints for download queue management and control.

IMPORTANT: Currently only qBittorrent is supported as a download client.
Additional torrent clients (Deluge, Transmission) will be added soon.

Endpoints:
- POST   /api/downloads/queue              - Add book to download queue
- GET    /api/downloads/queue              - Get all queue items
- GET    /api/downloads/queue/<id>         - Get specific download
- DELETE /api/downloads/queue/<id>         - Cancel/remove download
- POST   /api/downloads/queue/<id>/pause   - Pause download
- POST   /api/downloads/queue/<id>/resume  - Resume download
- POST   /api/downloads/queue/<id>/retry   - Retry failed download
- GET    /api/downloads/status             - Get service status
- GET    /api/downloads/statistics         - Get queue statistics
- POST   /api/downloads/service/start      - Start monitoring service
- POST   /api/downloads/service/stop       - Stop monitoring service
"""
# For progress tracking, refer to services_logging_progress.md