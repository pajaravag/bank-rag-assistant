"""Typed, centralized configuration loaded from environment / .env file.

`get_settings()` is cached so every component shares the same Settings
instance (Singleton behaviour without a hand-rolled singleton class).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    groq_api_key: str = ""
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # Conversation
    history_window_n: int = 6

    # Ingestion
    chunk_size: int = 800
    chunk_overlap: int = 120
    embedding_model: str = "intfloat/multilingual-e5-small"

    # Retrieval
    top_k: int = 8
    rerank_enabled: bool = True
    rerank_top_k: int = 4
    rerank_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

    # Vector DB
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "bank_site"

    # Scraper
    scrape_base_url: str = "https://www.bancolombia.com/"
    scrape_max_pages: int = 150
    scrape_delay_seconds: float = 0.4
    scrape_timeout_seconds: float = 15.0

    # Local storage
    data_dir: str = "data"
    history_db_path: str = "data/history.db"

    @property
    def raw_dir(self) -> str:
        return f"{self.data_dir}/raw"

    @property
    def clean_dir(self) -> str:
        return f"{self.data_dir}/clean"


@lru_cache
def get_settings() -> Settings:
    return Settings()
