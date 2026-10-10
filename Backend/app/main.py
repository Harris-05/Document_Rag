from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import comparison_repository, repository
from app.config import get_settings
from app.db import init_db
from app.errors import DocumentError
from app.routers import chat, comparisons, conversations, documents, export


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    repository.fail_interrupted_jobs()
    comparison_repository.fail_interrupted()
    yield


app = FastAPI(title="Marginalia API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(DocumentError)
async def document_error_handler(_: Request, error: DocumentError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code.value, "message": error.message},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(comparisons.router)
app.include_router(export.router)
