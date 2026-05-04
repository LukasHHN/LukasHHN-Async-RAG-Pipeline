# KI Dokumenten-Assistent — Async RAG Pipeline

> Lokales, asynchrones Retrieval-Augmented Generation System für die Verarbeitung und Befragung von PDF-Dokumenten.

---

## Inhaltsverzeichnis

1. [Projektübersicht](#1-projektübersicht)
2. [Architektur & Tech-Stack](#2-architektur--tech-stack)
3. [Systemvoraussetzungen](#3-systemvoraussetzungen)
4. [Installation & Setup](#4-installation--setup)
5. [Das System starten](#5-das-system-starten)
6. [Bedienung & Datenfluss](#6-bedienung--datenfluss)
7. [Projektstruktur](#7-projektstruktur)

---

## 1. Projektübersicht

Dieses Projekt ist ein lokales, asynchrones **Retrieval-Augmented Generation (RAG)**-System. Es ermöglicht Nutzern, PDF-Dokumente hochzuladen und anschließend in natürlicher Sprache Fragen zu diesen Dokumenten zu stellen.

Die Kernidee liegt in der **entkoppelten, asynchronen Architektur**: CPU-intensive Aufgaben (PDF-Parsing, Embedding-Generierung) blockieren nicht die Haupt-API, sondern werden über eine Redis-Queue an einen dedizierten Background-Worker ausgelagert.

**Vorteile dieser Architektur:**

| Eigenschaft | Bedeutung |
|---|---|
| **Skalierbarkeit** | API und Worker können unabhängig skaliert werden |
| **Ausfallsicherheit** | Fehlgeschlagene Jobs werden automatisch wiederholt |
| **Performance** | API antwortet sofort mit `202 Accepted` — kein Blockieren |
| **Wartbarkeit** | Klare Trennung der Verantwortlichkeiten (Clean Architecture) |

---

## 2. Architektur & Tech-Stack

Das System ist in drei logische Schichten unterteilt, die über definierte Schnittstellen kommunizieren.

```
┌─────────────────────────────────────────────┐
│              Frontend (Streamlit)            │
└────────────────────┬────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────┐
│              API (FastAPI)                   │
│       Routing · Validierung · Orchestrierung │
└────────┬───────────────────────┬────────────┘
         │ Redis Job Queue       │ Qdrant / Claude API
┌────────▼────────┐    ┌─────────▼──────────────────┐
│ Background      │    │ Persistence Layer            │
│ Worker (ARQ)    │    │ Redis · Qdrant · Embeddings  │
└─────────────────┘    └──────────────────────────────┘
```

### Komponenten im Überblick

| Schicht | Technologie | Aufgabe |
|---|---|---|
| **Frontend** | Streamlit | Benutzeroberfläche für Upload & Chat |
| **API** | FastAPI + Pydantic | HTTP-Routing, Validierung, Orchestrierung |
| **Worker** | ARQ (Async Redis Queue) | PDF-Parsing, Chunking, Embedding-Generierung |
| **Message Broker** | Redis | Job-Warteschlange zwischen API und Worker |
| **Vektordatenbank** | Qdrant (Docker) | Speicherung & Suche von Embeddings |
| **Embeddings** | fastembed · `BAAI/bge-small-en-v1.5` | Lokale CPU-Embeddings, kostenlos |
| **LLM** | Anthropic Claude Sonnet 4.5 | Textgenerierung via API |

---

## 3. Systemvoraussetzungen

Folgende Komponenten müssen auf dem Host-System installiert sein:

- **Python** 3.10+
- **uv** — moderner Python-Paketmanager ([Installation](https://docs.astral.sh/uv/))
- **Docker & Docker Compose** — für Redis und Qdrant
- **Anthropic API-Key** — für Claude ([API-Key erstellen](https://console.anthropic.com/))

---

## 4. Installation & Setup

### Schritt 1 — Repository klonen & Abhängigkeiten installieren

```bash
git clone <repo-url>
cd <projektverzeichnis>
uv sync
```

> `uv sync` liest `pyproject.toml` und installiert alle Abhängigkeiten in einer isolierten virtuellen Umgebung.

### Schritt 2 — Infrastruktur starten

Stelle sicher, dass Docker läuft, und starte Redis und Qdrant:

```bash
docker-compose up -d
```

### Schritt 3 — Umgebungsvariablen konfigurieren

Erstelle eine `.env`-Datei im Projektverzeichnis:

```env
# Infrastruktur
REDIS_URL=redis://localhost:6379
QDRANT_HOST=localhost
QDRANT_PORT=6333

# KI Provider
ANTHROPIC_API_KEY=sk-ant-api03-dein-echter-key-hier
```

> **Sicherheitshinweis:** Die `.env`-Datei niemals in die Versionskontrolle committen. Sicherstellen, dass `.env` in der `.gitignore` eingetragen ist.

---

## 5. Das System starten

Aufgrund der entkoppelten Architektur müssen drei Komponenten in **separaten Terminals** gestartet werden.

### Terminal 1 — API starten

```bash
uv run uvicorn src.interfaces.api.main:app --reload
```

Startet den FastAPI-Server auf `http://localhost:8000`. Die automatisch generierte API-Dokumentation ist unter `http://localhost:8000/docs` verfügbar.

### Terminal 2 — Background-Worker starten

```bash
uv run arq src.interfaces.worker.main.WorkerSettings
```

> **Hinweis:** Beim ersten Start lädt der Worker das Embedding-Modell (~130 MB) einmalig in den lokalen Cache. Dieser Vorgang kann einige Minuten dauern.

### Terminal 3 — Frontend starten

```bash
uv run streamlit run src/interfaces/frontend/app.py
```

Das Frontend öffnet sich automatisch im Browser unter `http://localhost:8501`.

---

## 6. Bedienung & Datenfluss

### Phase A — Dokument-Ingestion (Upload)

```
Nutzer lädt PDF hoch
       │
       ▼
Streamlit → POST /documents/
       │
       ▼
API: Datei speichern · DB-Eintrag (PENDING) · job_id → Redis
       │
       ▼
HTTP 202 Accepted  ←──── Nutzer wartet nicht
       │
       ▼ (asynchron)
Worker: PDF lesen (PyMuPDF) → Chunks erstellen (LangChain)
      → Embeddings generieren (fastembed) → Qdrant speichern
       │
       ▼
DB-Status: COMPLETED
```

### Phase B — Query (Chat)

```
Nutzer stellt Frage im Chat
       │
       ▼
Streamlit → POST /query/
       │
       ▼
API: Frage → Embedding-Vektor (lokal)
       │
       ▼
Qdrant: Top-3 semantisch ähnliche Chunks abrufen
       │
       ▼
API: Prompt aufbauen (Kontext + Frage) → Claude API
       │
       ▼
Claude generiert Antwort
       │
       ▼
Streamlit: Antwort + genutzte Quellen anzeigen
```

---

## 7. Projektstruktur

Das Projekt folgt den Prinzipien der **Clean Architecture**, um Abhängigkeiten sauber zu trennen und einzelne Schichten unabhängig testbar und austauschbar zu halten.

```
projekt/
├── src/
│   ├── interfaces/          # Kontaktpunkte nach außen
│   │   ├── api/             # FastAPI Router & Endpunkte
│   │   │   └── main.py
│   │   ├── worker/          # ARQ Worker Settings & Tasks
│   │   │   └── main.py
│   │   └── frontend/        # Streamlit UI
│   │       └── app.py
│   └── infrastructure/      # Technische Querschnittsthemen
│       ├── config.py        # Pydantic Settings (.env)
│       ├── logging.py       # Strukturiertes Logging
│       └── database/        # DB-Verbindungen & Modelle
├── data/
│   └── uploads/             # Temporärer Speicher für PDFs
├── docker-compose.yml       # Redis & Qdrant
├── pyproject.toml           # Abhängigkeiten (uv/poetry)
├── .env                     # Lokale Konfiguration (nicht committen!)
└── README.md                # Diese Dokumentation
```

### Architektur-Prinzipien

- **Dependency Inversion** — Business-Logik hängt von Abstraktionen ab, nicht von konkreten Bibliotheken. Ein `VectorStore`-Interface macht Qdrant austauschbar.
- **Pydantic-Validierung** — Strikte Datentvalidierung an allen Systemgrenzen.
- **Environment-Konfiguration** — Alle Secrets und URLs über `.env`-Dateien, niemals hartcodiert.

---

*Dokumentation zuletzt aktualisiert: Mai 2026*
