# Gabi Gateway - AI Agent System

## Project Overview

Gabi Gateway ist ein **autonomes KI-Agenten-System** mit multimodalem Verständnis (Text, Bild, GUI, Webcam) und selbstlernenden Fähigkeiten. Es dient als zentrale Schnittstelle zwischen verschiedenen LLMs (Ollama), Automatisierungstools und Benutzeroberflächen.

### Core Capabilities
- **Multimodale KI**: Text, Bildverarbeitung (YOLOv8), GUI-Interaktion
- **Autonomes Lernen**: Automatische Verbesserung durch Self-Correction Loop
- **Persistent Memory**: Langzeitgedächtnis via MEMORY.md, SOUL.json
- **Tool Integration**: Blender, Telegram, Web-Automation, GUI-Controller
- **Self-Awareness**: Systemmetriken, Lernfortschritt, Fehleranalyse

## Tech Stack

| Komponente | Technologie |
|------------|------------|
| **Sprache** | Python 3.10+ |
| **LLM Backend** | Ollama (qwen2.5-coder:14b empfohlen) |
| **Vision** | YOLOv8, OpenCV |
| **GUI Control** | PyAutoGUI, Selenium |
| **Memory** | JSON-basiert, Markdown-Archiv |
| **Web Framework** | FastAPI (http_api.py) |
| **Testing** | pytest |

## Getting Started

### Prerequisites

```bash
# Python 3.10 oder höher
python --version

# Ollama installieren und starten
ollama serve

# Empfohlenes Modell laden
ollama pull qwen2.5-coder:14b
ollama pull nomic-embed-text  # für Embeddings
Installation
bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# Für Vision-Features (optional)
pip install -r requirements-blender.txt

# Umgebungsvariablen einrichten
cp config.example.yaml config.yaml
# Bearbeite config.yaml mit deinen API-Keys
Quick Start
bash
# Hauptgateway starten
python main.py

# HTTP API startet auf http://localhost:8000
# Teste die API:
curl http://localhost:8000/health

# Telegram Bot starten (falls konfiguriert)
python integrations/telegram_bot.py
Project Structure
text
gateway/
├── main.py                    # Haupt-Einstiegspunkt
├── config.yaml                # Continue + System-Konfiguration
├── .continue/rules/           # AI-Assistant Regeln
│   └── CONTINUE.md           # Diese Datei
│
├── gateway/                   # Core Module
│   ├── http_api.py           # FastAPI REST API (370KB - zentral!)
│   ├── brain_left.py         # Analytisches Denken
│   ├── brain_right.py        # Kreatives/Visuelles Denken
│   ├── daemon.py             # Hintergrundprozesse
│   ├── security_gate.py      # Sicherheit & Auth
│   ├── skill_factory.py      # Tool-Management
│   ├── self_correction_loop.py # Autonome Verbesserung
│   ├── ollama_client.py      # Ollama API Wrapper
│   └── memory_extensions.py  # Gedächtnismanagement
│
├── integrations/              # Externe Integrationen
│   ├── gabi_vision.py        # Vision & Bilderkennung
│   ├── gui_controller.py     # GUI-Automatisierung (25KB)
│   ├── telegram_bot.py       # Telegram Interface
│   ├── web_automation.py     # Web-Scraping/Automation
│   ├── program_manager.py    # Programm-Management
│   └── shell_executor.py     # Shell-Kommandos
│
├── tools/                     # Utility Tools
│   ├── ai_analyzer.py        # KI-Analyse-Tools
│   ├── network_analyzer.py   # Netzwerk-Monitoring
│   ├── web_search.py         # Web-Suche
│   └── whisper_record.py     # Audio-Transkription
│
├── tests/                     # Tests
│   └── integrations/         # Integrationstests
│
├── memory_archive/            # Langzeitgedächtnis (ZIP-Archiv)
├── chat_archives/            # Gesprächsverläufe
├── screenshots/              # Screenshots (GUI, Web, Webcam)
├── static/                   # Statische Web-Dateien
└── templates/                # HTML-Templates
Core Concepts
1. Dual-Brain Architektur
Brain Left: Logisches Denken, Code-Analyse, Planung

Brain Right: Kreativität, Bildverarbeitung, Mustererkennung

2. Memory System
Kurzzeit: In-Memory während Sessions

Langzeit: MEMORY.md, MEMORY_NOTES.json, SOUL.json

Archiv: Automatisches Zippen alter Memorys (memory_archive/)

3. Self-Correction Loop
Autonomer Lernprozess:

Aktion ausführen

Ergebnis analysieren

Fehler identifizieren

Strategie anpassen

Wiederholen mit verbesserter Methode

4. Skill Factory
Dynamisches Tool-Management:

Tools werden als Skills registriert

Autonome Erkennung nutzbarer Tools

Kontext-basierte Tool-Auswahl

Development Workflow
Mit Continue und Ollama arbeiten
bash
# 1. Ollama Modell starten (empfohlen: qwen2.5-coder:14b)
ollama run qwen2.5-coder:14b

# 2. In VS Code: Ctrl+L für Continue Sidebar
# 3. Agent Mode aktivieren für Tool-Nutzung
Typische Aufgaben mit Gabi
Neue Integration hinzufügen:

text
/agent Erstelle eine neue Integration für Discord. 
Nutze das Muster aus integrations/telegram_bot.py als Vorlage.
Füge Tests in tests/integrations/ hinzu.
Memory analysieren:

text
/agent Analysiere MEMORY.md und extrahiere Lernmuster. 
Erstelle einen Report über Verbesserungspotentiale.
Self-Correction Loop verbessern:

text
/edit Optimiere self_correction_loop.py für schnellere Lernzyklen.
Behalte die bestehende Fehleranalyse bei, aber reduziere die Latenz.
Testing
bash
# Alle Tests ausführen
pytest tests/

# Integrationstests
pytest tests/integrations/

# Spezifisches Modul testen
python -c "from gateway import brain_left; brain_left.test()"
Common Tasks
1. Neues Modell in Ollama integrieren
python
# In gateway/ollama_client.py:
models = ollama.list()
# Verwende in config.yaml:
models:
  - model: qwen2.5-coder:14b
    roles: [chat, edit, apply]
2. Screenshot + Analyse durchführen
python
from integrations.gabi_vision import capture_and_analyze

# Screenshot machen und mit YOLO analysieren
result = capture_and_analyze(region="fullscreen")
print(f"Erkannte Objekte: {result['detections']}")
3. Web-Automation Aufgabe
python
from integrations.web_automation import WebAutomation

bot = WebAutomation()
bot.navigate("https://example.com")
bot.click_button("Submit")
screenshot = bot.take_screenshot()
4. Memory Backup
bash
# Automatisches Backup (läuft täglich)
python auto_git_backup.py

# Manuelles Memory-Archiv erstellen
python -c "from gateway.memory_extensions import archive_memory; archive_memory()"
Troubleshooting
Ollama Verbindungsprobleme
bash
# Prüfen ob Ollama läuft
ollama ps
# Falls nicht:
ollama serve

# API testen
curl http://localhost:11434/api/tags
Vision/GPU Probleme
python
# Teste GPU Verfügbarkeit
python -c "import torch; print(torch.cuda.is_available())"

# YOLO testen
python -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt')"
Continue "Could not resolve filepath"
Sicherstellen, dass Workspace geöffnet: File > Open Folder

Reload Window: Ctrl+Shift+P → "Developer: Reload Window"

config.yaml Pfade mit forward slashes: M:/projekte_2026/...

Memory-Korruption
bash
# Backup wiederherstellen
cd memory_archive
unzip MEMORY_ARCHIVE_*.zip -d ../restored_memory

# Memory validieren
python gateway/memory_extensions.py --validate
Environment Variables
Erstelle .env basierend auf config.example.yaml:

env
# Ollama
OLLAMA_API_BASE=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:14b

# API Keys
TELEGRAM_BOT_TOKEN=your_token
GOOGLE_API_KEY=your_key

# System
LOG_LEVEL=INFO
MEMORY_AUTO_ARCHIVE=true
SCREENSHOT_PATH=./screenshots
Important Resources
Hauptdokumentation: bedienungsanleitung.txt

API Reference: gateway/http_api.py enthält alle Endpunkte

Skills: gateway/SKILLS.md

Memory System: MEMORY.md, SOUL.json

Testing: tests/ Verzeichnis

Nächste Schritte für Entwicklung
HTTP API erweitern: Neue Endpunkte in http_api.py hinzufügen

Neue Integration: Discord, Slack, oder andere Services

Vision verbessern: YOLO-Modell feintunen für spezifische GUI-Elemente

Memory optimieren: Vektordatenbank für semantische Suche einbauen

Autonome Entscheidungen: Self-Correction Loop mit Reinforcement Learning