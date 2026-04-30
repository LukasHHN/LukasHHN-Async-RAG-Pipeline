# src/infrastructure/queue_client.py
from arq.connections import RedisSettings
from src.infrastructure.config import settings

# Wir übersetzen unsere Pydantic-Settings in das Format, das ARQ versteht
redis_settings = RedisSettings(
    host=settings.redis_host,
    port=settings.redis_port
)