-- Migration: Add DownloadIntents table for intent-based download tracking
-- This table tracks download intentions from search to completion

CREATE TABLE IF NOT EXISTS DownloadIntents (
    intent_id TEXT PRIMARY KEY,
    asin TEXT,
    title TEXT NOT NULL,
    author TEXT,
    narrator TEXT,
    expected_duration_sec INTEGER,
    source TEXT,
    magnet_uri TEXT,
    torrent_url TEXT,
    infohash TEXT,
    client_torrent_id TEXT,
    save_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'queued' CHECK (status IN ('queued', 'downloading', 'downloaded', 'organized', 'completed', 'needs_review', 'failed')),
    notes TEXT
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_download_intents_asin ON DownloadIntents(asin);
CREATE INDEX IF NOT EXISTS idx_download_intents_status ON DownloadIntents(status);
CREATE INDEX IF NOT EXISTS idx_download_intents_created_at ON DownloadIntents(created_at);
CREATE INDEX IF NOT EXISTS idx_download_intents_infohash ON DownloadIntents(infohash);
