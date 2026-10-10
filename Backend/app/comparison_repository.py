"""Storage for comparisons of two versions of a contract."""

import json
import uuid
from typing import Any

from app.db import connect, utc_now
from app.errors import ErrorCode
from app.schemas import ComparisonDetail, ComparisonSummary, DocumentBrief

_ROW = """
    c.id, c.status, c.stage, c.progress_done, c.progress_total, c.error_code, c.error_message, c.created_at, c.result,
    o.id AS old_id, o.filename AS old_name, o.file_kind AS old_kind, o.page_count AS old_pages,
    n.id AS new_id, n.filename AS new_name, n.file_kind AS new_kind, n.page_count AS new_pages
"""
_FROM = """
    FROM comparisons c
    JOIN documents o ON o.id = c.old_document_id
    JOIN documents n ON n.id = c.new_document_id
"""


def _summary_fields(row) -> dict[str, Any]:
    result = json.loads(row["result"]) if row["result"] else None
    return {
        "id": row["id"],
        "old_document": DocumentBrief(
            id=row["old_id"], filename=row["old_name"], file_kind=row["old_kind"], page_count=row["old_pages"]
        ),
        "new_document": DocumentBrief(
            id=row["new_id"], filename=row["new_name"], file_kind=row["new_kind"], page_count=row["new_pages"]
        ),
        "status": row["status"],
        "stage": row["stage"],
        "progress_done": row["progress_done"],
        "progress_total": row["progress_total"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "stats": result["stats"] if result else None,
        "ai_used": result["ai_used"] if result else None,
    }


def create(old_document_id: str, new_document_id: str) -> str:
    comparison_id = uuid.uuid4().hex
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO comparisons (id, old_document_id, new_document_id, status, stage, created_at, updated_at)
            VALUES (?, ?, ?, 'processing', 'queued', ?, ?)
            """,
            (comparison_id, old_document_id, new_document_id, now, now),
        )
    return comparison_id


def find_reusable(old_document_id: str, new_document_id: str) -> str | None:
    """A finished or running comparison of the same two documents in the same order, if there is one."""
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM comparisons
            WHERE old_document_id = ? AND new_document_id = ? AND status IN ('ready', 'processing')
            ORDER BY created_at DESC LIMIT 1
            """,
            (old_document_id, new_document_id),
        ).fetchone()
    return row["id"] if row else None


def update_progress(comparison_id: str, stage: str, done: int, total: int | None) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE comparisons SET stage = ?, progress_done = ?, progress_total = ?, updated_at = ? "
            "WHERE id = ? AND status = 'processing'",
            (stage, done, total, utc_now(), comparison_id),
        )


def mark_ready(comparison_id: str, result: dict[str, Any]) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE comparisons SET status = 'ready', stage = 'done', result = ?, updated_at = ? WHERE id = ?",
            (json.dumps(result), utc_now(), comparison_id),
        )


def mark_failed(comparison_id: str, code: ErrorCode, message: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE comparisons SET status = 'failed', stage = 'failed', error_code = ?, error_message = ?, "
            "updated_at = ? WHERE id = ?",
            (code.value, message, utc_now(), comparison_id),
        )


def fail_interrupted() -> int:
    """After a restart a comparison still marked as processing was killed mid-way and cannot finish."""
    with connect() as connection:
        return connection.execute(
            "UPDATE comparisons SET status = 'failed', stage = 'failed', error_code = ?, error_message = ?, "
            "updated_at = ? WHERE status = 'processing'",
            (
                ErrorCode.INTERRUPTED.value,
                "The comparison was interrupted by a server restart. Run it again.",
                utc_now(),
            ),
        ).rowcount


def get_summary(comparison_id: str) -> ComparisonSummary | None:
    with connect() as connection:
        row = connection.execute(f"SELECT {_ROW} {_FROM} WHERE c.id = ?", (comparison_id,)).fetchone()
    return ComparisonSummary(**_summary_fields(row)) if row else None


def get_detail(comparison_id: str) -> ComparisonDetail | None:
    with connect() as connection:
        row = connection.execute(f"SELECT {_ROW} {_FROM} WHERE c.id = ?", (comparison_id,)).fetchone()
    if row is None:
        return None
    fields = _summary_fields(row)
    result = json.loads(row["result"]) if row["result"] else {}
    return ComparisonDetail(
        **fields,
        summary=result.get("summary"),
        ai_notice=result.get("ai_notice"),
        changes=result.get("changes", []),
    )


def list_summaries() -> list[ComparisonSummary]:
    """Failed attempts are not listed, like failed uploads: the person who started one saw the error."""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_ROW} {_FROM} WHERE c.status != 'failed' ORDER BY c.created_at DESC"
        ).fetchall()
    return [ComparisonSummary(**_summary_fields(row)) for row in rows]


def delete(comparison_id: str) -> bool:
    with connect() as connection:
        return connection.execute("DELETE FROM comparisons WHERE id = ?", (comparison_id,)).rowcount > 0
