# src/interfaces/api/main.py
import os
import uuid
import aiofiles
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, UploadFile, File, status, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from arq import create_pool

from src.infrastructure.log_setup import configure_logging
from src.infrastructure.database import engine, get_db_session
from src.infrastructure.models import Base, DocumentModel
from src.infrastructure.queue_client import redis_settings

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

configure_logging()
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api_started", framework="fastapi")
    
    # Datenbank-Tabellen initialisieren
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_verified")
    
    # NEU: Redis Connection Pool für ARQ erstellen
    app.state.redis_pool = await create_pool(redis_settings)
    logger.info("redis_pool_created")
    
    yield
    
    # Sauberes Herunterfahren
    logger.info("api_shutdown", framework="fastapi")
    await app.state.redis_pool.close()
    await engine.dispose()

app = FastAPI(
    title="Async RAG Pipeline API",
    description="Professionelles API Gateway für die asynchrone Dokumentenverarbeitung",
    version="0.2.0",
    lifespan=lifespan
)

@app.post("/documents/", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request, # NEU: Das Request-Objekt, um an den app.state zu kommen
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session)
):
    job_id = str(uuid.uuid4())
    logger.info("document_upload_received", filename=file.filename, job_id=job_id)
    
    # 1. Datei physisch speichern
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
    except Exception as e:
        logger.error("document_save_failed", error=str(e), job_id=job_id)
        return JSONResponse(status_code=500, content={"message": "Fehler beim Speichern der Datei."})

    # 2. Datenbank-Eintrag anlegen
    new_doc = DocumentModel(id=job_id, filename=file.filename, status="PENDING")
    try:
        db.add(new_doc)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("database_entry_failed", error=str(e), job_id=job_id)
        return JSONResponse(status_code=500, content={"message": "Datenbankfehler."})

    # 3. NEU: Den Job in die Redis-Queue schieben
    try:
        redis_pool = request.app.state.redis_pool
        # Wir rufen eine Funktion "process_document" auf, die der Worker später bereitstellt
        await redis_pool.enqueue_job("process_document", job_id=job_id, file_path=file_path)
        logger.info("job_enqueued_to_redis", job_id=job_id)
    except Exception as e:
        logger.error("redis_enqueue_failed", error=str(e), job_id=job_id)
        return JSONResponse(status_code=500, content={"message": "Fehler beim Einreihen in die Queue."})
    
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Dokument erfolgreich entgegengenommen. Verarbeitung läuft.",
            "job_id": job_id,
            "filename": file.filename
        }
    )