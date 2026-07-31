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

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:8b"
    llm_max_retries: int = 1
    llm_timeout_seconds: int = 60

    mcp_server_url: str = "http://localhost:3000"


settings = Settings()
