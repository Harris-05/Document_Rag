from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status

from app import chat_repository, conversation_repository
from app.export.content import build_content
from app.export.pdf import render_pdf
from app.export.word import render_docx

router = APIRouter(prefix="/api/messages", tags=["export"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{message_id}/export")
def export_answer(message_id: int, format: Literal["pdf", "docx"] = "pdf") -> Response:
    """Download one answer, with its quotes and whether each was verified, as a PDF or Word file."""
    found = chat_repository.get_message_with_question(message_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That answer was not found. It may have been deleted.")
    message, question, conversation_id = found
    if message.role != "assistant" or message.status == "error" or not message.content.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a finished or stopped answer can be exported.")

    conversation = conversation_repository.get(conversation_id)
    names = [d.filename for d in conversation.documents] if conversation else []
    content = build_content(message, question, names, multi=bool(conversation and conversation.kind == "multi"))
    data = render_pdf(content) if format == "pdf" else render_docx(content)

    filename = f"{content.filename_stem}.{format}"
    return Response(
        content=data,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )
