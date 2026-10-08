import logging

from app import repository
from app.config import get_settings
from app.errors import DocumentError, ErrorCode
from app.extraction import extract_text

logger = logging.getLogger(__name__)


def process_document(document_id: str, kind: str) -> None:
    """Background job: extract text, then either persist it or record exactly why it failed.

    A failed job removes the stored upload so nothing half-processed is left behind.
    """
    settings = get_settings()
    path = repository.stored_file_path(document_id)

    def on_progress(done: int, total: int | None) -> None:
        repository.update_progress(document_id, "extracting", done, total)

    try:
        repository.update_progress(document_id, "extracting", 0, None)
        result = extract_text(path, kind, on_progress, settings.min_text_chars)
        repository.update_progress(document_id, "saving", len(result.pages), len(result.pages))
        repository.mark_ready(document_id, kind, result)
    except DocumentError as error:
        repository.mark_failed(document_id, error.code, error.message)
        path.unlink(missing_ok=True)
    except Exception:
        logger.exception("Unexpected failure while processing document %s", document_id)
        repository.mark_failed(
            document_id,
            ErrorCode.INTERNAL,
            "Something went wrong while reading this file. Please try again.",
        )
        path.unlink(missing_ok=True)
