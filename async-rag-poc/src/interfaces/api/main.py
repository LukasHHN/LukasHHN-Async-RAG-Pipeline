# src/interfaces/api/main.py
import os
import uuid
import aiofiles
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, UploadFile, File, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.log_setup import configure_logging
from src.infrastructure.database import engine, get_db_session
from src.infrastructure.models import Base, DocumentModel

# Upload-Verzeichnis definieren
UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 1. Logging initialisieren
configure_logging()
logger = structlog.get_logger()

# 2. Lifespan definieren
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api_started", framework="fastapi")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_verified")
    yield
    logger.info("api_shutdown", framework="fastapi")
    await engine.dispose()

# 3. FastAPI App Instanz erstellen
app = FastAPI(
    title="Async RAG Pipeline API",
    description="Professionelles API Gateway für die asynchrone Dokumentenverarbeitung",
    version="0.1.0",
    lifespan=lifespan
)

# 4. Der asynchrone Upload-Endpunkt
@app.post("/documents/", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session)  # <--- Dependency Injection der DB-Session
):
    """
    Nimmt ein Dokument (PDF, TXT) entgegen, speichert es ab und legt einen Datenbankeintrag an.
    """
    job_id = str(uuid.uuid4())
    
    logger.info(
        "document_upload_received", 
        filename=file.filename, 
        job_id=job_id, 
        content_type=file.content_type
    )
    
    # 1. Datei physisch asynchron abspeichern
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()  # Datei in den Speicher lesen
            await out_file.write(content) # Datei auf die Festplatte schreiben
        logger.info("document_saved_to_disk", path=file_path)
    except Exception as e:
        logger.error("document_save_failed", error=str(e), job_id=job_id)
        return JSONResponse(status_code=500, content={"message": "Fehler beim Speichern der Datei."})

    # 2. Datenbank-Eintrag (Status: PENDING) anlegen
    new_doc = DocumentModel(
        id=job_id,
        filename=file.filename,
        status="PENDING"
    )
    
    try:
        db.add(new_doc)
        await db.commit()
        logger.info("database_entry_created", job_id=job_id, status="PENDING")
    except Exception as e:
        await db.rollback()
        logger.error("database_entry_failed", error=str(e), job_id=job_id)
        return JSONResponse(status_code=500, content={"message": "Datenbankfehler."})

    # TODO: Nächster Schritt - Job_id an Redis (Task Queue) senden!
    
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Dokument erfolgreich entgegengenommen. Verarbeitung läuft im Hintergrund.",
            "job_id": job_id,
            "filename": file.filename
        }
    )