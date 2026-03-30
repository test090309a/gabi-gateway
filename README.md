# 🧠 GABI Gateway

**G**ateway **A**I **B**ot **I**nterface - Ein intelligenter KI-Assistent mit Sprachsteuerung, Web-Suche, Bildgenerierung und mehr.

[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-0.5+-orange.svg)](https://ollama.ai)

---

## ✨ Features

- 🎤 **Sprachsteuerung** - "Hey GABI" aktiviert Whisper-Transkription
- 🌐 **Web-Suche** - Headless DuckDuckGo Suche mit SmartSoMAgent
- 🎨 **ComfyUI Integration** - Bildgenerierung mit eigenen Workflows
- 📷 **Vision & Webcam** - Bildanalyse mit Vision-Modellen + YOLO Objekterkennung
- 📱 **Telegram Bot** - Chat über Telegram mit allen GABI-Funktionen
- 📧 **Gmail Integration** - E-Mails lesen, senden, beantworten
- 💻 **Shell & GUI Control** - Systembefehle und GUI-Automatisierung
- 🧠 **Memory System** - Notizen, Konversationsverlauf, Chat-Archive
- 🔧 **Corpus Callosum** - Hemisphären-Routing für optimale Modellauswahl
- ⚡ **Hot-Reload** - Dynamisches Laden von Integrationen

---

## 🚀 Quick Start

### Voraussetzungen

- Python 3.12+
- [Ollama](https://ollama.ai) mit mindestens einem Modell (z.B. `llama3.1:8b`)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) (optional, für Bildgenerierung)
- [Whisper Server](https://github.com/ggerganov/whisper.cpp) (optional, für Sprachsteuerung)

### Installation

```bash
# Repository klonen
git clone https://github.com/test090309a/gabi-gateway.git
cd gabi-gateway

# Abhängigkeiten installieren
pip install -r requirements.txt

# Konfiguration anpassen (optional)
# config.yaml enthält alle Einstellungen
Starten
bash
python main.py
Dashboard: http://localhost:8000
API Docs: http://localhost:8000/docs

📋 Befehle
Befehl	Beschreibung
/vision	Webcam-Foto + Analyse
/comfy generate <prompt>	Bild generieren (ComfyUI)
/comfy gallery	Generierte Bilder anzeigen
/shell <befehl>	Shell-Befehl ausführen
/gui open <programm>	Programm öffnen
/merken <text>	Notiz speichern
/gemerkt	Notizen anzeigen
/telegram send <msg>	Nachricht an Telegram
/model <name>	Modell wechseln
/help	Alle Befehle anzeigen
Sprachsteuerung
"Hey GABI" - Aktiviert die Spracherkennung

Web-Suche
"google <frage>" - Führt eine Web-Suche durch

⚙️ Konfiguration
Alle Einstellungen in config.yaml:

yaml
# API Key für Authentifizierung
api_key: "sysop"

# Ollama Modelle
ollama:
  default_model: "llama3.1:8b"
  preferred_vision_models: ["qwen3-vl:8b"]

# Telegram Bot
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: YOUR_CHAT_ID

# ComfyUI
comfyui:
  host: "127.0.0.1"
  port: 8188

# Whisper
whisper:
  enabled: true
  server_url: "http://127.0.0.1:9090"
🏗️ Projektstruktur
text
gabi-gateway/
├── main.py                 # FastAPI App
├── config.py               # Zentrale Konfiguration
├── auth.py                 # Authentifizierung
├── config.yaml             # Konfigurationsdatei
├── gateway/                # Hauptmodul
│   ├── api/                # API-Endpunkte
│   ├── core/               # Kernlogik (Brain, Router, Commands)
│   ├── integrations/       # Integrationen (Telegram, Gmail, ComfyUI)
│   └── utils/              # Hilfsfunktionen
├── static/                 # Web-Dashboard
├── screenshots/            # Screenshots und generierte Bilder
└── chat_archives/          # Chat-Archive
🛠️ Technologien
Backend: FastAPI, Uvicorn

KI: Ollama (Llama, Qwen, Vision-Modelle)

Spracherkennung: Whisper.cpp

Web-Suche: Selenium, DuckDuckGo

Bildgenerierung: ComfyUI

GUI-Steuerung: PyAutoGUI

Telegram: python-telegram-bot

Gmail/Calendar: Google APIs

📝 Lizenz
MIT License

🤝 Contributing
Issues und Pull Requests sind willkommen!

