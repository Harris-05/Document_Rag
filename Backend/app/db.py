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

-- A conversation is a chat about one document ('single') or several ('multi').
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (kind IN ('single', 'multi')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_documents (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    PRIMARY KEY (conversation_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_documents_document ON conversation_documents (document_id);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('complete', 'stopped', 'error')),
    quality         TEXT,
    citations       TEXT NOT NULL DEFAULT '[]',
    trace           TEXT NOT NULL DEFAULT '[]',
    coverage        TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, id);

-- A comparison of two versions of a contract. The finished result is stored as JSON.
CREATE TABLE IF NOT EXISTS comparisons (
    id              TEXT PRIMARY KEY,
    old_document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    new_document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status          TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    stage           TEXT NOT NULL DEFAULT 'queued',
    progress_done   INTEGER NOT NULL DEFAULT 0,
    progress_total  INTEGER,
    error_code      TEXT,
    error_message   TEXT,
    result          TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comparisons_created ON comparisons (created_at DESC);

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


# Version 2 changed how chunks are built, so older search indexes are discarded and rebuilt on a
# document's next question. Version 3 moved chat messages from "per document" to "per conversation". Version 4 added
# version comparisons (new tables only, so nothing needs migrating).
SCHEMA_VERSION = 4


def _has_legacy_messages(connection: sqlite3.Connection) -> bool:
    return "document_id" in [row[1] for row in connection.execute("PRAGMA table_info(messages)")]


def _copy_legacy_messages(connection: sqlite3.Connection) -> None:
    """Each document that had chat history becomes a one-document conversation, history intact."""
    connection.execute(
        """
        INSERT INTO conversations (id, kind, created_at)
        SELECT 'doc-' || document_id, 'single', MIN(created_at) FROM messages_v2 GROUP BY document_id
        """
    )
    connection.execute(
        """
        INSERT INTO conversation_documents (conversation_id, document_id, position)
        SELECT 'doc-' || document_id, document_id, 0 FROM messages_v2 GROUP BY document_id
        """
    )
    connection.execute(
        """
        INSERT INTO messages (id, conversation_id, role, content, status, quality, citations, trace, coverage,
                              error_message, created_at)
        SELECT id, 'doc-' || document_id, role, content, status, quality, citations, trace, coverage,
               error_message, created_at
        FROM messages_v2
        """
    )
    connection.execute("DROP TABLE messages_v2")


def init_db() -> None:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        stored_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if stored_version < 2:
            connection.execute("DROP TABLE IF EXISTS chunks")

        legacy = stored_version < 3 and _has_legacy_messages(connection)
        if legacy:
            connection.execute("ALTER TABLE messages RENAME TO messages_v2")
            connection.execute("DROP INDEX IF EXISTS idx_messages_document")

        connection.executescript(SCHEMA)
        if legacy:
            _copy_legacy_messages(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
