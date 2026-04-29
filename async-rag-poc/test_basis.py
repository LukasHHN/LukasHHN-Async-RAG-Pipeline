# test_basis.py
import asyncio
from redis.asyncio import Redis
import structlog

from src.infrastructure.config import settings
from src.infrastructure.log_setup import configure_logging

async def main():
    # 1. Logging initialisieren
    configure_logging()
    logger = structlog.get_logger()
    
    logger.info("starte_systemtest", phase="basis")
    
    # 2. Prüfen, ob Pydantic die .env Datei korrekt gelesen hat
    logger.info("settings_geladen", 
                db_host=settings.postgres_host, 
                redis_host=settings.redis_host, 
                qdrant_host=settings.qdrant_host,
                log_level=settings.log_level)
    
    # 3. Aktiver Verbindungstest zu Redis (läuft im Docker-Container)
    try:
        redis = Redis.from_url(settings.redis_url)
        pong = await redis.ping()
        logger.info("redis_verbindung_erfolgreich", antwort=pong)
        await redis.aclose()
    except Exception as e:
        logger.error("redis_verbindung_fehlgeschlagen", error=str(e))

if __name__ == "__main__":
    asyncio.run(main())