"""SQLite persistence. One short-lived connection per operation keeps this safe across worker threads."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    file_kind       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    stage           TEXT NOT NULL DEFAULT 'queued',
    progress_done   INTEGER NOT NULL DEFAULT 0,
    progress_total  INTEGER,
    page_count      INTEGER,
    empty_page_count INTEGER NOT NULL DEFAULT 0,
    char_count      INTEGER NOT NULL DEFAULT 0,
    word_count      INTEGER NOT NULL DEFAULT 0,
    error_code      TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text        TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    text        TEXT NOT NULL,
    context     TEXT NOT NULL DEFAULT '',
    embedding   BLOB
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id, ordinal);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('complete', 'stopped', 'error')),
    quality     TEXT,
    citations   TEXT NOT NULL DEFAULT '[]',
    trace       TEXT NOT NULL DEFAULT '[]',
    coverage    TEXT,
    error_message TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_document ON messages (document_id, id);

CREATE INDEX IF NOT EXISTS idx_documents_created ON documents (created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# Bump when the way chunks are built or searched changes. The search index is derived data that is
# rebuilt on a document's next question, so an old one is simply discarded.
INDEX_VERSION = 2


def init_db() -> None:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        stored_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if stored_version < INDEX_VERSION:
            connection.execute("DROP TABLE IF EXISTS chunks")
        connection.executescript(SCHEMA)
        connection.execute(f"PRAGMA user_version = {INDEX_VERSION}")
