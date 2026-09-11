from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Benefits Compare"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    # development | staging | production
    environment: str = "development"
    # Local only: create tables via SQLAlchemy metadata. Production uses Alembic.
    auto_create_tables: bool = True
    seed_on_startup: bool = True
    database_url: str = "postgresql+asyncpg://benefits:benefits@localhost:5432/benefits_compare"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    openai_api_key: str = ""
    ollama_base_url: str = ""
    ollama_chat_model: str = "mistral-small3.2:latest"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dimensions: int = 768
    qdrant_url: str = "http://localhost:6433"
    qdrant_collection: str = "plan_chunks"
    rag_score_threshold: float = 0.25
    rag_dense_k: int = 12
    rag_sparse_k: int = 12
    rag_rerank_k: int = 5
    rag_semantic_cache_threshold: float = 0.95
    cors_origins: str = Field(
        default="http://localhost:3100,http://127.0.0.1:3100",
        description="Comma-separated browser origins allowed by CORS",
    )

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def should_auto_create_tables(self) -> bool:
        if self.is_production:
            return False
        return self.auto_create_tables


@lru_cache
def get_settings() -> Settings:
    return Settings()
