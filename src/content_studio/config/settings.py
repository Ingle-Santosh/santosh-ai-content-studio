from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_base_dir() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOCAL_ONLY: bool = True

    # Paths
    BASE_DIR: Path = _default_base_dir()
    DATA_DIR: Path | None = None
    PROJECTS_DIR: Path | None = None
    DATABASE_URL: str | None = None

    # API & Model endpoints
    API_BASE_URL: str = "http://127.0.0.1:8000"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "qwen2.5-coder:14b"
    OLLAMA_WRITING_MODEL: str | None = None
    OLLAMA_FAST_MODEL: str | None = None

    # Optional Cloud LLM fallback (disabled by default via LOCAL_ONLY=True)
    CLOUD_LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str | None = None
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash"

    # LLM Execution & Budget Guardrails
    MAX_BUDGET_USD: float = Field(default=0.0, ge=0.0)
    LLM_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0.0)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_RETRY_BASE_DELAY_SECONDS: float = Field(default=0.5, ge=0.0)
    LLM_STRUCTURED_MAX_REPAIRS: int = Field(default=2, ge=0, le=4)

    # Web Research Providers (DuckDuckGo requires zero API keys by default)
    SEARCH_PROVIDER: str = "duckduckgo"
    SEARCH_API_KEY: str | None = None
    RESEARCH_FETCH_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0.0)
    RESEARCH_MAX_RESULTS_PER_QUERY: int = Field(default=5, ge=1, le=20)

    # Public YouTube Competitor Metadata (optional API key; falls back to public search + oEmbed)
    YOUTUBE_API_KEY: str | None = None
    YOUTUBE_MAX_COMPETITORS: int = Field(default=5, ge=1, le=20)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        base = self.BASE_DIR.resolve()
        self.BASE_DIR = base

        if self.DATA_DIR is None:
            self.DATA_DIR = base / "data"
        elif not self.DATA_DIR.is_absolute():
            self.DATA_DIR = (base / self.DATA_DIR).resolve()
        else:
            self.DATA_DIR = self.DATA_DIR.resolve()

        if self.PROJECTS_DIR is None:
            self.PROJECTS_DIR = self.DATA_DIR / "projects"
        elif not self.PROJECTS_DIR.is_absolute():
            self.PROJECTS_DIR = (base / self.PROJECTS_DIR).resolve()
        else:
            self.PROJECTS_DIR = self.PROJECTS_DIR.resolve()

        if not self.DATABASE_URL:
            db_path = (self.DATA_DIR / "content_studio.db").as_posix()
            self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

        return self

    @property
    def resolved_data_dir(self) -> Path:
        assert self.DATA_DIR is not None
        return self.DATA_DIR

    @property
    def resolved_projects_dir(self) -> Path:
        assert self.PROJECTS_DIR is not None
        return self.PROJECTS_DIR

    @property
    def resolved_database_url(self) -> str:
        assert self.DATABASE_URL is not None
        return self.DATABASE_URL

    @property
    def checkpoints_db_path(self) -> Path:
        return self.resolved_data_dir / "checkpoints.db"

    def ensure_directories(self) -> None:
        self.resolved_data_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_projects_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
