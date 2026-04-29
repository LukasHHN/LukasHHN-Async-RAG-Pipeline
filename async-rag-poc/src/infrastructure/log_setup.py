# src/infrastructure/log_setup.py
import logging
import sys
import structlog
from src.infrastructure.config import settings

def configure_logging() -> None:
    """
    Konfiguriert das Logging-System für die gesamte Anwendung.
    Überschreibt auch das Standard-Logging von FastAPI/Uvicorn, 
    damit alle Logs einheitlich aussehen.
    """
    # Lese den Log-Level aus unserer Pydantic Settings-Klasse
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Konfiguriere das Standard-Python-Logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Konfiguriere structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,          # Erlaubt das Hinzufügen von Kontext (z.B. job_id) zu allen Logs
            structlog.stdlib.add_log_level,                   # Fügt INFO, ERROR, etc. hinzu
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True), # Standardisierter Zeitstempel
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Für die lokale Entwicklung nutzen wir den ConsoleRenderer (schön formatiert und farbig).
            # In Produktion würde man hier structlog.processors.JSONRenderer() verwenden.
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )