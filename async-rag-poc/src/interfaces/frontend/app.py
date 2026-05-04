# src/interfaces/frontend/app.py
import streamlit as st
import requests

# Die Adresse unserer FastAPI
API_URL = "http://127.0.0.1:8000"

# --- Seiten-Konfiguration ---
st.set_page_config(page_title="KI Dokumenten-Assistent", page_icon="📄", layout="wide")
st.title("📄 Dein intelligenter Dokumenten-Assistent")
st.markdown("Lade ein PDF hoch und stelle Fragen dazu. Die KI antwortet basierend auf dem Dokumenten-Inhalt.")

# --- Seitenleiste: Datei-Upload ---
with st.sidebar:
    st.header("📂 1. Dokument hochladen")
    st.info("Lade hier deine PDFs hoch, bevor du Fragen stellst.")
    
    uploaded_file = st.file_uploader("Wähle ein PDF aus", type=["pdf"])
    
    if st.button("Hochladen & Verarbeiten", type="primary"):
        if uploaded_file is not None:
            with st.spinner("Dokument wird an die KI übergeben..."):
                # Datei an unsere FastAPI senden
                files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
                try:
                    response = requests.post(f"{API_URL}/documents/", files=files)
                    if response.status_code == 202:
                        st.success(f"Erfolg! '{uploaded_file.name}' wird verarbeitet und ist gleich bereit.")
                    else:
                        st.error("Fehler beim Upload.")
                except requests.exceptions.ConnectionError:
                    st.error("Konnte API nicht erreichen. Läuft dein Uvicorn-Server?")
        else:
            st.warning("Bitte wähle zuerst eine Datei aus.")

# --- Hauptbereich: Chat-Interface ---
st.header("💬 2. Chat")

# Chat-Verlauf im Session State speichern (damit er beim Neuladen nicht verschwindet)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Bisherigen Chat-Verlauf anzeigen
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Nutzereingabe ---
# st.chat_input erzeugt das typische Chat-Eingabefeld am unteren Rand
if prompt := st.chat_input("Was möchtest du über das Dokument wissen?"):
    
    # 1. Frage des Nutzers anzeigen und speichern
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Anfrage an unsere API senden
    with st.spinner("Die KI durchsucht die Dokumente..."):
        try:
            # Wir nutzen das Form-Feld, das wir in der API definiert haben
            response = requests.post(f"{API_URL}/query/", data={"question": prompt})
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "Keine Antwort erhalten.")
                sources = data.get("sources", [])
                
                # Quellen schön formatieren (Duplikate entfernen)
                unique_sources = list(set(sources))
                source_text = f"\n\n*📚 Quellen: {', '.join(unique_sources)}*" if unique_sources else ""
                
                full_response = answer + source_text
                
                # Antwort anzeigen und speichern
                with st.chat_message("assistant"):
                    st.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                st.error(f"Die API meldet einen Fehler: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            st.error("Konnte API nicht erreichen. Läuft dein Uvicorn-Server?")