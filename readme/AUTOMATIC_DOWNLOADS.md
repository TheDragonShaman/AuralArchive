# Automatic Download Service

The automatic download service converts any library entry marked as **Wanted** into a fully
managed download pipeline item.

## How It Works

1. The `AutomaticDownloadService` scans the books table on a timed interval
   (default: every 120 seconds) for entries whose `status = 'Wanted'` and that
   are not already queued or blocked.
2. Eligible titles are queued through the `DownloadManagementService` so they
   can be searched, downloaded, converted (when needed), and imported just like
   manual downloads.
3. Search concurrency is limited by the download manager via the new
   `download_management.max_active_searches` setting (default: 2). This keeps
   the number of simultaneous indexer searches under control while allowing the
   existing `max_concurrent_downloads` limit to govern active transfers.
4. Users can temporarily exclude books from automation by clearing or removing
   queue entries; excluded IDs are persisted in `auto_search.skip_book_ids` and
   can be re-enabled later or overridden via the "force" endpoints.

## Configuration

Key settings live under the `[auto_search]` section in `config.txt`:

```ini
[auto_search]
auto_download_enabled = false
quality_threshold = 5
scan_interval_seconds = 120
max_batch_size = 2
skip_book_ids =
```

- **auto_download_enabled** – master toggle for the background service.
- **scan_interval_seconds** – delay between Wanted scans.
- **max_batch_size** – number of new books queued per cycle.
- **skip_book_ids** – comma-separated list of book IDs that should be ignored
  by automation (managed automatically by the settings UI/api).

Under `[download_management]`, the new `max_active_searches` option enforces the
"no more than two searches at a time" requirement.

## API Surface

All automatic-control endpoints live under `/api/search/automatic/*`:

- `GET /automatic/status` – runtime + metric snapshot.
- `POST /automatic/start|pause|resume|stop` – control flow.
- `GET/POST /automatic/config` – read/write the `[auto_search]` section.
- `GET /automatic/queue` – view pending Wanted books that are eligible for
  automation.
- `POST /automatic/force/<book_id>` – immediately queue a specific Wanted book.

Matching routes exist inside the Settings module (`/settings/api/search/*`) so
users can manage automation directly from the UI.

## Operational Notes

- The automatic service starts with the application but quietly idles unless
  `auto_download_enabled` is set to `true`.
- Queue additions respect the per-ASIN uniqueness check inside the download
  manager, so rerunning automation is safe.
- "Clear queue" and "Remove from queue" operations simply add the affected
  IDs to the skip list; removing them later or forcing a search will re-enable
  automation for those books.
