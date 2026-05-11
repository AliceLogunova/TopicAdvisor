from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "topicadvisor"
    postgres_user: str = "postgres"
    postgres_password: str = "102612"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Ollama
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:2b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"

    # FAISS
    faiss_index_path: Path = Path("data/faiss_store/index.faiss")

    # arXiv
    arxiv_max_results: int = 1000

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()