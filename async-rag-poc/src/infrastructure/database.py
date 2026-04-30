# src/infrastructure/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.infrastructure.config import settings

# Die Engine verwaltet den Connection-Pool zur Datenbank
engine = create_async_engine(settings.database_url, echo=False)

# Die Session-Fabrik generiert uns für jeden API-Aufruf eine frische Datenbankverbindung
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    expire_on_commit=False
)

# Diese Funktion nutzen wir später in FastAPI, um die Verbindung bereitzustellen
async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session