from app.config import get_settings
from app.errors import DocumentError, ErrorCode
from app.rag.llm import LLMClient, LLMError, build_llm_client


def get_llm() -> LLMClient:
    """FastAPI dependency. Tests override it with a scripted fake."""
    try:
        return build_llm_client(get_settings())
    except LLMError as error:
        raise DocumentError(ErrorCode.AI_NOT_CONFIGURED, error.message, status_code=503) from error
