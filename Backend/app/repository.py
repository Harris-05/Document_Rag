import sqlite3
from pathlib import Path

from app.config import get_settings
from app.db import connect, utc_now
from app.errors import ErrorCode
from app.extraction import ExtractionResult
from app.schemas import DocumentDetail, DocumentSummary, PageText

SUMMARY_COLUMNS = """
    id, filename, file_kind, size_bytes, status, stage, progress_done, progress_total,
    page_count, empty_page_count, word_count, error_code, error_message, created_at
"""


def _summary(row: sqlite3.Row) -> DocumentSummary:
    return DocumentSummary(**{key: row[key] for key in row.keys()})


def create_document(document_id: str, filename: str, file_kind: str, size_bytes: int) -> None:
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, filename, file_kind, size_bytes, status, stage, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'processing', 'queued', ?, ?)
            """,
            (document_id, filename, file_kind, size_bytes, now, now),
        )


def update_progress(document_id: str, stage: str, done: int, total: int | None) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE documents SET stage = ?, progress_done = ?, progress_total = ?, updated_at = ?
            WHERE id = ? AND status = 'processing'
            """,
            (stage, done, total, utc_now(), document_id),
        )


def mark_ready(document_id: str, kind: str, result: ExtractionResult) -> None:
    """Persist the extracted pages and flip the document to ready in a single transaction."""
    with connect() as connection:
        connection.executemany(
            "INSERT INTO pages (document_id, page_number, text) VALUES (?, ?, ?)",
            [(document_id, page.number, page.text) for page in result.pages],
        )
        connection.execute(
            """
            UPDATE documents SET
                status = 'ready', stage = 'done', progress_done = ?, progress_total = ?,
                page_count = ?, empty_page_count = ?, char_count = ?, word_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                len(result.pages),
                len(result.pages),
                len(result.pages) if kind == "pdf" else None,
                result.empty_page_count,
                result.char_count,
                result.word_count,
                utc_now(),
                document_id,
            ),
        )


def mark_failed(document_id: str, code: ErrorCode, message: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE documents SET status = 'failed', stage = 'failed', error_code = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (code.value, message, utc_now(), document_id),
        )


def fail_interrupted_jobs() -> int:
    """After a restart, any job still marked as processing was killed mid-way and can never finish."""
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE documents SET status = 'failed', stage = 'failed', error_code = ?, error_message = ?, updated_at = ?
            WHERE status = 'processing'
            """,
            (
                ErrorCode.INTERRUPTED.value,
                "Processing was interrupted by a server restart. Upload the file again.",
                utc_now(),
            ),
        )
        return cursor.rowcount


def list_documents() -> list[DocumentSummary]:
    """The library never shows failed uploads; those are reported to the uploader only."""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {SUMMARY_COLUMNS} FROM documents WHERE status != 'failed' ORDER BY created_at DESC"
        ).fetchall()
    return [_summary(row) for row in rows]


def get_summary(document_id: str) -> DocumentSummary | None:
    with connect() as connection:
        row = connection.execute(
            f"SELECT {SUMMARY_COLUMNS} FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    return _summary(row) if row else None


def get_detail(document_id: str) -> DocumentDetail | None:
    with connect() as connection:
        row = connection.execute(
            f"SELECT {SUMMARY_COLUMNS}, char_count FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return None
        pages = connection.execute(
            "SELECT page_number, text FROM pages WHERE document_id = ? ORDER BY page_number",
            (document_id,),
        ).fetchall()
    data = {key: row[key] for key in row.keys()}
    return DocumentDetail(**data, pages=[PageText(**dict(page)) for page in pages])


def delete_document(document_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        deleted = cursor.rowcount > 0
        # Removing the document unlinked it from its conversations. A conversation left with no
        # documents at all (its one-document chat, or a comparison of documents that are all gone)
        # has nothing to talk about, so it goes too. One that still has documents keeps its history.
        connection.execute(
            """
            DELETE FROM conversations
            WHERE NOT EXISTS (SELECT 1 FROM conversation_documents cd WHERE cd.conversation_id = conversations.id)
            """
        )
    stored_file_path(document_id).unlink(missing_ok=True)
    return deleted


def stored_file_path(document_id: str) -> Path:
    return get_settings().uploads_dir / document_id
