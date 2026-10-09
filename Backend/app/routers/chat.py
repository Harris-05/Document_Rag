from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app import chat_repository, repository
from app.chat_service import stream_chat
from app.config import Settings, get_settings
from app.dependencies import get_llm
from app.rag.llm import LLMClient
from app.schemas import ChatMessage, ChatRequest

router = APIRouter(prefix="/api/documents/{document_id}", tags=["chat"])


def _ready_document(document_id: str):
    detail = repository.get_detail(document_id)
    if detail is None or detail.status != "ready":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return detail


@router.get("/messages", response_model=list[ChatMessage])
def list_messages(document_id: str) -> list[ChatMessage]:
    _ready_document(document_id)
    return chat_repository.list_messages(document_id)


@router.post("/chat")
async def chat(
    document_id: str,
    body: ChatRequest,
    llm: LLMClient = Depends(get_llm),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    document = _ready_document(document_id)
    pages = [(page.page_number, page.text) for page in document.pages]
    return StreamingResponse(
        stream_chat(document_id=document_id, question=body.question, pages=pages, llm=llm, settings=settings),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
