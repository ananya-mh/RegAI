from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/complianceforge"
    database_sync_url: str = "postgresql://postgres:postgres@localhost:5432/complianceforge"

    faiss_index_path: str = "./backend/rag/indexes/faiss"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_persist_path: str = "./backend/rag/indexes/chroma"


settings = Settings()
