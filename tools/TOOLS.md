# Tools-Verzeichnis für OpenClaw

Dieses Verzeichnis enthält alle verfügbaren Tools und Skills für OpenClaw.

## 📁 Verzeichnisstruktur
C:\Users\i2u5h.openclaw\workspace\tools
├── mistral_tool.py # Mistral AI Tool (Hauptskript)
├── mistral_tool.md # Mistral AI Dokumentation
├── SKILL.md # Mistral AI Skill-Erkennung
├── TOOLS.md # Diese Datei - Tools-Übersicht
│
├── web_search.py # Web Search Tool
├── web_search.md # Web Search Dokumentation
├── web-search.yaml # Web Search Konfiguration
│
├── web_scraper.py # Web Scraper Tool
│
├── gog.py # GOG Tool
│
├── search_fixer.py # Search Fixer Tool
│
├── tmp/ # Temporäre Dateien (kann gelöscht werden)
└── tmp.mistral/ # Mistral temporär (kann gelöscht werden)

text

## 🔧 Verfügbare Tools

### 🤖 Mistral AI Tool (`mistral_tool.py`)
Fragt Mistral AI Chat und liefert Antworten als JSON.
- **Befehl**: `!mistral-tool <frage>`
- **Dokumentation**: `mistral_tool.md`
- **Status**: ✅ Aktiv

### 🌐 Web Search (`web_search.py`)
Durchsucht das Web nach Informationen.
- **Befehl**: `!web-search <suchbegriff>`
- **Dokumentation**: `web-search.md`
- **Status**: ✅ Aktiv

### 📄 Web Scraper (`web_scraper.py`)
Extrahiert Inhalte von Webseiten.
- **Befehl**: `!web-scraper <url>`
- **Status**: ✅ Aktiv

### 🎮 GOG Tool (`gog.py`)
Tool für GOG (Good Old Games) Integration.
- **Befehl**: `!gog <befehl>`
- **Status**: ✅ Aktiv

### 🔧 Search Fixer (`search_fixer.py`)
Repariert und optimiert Suchanfragen.
- **Befehl**: `!search-fixer <suchbegriff>`
- **Status**: ✅ Aktiv

## 🚀 Neue Tools hinzufügen

Um ein neues Tool zu OpenClaw hinzuzufügen:

1. **Tool-Datei erstellen**: `mein_tool.py`
2. **Dokumentation**: `mein_tool.md`
3. **Skill-Erkennung**: `SKILL.md` (für das Tool)
4. **In dieser Datei eintragen**: Abschnitt oben aktualisieren
5. **In config.yaml eintragen**: Unter `skills.entries`
6. **OpenClaw neu starten**

## ⚙️ Konfiguration in OpenClaw

Die Tools werden in der `config.yaml` konfiguriert:

```yaml
skills:
  entries:
    mistral-tool:
      enabled: true
      env:
        SCRIPT_PATH: "C:\\Users\\i2u5h\\.openclaw\\workspace\\tools\\mistral_tool.py"
        PYTHON_EXE: "python"
    
    web-search:
      enabled: true
      env:
        SCRIPT_PATH: "C:\\Users\\i2u5h\\.openclaw\\workspace\\tools\\web_search.py"
        PYTHON_EXE: "python"
    
    # ... weitere Tools