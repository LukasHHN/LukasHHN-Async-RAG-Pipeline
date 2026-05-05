# Wir starten mit einem schlanken Python 3.11 Image
FROM python:3.11-slim

# 1. WICHTIG: Fehlende System-Bibliotheken für KI & PDF-Tools installieren
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# uv installieren
RUN pip install uv

# Kopiere alle Projektdateien in den Container
COPY . /app

# Erstelle den Upload-Ordner zur Sicherheit
RUN mkdir -p data/uploads

# 2. WICHTIG: Wir löschen eine eventuell von Windows kopierte Lockfile, 
# damit uv die Abhängigkeiten frisch für Linux auflöst.
RUN rm -f uv.lock

# Installiere alle Abhängigkeiten
RUN uv sync

# Standardmäßig machen wir nichts (Der Startbefehl kommt aus der docker-compose.yml)
CMD ["bash"]