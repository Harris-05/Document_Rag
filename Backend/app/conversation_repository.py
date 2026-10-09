"""Conversations: a chat about one document ("single") or about several at once ("multi")."""

import uuid

from app.db import connect, utc_now
from app.schemas import Conversation, DocumentSummary

SINGLE_PREFIX = "doc-"

_SUMMARY_COLUMNS = """
    d.id, d.filename, d.file_kind, d.size_bytes, d.status, d.stage, d.progress_done, d.progress_total,
    d.page_count, d.empty_page_count, d.word_count, d.error_code, d.error_message, d.created_at
"""


def single_conversation_id(document_id: str) -> str:
    return f"{SINGLE_PREFIX}{document_id}"


def ensure_single(document_id: str) -> str:
    """The one-document conversation for a document, created the first time it is needed."""
    conversation_id = single_conversation_id(document_id)
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO conversations (id, kind, created_at) VALUES (?, 'single', ?)",
            (conversation_id, utc_now()),
        )
        connection.execute(
            "INSERT OR IGNORE INTO conversation_documents (conversation_id, document_id, position) VALUES (?, ?, 0)",
            (conversation_id, document_id),
        )
    return conversation_id


def create_multi(document_ids: list[str]) -> str:
    conversation_id = uuid.uuid4().hex
    with connect() as connection:
        connection.execute(
            "INSERT INTO conversations (id, kind, created_at) VALUES (?, 'multi', ?)", (conversation_id, utc_now())
        )
        connection.executemany(
            "INSERT INTO conversation_documents (conversation_id, document_id, position) VALUES (?, ?, ?)",
            [(conversation_id, document_id, position) for position, document_id in enumerate(document_ids)],
        )
    return conversation_id


def _documents(connection, conversation_id: str) -> list[DocumentSummary]:
    rows = connection.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS} FROM conversation_documents cd
        JOIN documents d ON d.id = cd.document_id
        WHERE cd.conversation_id = ? ORDER BY cd.position
        """,
        (conversation_id,),
    ).fetchall()
    return [DocumentSummary(**{key: row[key] for key in row.keys()}) for row in rows]


def get(conversation_id: str) -> Conversation | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT c.id, c.kind, c.created_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c WHERE c.id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        documents = _documents(connection, conversation_id)
    return Conversation(
        id=row["id"],
        kind=row["kind"],
        created_at=row["created_at"],
        message_count=row["message_count"],
        documents=documents,
    )


def list_multi() -> list[Conversation]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT c.id, c.kind, c.created_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c WHERE c.kind = 'multi' ORDER BY c.created_at DESC
            """
        ).fetchall()
        return [
            Conversation(
                id=row["id"],
                kind=row["kind"],
                created_at=row["created_at"],
                message_count=row["message_count"],
                documents=_documents(connection, row["id"]),
            )
            for row in rows
        ]


def delete(conversation_id: str) -> bool:
    with connect() as connection:
        return connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,)).rowcount > 0
