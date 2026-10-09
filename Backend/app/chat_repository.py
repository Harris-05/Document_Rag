import json
from typing import Any

from app.db import connect, utc_now
from app.schemas import ChatMessage


def _row_to_message(row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        status=row["status"],
        quality=row["quality"],
        citations=json.loads(row["citations"]),
        trace=json.loads(row["trace"]),
        coverage=json.loads(row["coverage"]) if row["coverage"] else None,
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def list_messages(document_id: str) -> list[ChatMessage]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM messages WHERE document_id = ? ORDER BY id", (document_id,)
        ).fetchall()
    return [_row_to_message(row) for row in rows]


def add_user_message(document_id: str, content: str) -> int:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO messages (document_id, role, content, status, created_at) VALUES (?, 'user', ?, 'complete', ?)",
            (document_id, content, utc_now()),
        )
        return int(cursor.lastrowid)


def add_assistant_message(
    document_id: str,
    *,
    content: str,
    status: str,
    quality: str | None,
    citations: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    coverage: dict[str, Any] | None,
    error_message: str | None = None,
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages
                (document_id, role, content, status, quality, citations, trace, coverage, error_message, created_at)
            VALUES (?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                content,
                status,
                quality,
                json.dumps(citations),
                json.dumps(trace),
                json.dumps(coverage) if coverage else None,
                error_message,
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def recent_history(document_id: str, limit: int = 8) -> list[tuple[str, str]]:
    """Completed turns only, oldest first, so an interrupted answer never poisons later context."""
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT role, content FROM messages
            WHERE document_id = ? AND (role = 'user' OR status = 'complete')
            ORDER BY id DESC LIMIT ?
            """,
            (document_id, limit),
        ).fetchall()
    return [(row["role"], row["content"]) for row in reversed(rows)]


def clear_messages(document_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM messages WHERE document_id = ?", (document_id,))
