# GABI Skills & Fähigkeiten

## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Gmail**: E-Mails lesen, senden, verwalten
- **Telegram**: Bot-Integration
- **Whisper**: Audio-Transkription (Sprach-zu-Text)
- **Voice**: `/api/voice/transcribe` für Audio-Transkription

## 🤖 Autonome Fähigkeiten (Selbst-erweiternd)

### 1. SELF-CORRECTION LOOP
- **Status**: ✅ Aktiv
- **Beschreibung**: Wenn der Security-Score < 80 liegt oder Tests fehlschlagen, analysiert GABI den Fehler automatisch und korrigiert den Code selbstständig (bis zu 3 Iterationen).
- **Konfiguration**: `MIN_SECURITY_SCORE = 80`, `MAX_CORRECTION_ITERATIONS = 3`

### 2. DYNAMISCHES HOT-RELOADING
- **Status**: ✅ Aktiv
- **Beschreibung**: Neue Integrationen im `integrations/` Ordner werden automatisch erkannt und ohne Neustart des Servers als FastAPI-Routen registriert.
- **Technologie**: `importlib` + Background-Thread

### 3. PROAKTIVES ENVIRONMENT-SENSING
- **Status**: ✅ Aktiv
- **Beschreibung**: Der Daemon scannt das System auf Tools wie `ffmpeg`, `tesseract`, `docker`, `git` und erstellt automatisch HEARTBEAT-Tasks für passende Integrationen.
- **Scan-Intervall**: Alle 5 Minuten

## 🧠 Selbstprogrammierte Integrationen
- **Whisper-Client**: Ich habe gelernt, wie ich eigenständig neue Python-Integrationen programmiere und installiere. Mein erster neuer Skill ist die Audio-Transkription via Whisper.
- **AutoLearn**: Ich kann meine eigenen Fähigkeiten zur Laufzeit erweitern!

## 💻 Erlaubte Shell-Kommandos
- ls/dir, pwd/cd, date, echo, cat/type, git, head, tail, wc
