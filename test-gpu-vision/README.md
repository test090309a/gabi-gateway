# 🤖 GABI - GPU-Accelerated Bot Interface


![GABI Logo](https://via.placeholder.com/150/4CAF50/ffffff?text=GABI)

**Automatisiere Windows-Programme mit GPU-beschleunigter Bilderkennung**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![CUDA Support](https://img.shields.io/badge/CUDA-enabled-green)](https://developer.nvidia.com/cuda-toolkit)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)](https://github.com/yourusername/gabi)

</div>

## 📋 Inhaltsverzeichnis
- [Über GABI](#-über-gabi)
- [Features](#-features)
- [Systemanforderungen](#-systemanforderungen)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Trainings-Methoden](#-trainings-methoden)
- [Test-Modi](#-test-modi)
- [Automation-Typen](#-automation-typen)
- [Tastaturkürzel](#-tastaturkürzel)
- [Projektstruktur](#-projektstruktur)
- [Beispiele](#-beispiele)
- [Fehlerbehebung](#-fehlerbehebung)
- [FAQ](#-faq)
- [Mitwirken](#-mitwirken)
- [Lizenz](#-lizenz)

## 🎯 Über GABI

**GABI** (GPU-Accelerated Bot Interface) ist ein leistungsstarkes Tool zur Automatisierung von Windows-Anwendungen durch GPU-beschleunigte Bilderkennung. Im Gegensatz zu herkömmlichen Automatisierungstools, die auf Koordinaten oder feste Positionen angewiesen sind, erkennt GABI visuelle Elemente unabhängig von ihrer Position auf dem Bildschirm.

### 🔥 Hauptvorteile
- **GPU-Beschleunigt** - Blitzschnelle Erkennung durch CUDA
- **Positionsunabhängig** - Findet Elemente überall auf dem Bildschirm
- **Visuelles Training** - Zeige einmal, erkenne immer
- **Vielfältige Automation** - Von einfachen Klicks bis zu komplexen Workflows
- **Benutzerfreundlich** - Komplette GUI für Training, Test und Automation

## ✨ Features

### 🎓 **Training (5 Methoden)**
- **Manuell** - Präzises Training durch Maus-Zielen
- **Grid-Scan** - Automatische Rastererkennung (ideal für Taschenrechner, Keypads)
- **Batch** - Mehrere Programme nacheinander trainieren
- **Rechteck** - Bereich aufziehen und benennen
- **Schnellaufnahme** - Automatische Aufnahme alle 2 Sekunden

### 🧪 **Test & Validierung**
- Einzeltest mit Wiederholungen
- Sequenz-Test kompletter Abläufe
- Batch-Test aller Elemente
- Performance-Test mit Zeitmessung
- Export als JSON-Report
- Live-Statistiken

### 🤖 **Automation (5 Typen)**
- **Sequenzen** - Schritt-für-Schritt Abläufe
- **Rezepte** - Komplexe, wiederverwendbare Workflows
- **Watchdog** - Automatische Reaktion auf Bildschirmereignisse
- **Batch** - Mehrere Aufgaben nacheinander
- **Scheduler** - Zeitgesteuerte Ausführung

### 🖥️ **GUI-Features**
- Live-Maus-Tracking
- Echtzeit-Vorschau
- Fortschrittsanzeige
- Detaillierte Logs
- Import/Export (CSV, JSON)
- Kontextsensitive Hilfe
- Tastaturkürzel

## 💻 Systemanforderungen

### **Minimal**
- Windows 10 (64-bit)
- Python 3.8 oder höher
- 4 GB RAM
- 500 MB freier Festplattenspeicher

### **Empfohlen**
- Windows 11 (64-bit)
- NVIDIA GPU mit CUDA-Support (für GPU-Beschleunigung)
- 8 GB RAM
- SSD mit 1 GB freiem Speicher

### **Unterstützte Python-Versionen**
- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11

## 📦 Installation

### 1. Python installieren (falls nicht vorhanden)
```bash
# Prüfe ob Python installiert ist
python --version

# Download unter: https://www.python.org/downloads/
2. Repository klonen
bash
git clone https://github.com/yourusername/gabi.git
cd gabi
3. Abhängigkeiten installieren
bash
# Mit pip (empfohlen)
pip install -r requirements.txt

# Oder mit conda
conda create -n gabi python=3.9
conda activate gabi
pip install -r requirements.txt
4. CUDA-Support (optional, aber empfohlen)
bash
# Prüfe ob CUDA verfügbar ist
python -c "import torch; print(torch.cuda.is_available())"

# Falls False: Installiere CUDA von https://developer.nvidia.com/cuda-toolkit
5. GABI starten
bash
python gabi_training_center.py
🚀 Quick Start
Taschenrechner automatisieren in 5 Minuten
Schritt 1: Modul erstellen
Starte gabi_training_center.py

Gehe zu Training → Modul-Management

Klicke auf ➕ Neu und gib "calc" ein

Schritt 2: Elemente definieren
python
# In der Elemente-Liste folgende Namen eintragen:
7, 8, 9, plus, minus, gleich
Schritt 3: Training starten
Wähle Manuell als Trainings-Methode

Klicke ▶️ Training starten

Öffne den Windows Taschenrechner

Fahre mit der Maus über die '7' und drücke S

Wiederhole für alle Elemente

Schritt 4: Testen
Gehe zu Test & Validierung

Wähle Sequenz-Test

Gib ein: 7, plus, 8, gleich

Klicke ▶️ Test starten

GABI sollte jetzt automatisch rechnen!

Schritt 5: Automatisieren
Gehe zu Automation → Sequenz

Erstelle die Schritte (Klick auf 7, plus, 8, gleich)

Stelle Wiederholungen ein (z.B. 10x)

Starte die Automation

🎓 Trainings-Methoden im Detail
1. Manuell (Empfohlen für Einsteiger)
text
┌─────────────────────────────────────┐
│  ✅ Vorteile:                       │
│  • Sehr präzise                     │
│  • Funktioniert für alle Programme  │
│  • Sofortiges Feedback               │
│                                     │
│  ⚠️ Nachteile:                       │
│  • Zeitaufwendig bei vielen Elementen│
└─────────────────────────────────────┘
2. Grid-Scan (Ideal für regelmäßige Layouts)
text
┌─────────────────────────────────────┐
│  ✅ Ideal für:                       │
│  • Taschenrechner                    │
│  • Zahlenblöcke                      │
│  • Menüleisten                       │
│                                     │
│  🔧 Parameter:                       │
│  • Zeilen: 4                         │
│  • Spalten: 3                        │
│  • Start-Button: '7'                 │
└─────────────────────────────────────┘
3. Batch (Für Power-User)
Trainiere mehrere Module in einem Durchlauf

Perfekt für große Projekte

Automatische Ordnerstruktur

4. Rechteck (Für große Elemente)
Ziehe ein Rechteck um das Element

Ideal für Fenster, Dialoge, große Buttons

5. Schnellaufnahme (Für viele ähnliche Elemente)
Automatische Aufnahme alle 2 Sekunden

Einfach durch die Elemente klicken

🧪 Test-Modi
Modus	Beschreibung	Typische Anwendung
Einzeltest	Testet ein Element mehrfach	Erkennungsqualität prüfen
Sequenz-Test	Testet kompletten Workflow	Ablauf validieren
Batch-Test	Testet alle Elemente	Vollständigkeit prüfen
Performance	Misst Geschwindigkeit	Optimierung
🤖 Automation-Typen
📋 Sequenzen
yaml
Beispiel: Taschenrechner
1. Klick auf '7'
2. Klick auf 'plus'  
3. Klick auf '8'
4. Klick auf 'gleich'
5. Warte 2 Sekunden
6. Screenshot 'ergebnis.png'
👀 Watchdog
yaml
Überwachung: Bildschirmbereich
Ereignis: "OK" Button erscheint
Aktion: Automatisch klicken
⏰ Scheduler
yaml
Job: "Täglicher Bericht"
Zeit: 09:00 Uhr
Wiederholung: Täglich
Aktion: Excel öffnen, Daten aktualisieren, speichern
⌨️ Tastaturkürzel
Globale Shortcuts
Taste	Funktion
F1	Hilfe öffnen
Strg+Q	Programm beenden
Strg+S	Konfiguration speichern
Training
Taste	Funktion
S	Element speichern
Esc	Training abbrechen
Leertaste	Pause/Fortsetzen
Test
Taste	Funktion
Strg+T	Test starten
Strg+R	Report exportieren
F5	Templates neu laden
Automation
Taste	Funktion
Strg+A	Automation starten
Strg+P	Pause
Strg+X	Stop
📁 Projektstruktur
text
gabi/
├── 📄 gabi_training_center.py    # Hauptprogramm mit GUI
├── 📄 gpu_screenshot.py           # GPU-beschleunigte Screenshots
├── 📄 gui_controller.py           # Windows GUI-Steuerung
├── 📄 requirements.txt             # Python-Abhängigkeiten
├── 📄 README.md                    # Diese Datei
├── 📄 LICENSE                      # MIT-Lizenz
│
├── 📁 assets/                      # Trainingsdaten
│   ├── 📁 calc/                    # Taschenrechner-Modul
│   │   ├── 🖼️ btn_7.png
│   │   ├── 🖼️ btn_8.png
│   │   ├── 🖼️ btn_plus.png
│   │   └── ...
│   └── 📁 excel/                    # Excel-Modul
│       ├── 🖼️ btn_neu.png
│       └── ...
│
├── 📁 sequences/                    # Gespeicherte Sequenzen
│   ├── 📄 calc_basic.json
│   └── 📄 excel_report.json
│
├── 📁 reports/                      # Test-Reports
│   └── 📄 test_report_20240219.json
│
└── 📁 screenshots/                   # Automatische Screenshots
    └── 📄 screenshot_20240219.png
📚 Beispiele
Beispiel 1: Taschenrechner automatisieren
python
# Berechnung: 7 + 8 * 9 - 3 = ?
sequence = [
    ("click", "7"),
    ("click", "plus"),
    ("click", "8"),
    ("click", "mal"),
    ("click", "9"),
    ("click", "minus"),
    ("click", "3"),
    ("click", "gleich"),
    ("wait", "2"),
    ("screenshot", "ergebnis.png")
]
Beispiel 2: Excel-Bericht erstellen
python
# Täglichen Bericht automatisieren
sequence = [
    ("open", "excel"),
    ("click", "neu"),
    ("type", "Umsatz Januar"),
    ("click", "speichern"),
    ("type", "umsatz_januar.xlsx"),
    ("click", "ok")
]
Beispiel 3: Watchdog für Popups
python
watchdog = {
    "name": "Popup-Killer",
    "watch": "Bildschirm",
    "event": "OK Button erscheint",
    "action": "click",
    "active": True
}
🔧 Fehlerbehebung
Häufige Probleme
❌ "Kein CUDA-Gerät gefunden"
bash
# Lösung 1: CPU-Modus verwenden (automatisch)
# Lösung 2: CUDA installieren
nvcc --version  # Prüfe CUDA-Installation
❌ "Template nicht gefunden"
bash
# Lösung: Trainiere das Element neu
# Stelle sicher, dass das Element sichtbar ist
# Prüfe den assets/[modul] Ordner
❌ "ImportError: No module named 'tkinter'"
bash
# Linux:
sudo apt-get install python3-tk

# Windows: Python mit tkinter installieren
# (Standardmäßig dabei)
❌ "Permission denied" bei Mausklicks
bash
# Als Administrator ausführen
# Oder: pyautogui.FAILSAFE = True in gui_controller.py
❓ FAQ
Allgemein
F: Ist GABI kostenlos?
A: Ja, GABI ist Open Source unter der MIT-Lizenz.

F: Brauche ich eine NVIDIA GPU?
A: Nein, GABI funktioniert auch ohne GPU (dann aber langsamer).

F: Kann ich GABI für Spiele verwenden?
A: Ja, solange das Spiel im Fenster-Modus läuft.

Training
F: Wie viele Elemente kann ich trainieren?
A: Unbegrenzt! Die GPU-Erkennung bleibt auch bei tausenden Templates schnell.

F: Kann ich trainierte Elemente teilen?
A: Ja, einfach den assets/[modul] Ordner kopieren.

F: Was ist der beste Threshold?
A: Für die meisten Anwendungen ist 0.8 optimal. Teste verschiedene Werte.

Automation
F: Kann ich mehrere Programme gleichzeitig automatisieren?
A: Ja, mit der Batch-Funktion werden Aufgaben nacheinander ausgeführt.

F: Funktioniert GABI auch im Hintergrund?
A: Ja, der Watchdog und Scheduler laufen im Hintergrund.

F: Wie mache ich ein Backup?
A: Einfach den gesamten assets Ordner und die sequences Ordner kopieren.

🤝 Mitwirken
Beiträge sind willkommen! So kannst du helfen:

Fork das Repository

Erstelle einen Feature-Branch (git checkout -b feature/AmazingFeature)

Commit deine Änderungen (git commit -m 'Add some AmazingFeature')

Push zum Branch (git push origin feature/AmazingFeature)

Öffne eine Pull Request

Entwicklungsumgebung einrichten
bash
# Repository klonen
git clone https://github.com/yourusername/gabi.git
cd gabi

# Virtual Environment erstellen
python -m venv venv
venv\Scripts\activate  # Windows

# Entwicklungs-Abhängigkeiten
pip install -r requirements-dev.txt
📄 Lizenz
Dieses Projekt ist unter der MIT-Lizenz lizenziert - siehe LICENSE Datei für Details.

text
MIT License

Copyright (c) 2024 GABI Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files...
🙏 Danksagungen
PyAutoGUI - Für die zuverlässige GUI-Steuerung

OpenCV - Für die Bildverarbeitung

PyTorch - Für GPU-Beschleunigung

Pillow - Für Bildbearbeitung

Tkinter - Für die GUI

📞 Kontakt & Support
Issues: GitHub Issues

Discussions: GitHub Discussions

Email: support@gabi-bot.com

Made with ❤️ for the automation community