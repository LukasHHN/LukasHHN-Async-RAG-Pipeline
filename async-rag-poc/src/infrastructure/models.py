# src/infrastructure/models.py
from datetime import datetime, timezone
from sqlalchemy import String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Die Basis-Klasse für alle unsere Tabellen
class Base(DeclarativeBase):
    pass

class DocumentModel(Base):
    __tablename__ = "documents"

    # Die job_id ist unser Primärschlüssel
    id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Der ursprüngliche Dateiname
    filename: Mapped[str] = mapped_column(String, nullable=False)
    
    # Status: PENDING, PROCESSING, COMPLETED, FAILED
    status: Mapped[str] = mapped_column(String, default="PENDING")
    
    # Wann wurde das Dokument hochgeladen?
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )