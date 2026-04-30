# src/interfaces/worker/main.py
import asyncio
import uuid
import structlog
import fitz  # PyMuPDF

from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from src.infrastructure.log_setup import configure_logging
from src.infrastructure.queue_client import redis_settings
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.models import DocumentModel
from src.infrastructure.config import settings

configure_logging()
logger = structlog.get_logger()

# 1. Wir initialisieren das Embedding-Modell (wird beim ersten Start lokal heruntergeladen)
# BAAI/bge-small-en-v1.5 ist ein winziges, aber extrem starkes Open-Source-Modell (Vektor-Größe: 384)
embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

# 2. Verbindung zu unserer lokalen Qdrant-Instanz
qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
COLLECTION_NAME = "documents"

def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text_parts = [str(page.get_text()) for page in doc]
    return "".join(text_parts)

def chunk_text(text: str) -> list[str]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )
    return text_splitter.split_text(text)

async def ensure_qdrant_collection():
    """Stellt sicher, dass die Tabelle (Collection) in Qdrant existiert."""
    exists = await qdrant.collection_exists(COLLECTION_NAME)
    if not exists:
        await qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("qdrant_collection_created", collection=COLLECTION_NAME)

async def process_document(ctx, job_id: str, file_path: str):
    logger.info("worker_started_job", job_id=job_id, file_path=file_path)
    
    # Sicherstellen, dass Qdrant bereit ist
    await ensure_qdrant_collection()
    
    async with AsyncSessionLocal() as db:
        doc = await db.get(DocumentModel, job_id)
        if not doc:
            return
            
        doc.status = "PROCESSING"
        await db.commit()
        
        try:
            # 1. Text extrahieren
            full_text = await asyncio.to_thread(extract_text_from_pdf, file_path)
            
            # 2. Chunking
            chunks = await asyncio.to_thread(chunk_text, full_text)
            
            # 3. Embeddings generieren (Lokale KI-Magie)
            logger.info("generating_embeddings", job_id=job_id)
            # fastembed.embed() gibt einen Generator zurück, wir wandeln ihn in eine Liste um
            embeddings_generator = await asyncio.to_thread(embedding_model.embed, chunks)
            embeddings = list(embeddings_generator)
            
            # 4. Speichern in Qdrant
            logger.info("saving_to_qdrant", job_id=job_id, count=len(chunks))
            points = [
                PointStruct(
                    id=str(uuid.uuid4()), 
                    vector=emb.tolist(), 
                    payload={"job_id": job_id, "text": chunk, "filename": doc.filename}
                )
                for emb, chunk in zip(embeddings, chunks)
            ]
            await qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            
            # Abschluss
            doc.status = "COMPLETED"
            await db.commit()
            logger.info("db_status_updated", job_id=job_id, status="COMPLETED")
            
        except Exception as e:
            logger.error("processing_failed", job_id=job_id, error=str(e))
            doc.status = "FAILED"
            await db.commit()
            
    logger.info("worker_finished_job", job_id=job_id)

class WorkerSettings:
    functions = [process_document]
    redis_settings = redis_settings