import uuid
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app import repository
from app.config import get_settings
from app.errors import DocumentError, ErrorCode
from app.extraction import detect_file_kind
from app.processing import process_document
from app.schemas import DocumentDetail, DocumentSummary

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
CHUNK_SIZE = 1024 * 1024


def _display_name(raw: str | None) -> str:
    name = PureWindowsPath(PurePosixPath(raw or "").name).name.strip()
    return name[:255] or "Untitled"


def _extension_kind(filename: str) -> str:
    suffix = PurePosixPath(filename.lower()).suffix
    kind = ALLOWED_EXTENSIONS.get(suffix)
    if kind is None:
        raise DocumentError(
            ErrorCode.UNSUPPORTED_TYPE,
            f"Only PDF and DOCX files can be uploaded. “{filename}” is not one of those.",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    return kind


async def _save_upload(upload: UploadFile, destination, max_bytes: int) -> int:
    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise DocumentError(
                        ErrorCode.FILE_TOO_LARGE,
                        f"This file is larger than the {max_bytes // (1024 * 1024)} MB limit.",
                        status.HTTP_413_CONTENT_TOO_LARGE,
                    )
                handle.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return size


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks) -> DocumentSummary:
    settings = get_settings()
    filename = _display_name(file.filename)
    expected_kind = _extension_kind(filename)

    document_id = uuid.uuid4().hex
    destination = repository.stored_file_path(document_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = await _save_upload(file, destination, settings.max_upload_bytes)

    if size == 0:
        destination.unlink(missing_ok=True)
        raise DocumentError(ErrorCode.EMPTY_FILE, "This file is empty (0 bytes).")

    actual_kind = detect_file_kind(destination)
    if actual_kind != expected_kind:
        destination.unlink(missing_ok=True)
        raise DocumentError(
            ErrorCode.UNSUPPORTED_TYPE,
            f"“{filename}” is not a valid {expected_kind.upper()} file. "
            "Only genuine PDF and DOCX files can be uploaded.",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    repository.create_document(document_id, filename, actual_kind, size)
    background_tasks.add_task(process_document, document_id, actual_kind)
    summary = repository.get_summary(document_id)
    assert summary is not None
    return summary


@router.get("", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return repository.list_documents()


@router.get("/{document_id}", response_model=DocumentSummary)
def get_document(document_id: str) -> DocumentSummary:
    summary = repository.get_summary(document_id)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return summary


@router.get("/{document_id}/text", response_model=DocumentDetail)
def get_document_text(document_id: str) -> DocumentDetail:
    detail = repository.get_detail(document_id)
    if detail is None or detail.status != "ready":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return detail


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> None:
    if not repository.delete_document(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")


MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{document_id}/file")
def get_original_file(document_id: str) -> FileResponse:
    """The uploaded file exactly as received, for the in-browser viewer. Served inline, not as a download."""
    summary = repository.get_summary(document_id)
    path = repository.stored_file_path(document_id)
    if summary is None or summary.status != "ready" or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[summary.file_kind],
        headers={"Content-Disposition": "inline", "Cache-Control": "private, max-age=3600"},
    )
