"""Conversations that span several documents ("compare these contracts")."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app import chat_repository, conversation_repository, repository
from app.chat_service import stream_chat
from app.config import Settings, get_settings
from app.dependencies import get_llm
from app.errors import DocumentError, ErrorCode
from app.rag.llm import LLMClient
from app.routers.chat import source_of
from app.schemas import ChatMessage, ChatRequest, Conversation, CreateConversationRequest

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _conversation(conversation_id: str) -> Conversation:
    conversation = conversation_repository.get(conversation_id)
    if conversation is None or conversation.kind != "multi":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return conversation


@router.post("", response_model=Conversation, status_code=status.HTTP_201_CREATED)
def create_conversation(body: CreateConversationRequest, settings: Settings = Depends(get_settings)) -> Conversation:
    if len(body.document_ids) > settings.max_documents_per_question:
        raise DocumentError(
            ErrorCode.TOO_MANY_DOCUMENTS,
            f"You can compare up to {settings.max_documents_per_question} documents at once. "
            f"{len(body.document_ids)} were selected.",
        )
    for document_id in body.document_ids:
        summary = repository.get_summary(document_id)
        if summary is None:
            raise DocumentError(
                ErrorCode.DOCUMENT_NOT_READY, "One of the selected documents no longer exists.", status.HTTP_404_NOT_FOUND
            )
        if summary.status != "ready":
            raise DocumentError(
                ErrorCode.DOCUMENT_NOT_READY,
                f"“{summary.filename}” is still being processed. Wait for it to finish and try again.",
            )
    conversation = conversation_repository.get(conversation_repository.create_multi(body.document_ids))
    assert conversation is not None
    return conversation


@router.get("", response_model=list[Conversation])
def list_conversations() -> list[Conversation]:
    return conversation_repository.list_multi()


@router.get("/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str) -> Conversation:
    return _conversation(conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[ChatMessage])
def list_messages(conversation_id: str) -> list[ChatMessage]:
    _conversation(conversation_id)
    return chat_repository.list_messages(conversation_id)


@router.post("/{conversation_id}/chat")
async def chat(
    conversation_id: str,
    body: ChatRequest,
    llm: LLMClient = Depends(get_llm),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    conversation = _conversation(conversation_id)
    if body.mode == "research" and conversation.kind == "multi":
        raise HTTPException(
            422, "Research mode works on one document at a time."
        )
    details = [repository.get_detail(d.id) for d in conversation.documents if d.status == "ready"]
    documents = [source_of(detail) for detail in details if detail is not None]
    if not documents:
        raise DocumentError(
            ErrorCode.DOCUMENT_NOT_READY, "None of this conversation's documents are available any more.", status.HTTP_404_NOT_FOUND
        )
    return StreamingResponse(
        stream_chat(
            conversation_id=conversation_id,
            question=body.question,
            documents=documents,
            llm=llm,
            settings=settings,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str) -> None:
    _conversation(conversation_id)
    conversation_repository.delete(conversation_id)
