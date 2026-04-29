# src/infrastructure/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # App Settings
    log_level: str = "INFO"

    # Pydantic v2 Konfiguration, um die .env Datei automatisch zu laden
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def database_url(self) -> str:
        """Baut den SQLAlchemy Connection String zusammen."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        """Baut die Redis URL für ARQ/Celery zusammen."""
        return f"redis://{self.redis_host}:{self.redis_port}"

# Wir erstellen direkt eine Instanz, die wir im gesamten Projekt importieren können
settings = Settings()  # type: ignore