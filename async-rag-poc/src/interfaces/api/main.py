# src/interfaces/api/main.py
import os
import uuid
import aiofiles
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, UploadFile, File, status, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from arq import create_pool

from src.infrastructure.log_setup import configure_logging
from src.infrastructure.database import engine, get_db_session
from src.infrastructure.models import Base, DocumentModel
from src.infrastructure.queue_client import redis_settings

# Neue Imports für den Query-Endpunkt in main.py
from pydantic import BaseModel
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from anthropic import AsyncAnthropic
from src.infrastructure.config import settings

# --- Globale KI-Clients initialisieren ---
# Qdrant Client
qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
COLLECTION_NAME = "documents"

# Anthropic Client für Claude
anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# Das gleiche lokale Embedding-Modell wie im Worker!
embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

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
    
    
@app.post("/query/")
async def query_documents(question: str = Form(...)):  # <--- HIER GEÄNDERT
    """
    Sucht die relevantesten Textabschnitte in Qdrant und generiert eine Antwort mit Claude.
    """
    logger.info("query_received", question=question)   # <--- HIER GEÄNDERT

    try:
        # 1. Frage embedden (lokal)
        question_embedding_generator = embedding_model.embed([question]) # <--- HIER GEÄNDERT
        question_vector = list(question_embedding_generator)[0].tolist()
        
        # 2. Vektor-Suche in Qdrant (Hole die Top 3 Treffer)
        search_response = await qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=question_vector,
            limit=3
        )
        
        # Die eigentlichen Treffer stecken nun im '.points' Attribut der Antwort
        search_result = search_response.points
        
        # Wenn Qdrant leer ist
        if not search_result:
            return {"answer": "Ich habe leider noch keine Dokumente in meiner Datenbank, um diese Frage zu beantworten."}
            
        # 3. Kontext zusammenbauen
        context_texts = []
        for hit in search_result:
            # Wir ziehen den Text aus der Payload, die der Worker gespeichert hat
            chunk_text = hit.payload.get("text", "") 
            filename = hit.payload.get("filename", "Unbekannt")
            context_texts.append(f"--- Aus Dokument '{filename}' ---\n{chunk_text}")
            
        full_context = "\n\n".join(context_texts)
        logger.info("context_retrieved", num_chunks=len(search_result))
        
        # 4. Prompt für Claude bauen
        system_prompt = """Du bist ein präziser, hilfreicher Assistent. 
Beantworte die Frage des Nutzers AUSSCHLIESSLICH basierend auf dem bereitgestellten Kontext. 
Wenn die Antwort nicht im Kontext steht, sage ehrlich, dass du es basierend auf den Dokumenten nicht weißt. Erfinde nichts."""

        # (Achte nur darauf, auch unten beim user_prompt das request.question zu ändern)
        user_prompt = f"Kontext:\n{full_context}\n\nFrage: {question}" # <--- HIER GEÄNDERT
        
        # 5. Claude API aufrufen
        logger.info("calling_claude")
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-6", # Das neue Modell
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        answer = response.content[0].text
        logger.info("claude_answered")
        
        return {
            "answer": answer,
            "sources": [hit.payload.get("filename") for hit in search_result] # Wir geben auch die Quellen zurück!
        }
        
    except Exception as e:
        logger.error("query_failed", error=str(e))
        return JSONResponse(status_code=500, content={"message": f"Fehler bei der Anfrage: {str(e)}"})