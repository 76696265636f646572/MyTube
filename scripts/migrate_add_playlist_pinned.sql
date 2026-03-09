-- Add `pinned` column to playlists for existing databases.
-- Run once if you created the DB before this column was added (e.g. with sqlite3):
--   sqlite3 /path/to/mytube.db < scripts/migrate_add_playlist_pinned.sql
-- SQLite has no BOOLEAN type; we use INTEGER 0/1.
ALTER TABLE playlists ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
