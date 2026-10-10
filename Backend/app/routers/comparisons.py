"""Comparing two versions of a contract: start a comparison, watch its progress, read the result."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app import comparison_repository, repository
from app.compare.engine import compare_documents
from app.config import Settings, get_settings
from app.dependencies import get_optional_llm
from app.errors import DocumentError, ErrorCode
from app.rag.llm import LLMClient
from app.schemas import ComparisonDetail, ComparisonSummary, CreateComparisonRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


async def run_comparison_job(comparison_id: str, old_id: str, new_id: str, llm: LLMClient | None, settings: Settings) -> None:
    """Background job. Reads both documents' text, compares them, and stores the result or the failure."""

    def progress(stage: str, done: int, total: int | None) -> None:
        comparison_repository.update_progress(comparison_id, stage, done, total)

    try:
        old, new = repository.get_detail(old_id), repository.get_detail(new_id)
        if old is None or new is None:
            comparison_repository.mark_failed(comparison_id, ErrorCode.DOCUMENT_NOT_READY, "One of the documents was removed before the comparison could finish.")
            return
        result = await compare_documents(
            [(p.page_number, p.text) for p in old.pages],
            [(p.page_number, p.text) for p in new.pages],
            llm,
            settings,
            progress,
        )
        comparison_repository.mark_ready(comparison_id, result)
    except Exception:
        logger.exception("Comparison %s failed", comparison_id)
        comparison_repository.mark_failed(comparison_id, ErrorCode.INTERNAL, "Something went wrong while comparing these documents. Please try again.")


def _ready(document_id: str):
    summary = repository.get_summary(document_id)
    if summary is None:
        raise DocumentError(ErrorCode.DOCUMENT_NOT_READY, "One of the selected documents no longer exists.", status.HTTP_404_NOT_FOUND)
    if summary.status != "ready":
        raise DocumentError(
            ErrorCode.DOCUMENT_NOT_READY,
            f"“{summary.filename}” is still being processed. Wait for it to finish and try again.",
        )
    return summary


@router.post("", response_model=ComparisonSummary, status_code=status.HTTP_202_ACCEPTED)
async def create_comparison(
    body: CreateComparisonRequest,
    background_tasks: BackgroundTasks,
    llm: LLMClient | None = Depends(get_optional_llm),
    settings: Settings = Depends(get_settings),
) -> ComparisonSummary:
    if body.old_document_id == body.new_document_id:
        raise DocumentError(ErrorCode.SAME_DOCUMENT, "Choose two different documents to compare.")
    _ready(body.old_document_id)
    _ready(body.new_document_id)

    existing = comparison_repository.find_reusable(body.old_document_id, body.new_document_id)
    if existing is not None:
        summary = comparison_repository.get_summary(existing)
        assert summary is not None
        return summary

    comparison_id = comparison_repository.create(body.old_document_id, body.new_document_id)
    background_tasks.add_task(run_comparison_job, comparison_id, body.old_document_id, body.new_document_id, llm, settings)
    summary = comparison_repository.get_summary(comparison_id)
    assert summary is not None
    return summary


@router.get("", response_model=list[ComparisonSummary])
def list_comparisons() -> list[ComparisonSummary]:
    return comparison_repository.list_summaries()


@router.get("/{comparison_id}", response_model=ComparisonDetail)
def get_comparison(comparison_id: str) -> ComparisonDetail:
    detail = comparison_repository.get_detail(comparison_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparison not found.")
    return detail


@router.delete("/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comparison(comparison_id: str) -> None:
    if not comparison_repository.delete(comparison_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparison not found.")
