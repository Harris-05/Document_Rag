from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration. Every value can be overridden through the environment or Backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    data_dir: Path = BACKEND_ROOT / "data"
    max_upload_mb: int = 25
    # A document with fewer meaningful characters than this is treated as "no readable text".
    min_text_chars: int = 25
    cors_origins: str = "http://localhost:3000"

    # AI provider. Any OpenAI-compatible endpoint works. OPEN_AI_APIKEY is accepted as an alias.
    openai_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "OPEN_AI_APIKEY")
    )
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_timeout_seconds: float = 90.0

    # Short-term memory: how many earlier question/answer exchanges the assistant can see when it
    # reads a follow-up. 0 turns the memory off, so every question is treated as stand-alone.
    chat_memory_turns: int = Field(default=6, ge=0, le=20)
    # Earlier answers are shortened to this many characters before being shown to the model.
    chat_memory_chars: int = Field(default=800, ge=100, le=4000)

    # Sampling temperature per stage. Planning and answering benefit from some variety (varied search
    # wording, natural explanations); the judge should stay close to deterministic. Models that only
    # accept their default temperature are handled automatically.
    temperature_plan: float = Field(default=0.3, ge=0, le=2)
    temperature_judge: float = Field(default=0.1, ge=0, le=2)
    temperature_answer: float = Field(default=0.4, ge=0, le=2)

    # Agentic retrieval loop.
    max_retrieval_rounds: int = 3
    candidates_per_round: int = 14
    max_evidence_passages: int = 10
    # Neighbouring chunks added around each strongly relevant passage so a clause is read whole.
    neighbor_chunks: int = Field(default=1, ge=0, le=3)
    chunk_target_chars: int = 1100
    chunk_overlap_chars: int = 180

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "documents.db"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
