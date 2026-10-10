"""Configuration comes from the environment or Backend/.env, not from values fixed in the code."""

from pathlib import Path

from app.config import Settings

AI_VARIABLES = (
    "OPENAI_API_KEY",
    "OPEN_AI_APIKEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "CORS_ORIGINS",
    "DATA_DIR",
)


def clean(monkeypatch):
    for name in AI_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_the_model_provider_and_frontend_origin_are_read_from_the_environment(monkeypatch):
    clean(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_MODEL", "some/other-model")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embed-x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.vercel.app")
    monkeypatch.setenv("DATA_DIR", "/var/data")
    settings = Settings(_env_file=None)
    assert (settings.openai_api_key, settings.openai_base_url) == ("sk-test", "https://openrouter.ai/api/v1")
    assert (settings.openai_model, settings.openai_embedding_model) == ("some/other-model", "embed-x")
    assert settings.cors_origin_list == ["https://app.vercel.app"]
    assert settings.data_dir == Path("/var/data")


def test_everything_can_come_from_a_dotenv_file(monkeypatch, tmp_path):
    clean(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPEN_AI_APIKEY=sk-from-file\nOPENAI_MODEL=file-model\nCORS_ORIGINS=https://a.example,https://b.example\nMAX_UPLOAD_MB=7\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.openai_api_key == "sk-from-file"
    assert settings.openai_model == "file-model"
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]
    assert settings.max_upload_mb == 7


def test_the_real_environment_wins_over_the_dotenv_file(monkeypatch, tmp_path):
    clean(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_MODEL", "dashboard-model")
    assert Settings(_env_file=env_file).openai_model == "dashboard-model"


def test_origins_tolerate_trailing_slashes_spaces_and_empty_entries(monkeypatch):
    clean(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", " https://app.vercel.app/ , ,https://other.example// ")
    assert Settings(_env_file=None).cors_origin_list == ["https://app.vercel.app", "https://other.example"]


def test_the_key_is_not_set_by_default(monkeypatch):
    clean(monkeypatch)
    assert Settings(_env_file=None).openai_api_key is None
