# GABI Skills & Fähigkeiten

## 🚀 Autonomes Selbsterweiterungs-System (v1.1.0)
GABI kann nun ihre eigene API zur Laufzeit erweitern!

### ✨ Neue Autonome Fähigkeiten (Februar 2026)
- **Self-Correction Loop**: Automatische Fehleranalyse und -korrektur bei Security-Score < 80 oder Testfehlern (bis zu 3 Iterationen)
- **Dynamisches Hot-Reloading**: Neue Integrationen im `/integrations/` Ordner werden automatisch erkannt und als FastAPI-Routen registriert ohne Neustart
- **Proaktives Environment-Sensing**: Scannt das System nach Tools (ffmpeg, tesseract, docker, etc.) und erstellt automatisch Tasks für passende Integrationen
- **Voice-Integration**: Vollständiger /api/voice/transcribe Endpoint für Audio-Transkription

## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Auto-Exploration**: Selbstständige Systemerkundung bei Inaktivität
- **Chat-Archiv**: Speichert und verwaltet Chat-Verläufe
- **Whisper**: Audio-Transkription (Sprach-zu-Text)

## 💻 Erlaubte Shell-Kommandos
- ls/dir, pwd/cd, date, echo, cat/type, git, head, tail, wc, systeminfo, whoami, netstat

## 🔄 Self-Correction Loop Details
Der Self-Correction Loop in der SkillFactory funktioniert wie folgt:
1. Generiere Integration + Tests
2. Führe Tests aus
3. Prüfe Security-Score (Minimum: 80)
4. Bei Fehlern: Analysiere Fehler, korrigiere Code automatisch
5. Wiederhole bis max. 3 Iterationen erreicht
6. Bei Erfolg: Dokumentiere in AUTOLEARN.md und lade Modul dynamisch

## 📡 Dynamische API-Erweiterung
Wenn eine neue .py Datei in `/integrations/` erstellt wird:
1. Der Integration-Watcher scannt alle 5 Sekunden das Verzeichnis
2. Neue/geänderte Dateien werden mit importlib importiert
3. Gefundene FastAPI-Router werden automatisch registriert
4. Kein Server-Neustart erforderlich!
