# GUI Controller Dokumentation

## Übersicht

Der **GUI Controller** ist ein Modul für GABI Gateway, das die Steuerung der Windows-GUI ermöglicht. Es erlaubt GABI, Programme zu öffnen, Mausklicks auszuführen, Screenshots zu machen und Fenster zu verwalten - ideal für Automatisierungsaufgaben.

---

## Features

| Feature | Beschreibung | Anwendung |
|---------|--------------|-----------|
| **Screenshot** | Bildschirmfotos erstellen | Überwachung, Dokumentation |
| **Fenster-Liste** | Alle geöffneten Fenster anzeigen | Übersicht, Navigation |
| **Maus-Klicks** | Klicks an beliebigen Positionen | App-Bedienung, Buttons |
| **App-Start** | Programme über Windows-Suche öffnen | Workflow-Automatisierung |
| **Icon-Erkennung** | Bilderkennung für UI-Elemente | Zuverlässiges Klicken |
| **Multi-Monitor** | Unterstützung für mehrere Bildschirme | Erweiterte Arbeitsflächen |

---

## Voraussetzungen

### Python-Pakete

```bash
pip install pyautogui pygetwindow pillow opencv-python screeninfo
```

| Paket | Zweck |
|-------|-------|
| `pyautogui` | Maus- und Tastatursteuerung |
| `pygetwindow` | Fenster-Informationen |
| `pillow` | Bildverarbeitung (Screenshots) |
| `opencv-python` | Bilderkennung (Template Matching) |
| `screeninfo` | Multi-Monitor-Unterstützung |

### System

- **OS**: Windows 10/11
- **Python**: 3.9+
- **Zugriff**: Desktop-Interaktion erfordert angemeldeten Benutzer

---

## Schnelle Startanleitung

### 1. Controller initialisieren

```python
from integrations.gui_controller import get_gui_controller

# Controller holen
gui = get_gui_controller()

# Verfügbarkeit prüfen
status = gui.check_available()
print(status)
# Ausgabe: {'pyautogui': True, 'opencv': True, 'pillow': True, 'ready': True, ...}
```

### 2. Bildschirmgröße ermitteln

```python
# Einzelner Monitor
result = gui.get_screen_size()
print(result)
# {
#   "success": True,
#   "size": {"width": 1920, "height": 1080},
#   "monitors": [...],
#   "monitor_count": 2
# }
```

### 3. Fenster auflisten

```python
windows = gui.get_window_titles()
for w in windows.get("windows", []):
    print(f"{w['title']}: {w['width']}x{w['height']} @ ({w['left']}, {w['top']})")
```

### 4. Screenshot erstellen

```python
result = gui.screen_capture("mein_screenshot.png")
if result["success"]:
    print(f"Gespeichert: {result['path']}")
```

### 5. Mausklick ausführen

```python
# Einfacher Klick
result = gui.safe_click(500, 300)

# Doppelklick
result = gui.safe_click(500, 300, double=True)

# Rechtsklick
result = gui.safe_click(500, 300, button="right")
```

### 6. Programm öffnen

```python
# Über Windows-Suche
result = gui.win_search_and_open("Notepad")
result = gui.win_search_and_open("Calculator")
```

---

## Multi-Monitor-Setup

### Problem: Fenster auf dem zweiten Monitor werden nicht gefunden

**Lösung:** Der Controller erkennt automatisch alle Monitore.

```python
# Alle Monitore anzeigen
status = gui.check_available()
for m in status.get("monitors", []):
    print(f"Monitor {m['index']}: {m['width']}x{m['height']} @ ({m['x']}, {m['y']})")
    print(f"  Primär: {m['primary']}")

# Beispiel-Ausgabe:
# Monitor 0: 1920x1080 @ (0, 0)     <- Hauptmonitor
# Monitor 1: 1920x1080 @ (1920, 0)  <- Zweiter Monitor (rechts)
```

### Koordinaten-System

- **Monitor 1 (Haupt)**: x=0 bis 1920, y=0 bis 1080
- **Monitor 2 (Rechts)**: x=1920 bis 3840, y=0 bis 1080
- **Monitor 2 (Links)**: x=-1920 bis 0, y=0 bis 1080

```python
# Klick auf dem zweiten Monitor (rechts vom Haupt)
result = gui.safe_click(2000, 500)  # x > 1920 = zweiter Monitor
```

### Fenster-Positionierung

```python
windows = gui.get_window_titles()
for w in windows.get("windows", []):
    # Auf welchem Monitor ist das Fenster?
    if w["left"] >= 1920:
        monitor = "Zweiter Monitor (rechts)"
    elif w["right"] < 0:
        monitor = "Linker Monitor"
    else:
        monitor = "Hauptmonitor"

    print(f"{w['title']} ist auf: {monitor}")
```

---

## Icon-Erkennung (Bildbasierte Steuerung)

### Wozu?

Statt feste Koordinaten zu verwenden (die sich ändern können), sucht GABI nach einem Bild und klickt darauf.

### Anwendung

```python
# Screenshot des Icons speichern als "send_button.png"

# Icon finden und klicken
result = gui.click_icon("templates/send_button.png")

if result["success"]:
    print(f"Geklickt bei: {result['position']}")
else:
    print(f"Icon nicht gefunden: {result['error']}")
```

### Confidence-Level

```python
# Strenger (nur exakte Übereinstimmung)
result = gui.find_icon_on_screen("icon.png", threshold=0.95)

# Lockerer (auch ähnliche Icons)
result = gui.find_icon_on_screen("icon.png", threshold=0.7)
```

---

## Sicherheit

### Blockierte Tastenkombinationen

Zum Schutz vor Fehlern sind folgende Kombinationen blockiert:

- `Alt+F4` - Fenster schließen
- `Win+L` - Windows sperren
- `Ctrl+Alt+Del` - Security-Screen
- `Win+D` - Desktop anzeigen
- `Win+M` - Alle minimieren

### Safety-Override (Nur für Notfälle)

```python
# VORSICHT: Deaktiviert Schutzmechanismen!
gui.enable_security_override()

# Jetzt sind alle Kombinationen erlaubt
gui.press_key("alt+f4")  # Funktioniert jetzt

# Wieder aktivieren
gui.disable_security_override()
```

### Fail-Safe

**WICHTIG:** Bewegen Sie die Maus in eine Bildschirmecke, um alle Aktionen sofort abzubrechen!

---

## Integration mit GABI Gateway

### API-Endpunkte

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/gui/screensize` | GET | Bildschirmgröße |
| `/api/gui/windows` | GET | Fensterliste |
| `/api/gui/screenshot` | POST | Screenshot erstellen |
| `/api/gui/open` | POST | App öffnen |
| `/api/gui/click` | POST | Mausklick |

### Beispiel: HTTP-Request

```python
import requests

# Screenshot erstellen
response = requests.post(
    "http://localhost:8000/api/gui/screenshot",
    headers={"X-API-Key": "dev-key"}
)
print(response.json())
# {"success": True, "path": "screenshots/gui/gui_20260320_151252.png"}

# Fensterliste holen
response = requests.get(
    "http://localhost:8000/api/gui/windows",
    headers={"X-API-Key": "dev-key"}
)
windows = response.json()
```

---

## Dashboard-Anzeige

### Erwartete Ausgabe

```json
{
  "status": "success",
  "controller": "aktiv",
  "screen": {
    "primary": "1920x1080",
    "total": "3840x1080",
    "monitors": 2
  },
  "windows": [
    {"title": "Visual Studio Code", "width": 1200, "height": 800, ...},
    {"title": "Chrome", "width": 1920, "height": 1080, ...}
  ]
}
```

### Fehlerbehebung

| Problem | Ursache | Lösung |
|---------|---------|--------|
| `Bildschirm: ? x ?` | `screeninfo` nicht installiert | `pip install screeninfo` |
| `0 Fenster` | `pygetwindow` nicht installiert | `pip install pygetwindow` |
| Screenshots schwarz | Kein Desktop-Zugriff | Als Benutzer (nicht Service) ausführen |
| Klicks funktionieren nicht | Falsche Koordinaten | Multi-Monitor beachten |

---

## Architektur

### Komponenten-Diagramm

```
┌─────────────────┐
│  GABI Gateway   │
│   Dashboard     │
└────────┬────────┘
         │ HTTP API
         ▼
┌─────────────────┐
│   HTTP API      │
│   (FastAPI)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GUIController   │
│   Klasse        │
└────────┬────────┘
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
┌───────┐ ┌───────┐ ┌──────────┐
│pyauto-│ │  CV2  │ │ pygetwin │
│  gui  │ │OpenCV │ │   dow    │
└───────┘ └───────┘ └──────────┘
```

### Datenfluss

1. **Dashboard** sendet Request an `/api/gui/windows`
2. **HTTP API** ruft `gui.get_window_titles()` auf
3. **GUIController** nutzt `pygetwindow` um Fenster zu listen
4. **Ergebnis** wird als JSON zurückgegeben

---

## Erweiterung: Selbstständige Bedienung

### Vision

GABI soll Programme selbst bedienen können:

1. **Screenshot** machen → UI erkennen
2. **Icons finden** → Buttons/Elemente lokalisieren
3. **Klicken** → Aktionen ausführen
4. **Ergebnis prüfen** → Erfolg verifizieren

### Beispiel-Workflow

```python
# GABI möchte eine E-Mail senden

# 1. Outlook öffnen
gui.win_search_and_open("Outlook")
time.sleep(2)

# 2. "Neue E-Mail"-Button finden
result = gui.click_icon("templates/outlook_new_mail.png")

# 3. Empfänger eingeben
gui.type_text("max@example.com")
gui.press_key("tab")

# 4. Betreff eingeben
gui.type_text("Status-Update")
gui.press_key("tab")

# 5. Text eingeben
gui.type_text("Hallo, hier ist der aktuelle Status...")

# 6. Senden-Button klicken
gui.click_icon("templates/outlook_send.png")
```

### Vorteile

- ✅ **Flexibel** - Funktioniert mit jeder Windows-App
- ✅ **Keine APIs** - Keine Integration nötig
- ✅ **Visuell** - Wie ein menschlicher Benutzer
- ⚠️ **Langsamer** - Bildverarbeitung braucht Zeit
- ⚠️ **Fehleranfällig** - UI-Änderungen brechen Automation

---

## Best Practices

1. **Immer Pausen einbauen** - Apps brauchen Zeit zum Laden
2. **Screenshots verifizieren** - Prüfe vorher/nachher
3. **Templates aktuell halten** - UI-Änderungen aktualisieren
4. **Fail-Safe nutzen** - Maus in Ecke = sofortiger Abbruch
5. **Logging aktivieren** - `logger.info()` für Debug-Info

---

## Troubleshooting

### Problem: "? x ?" im Dashboard

**Ursache:** `screeninfo` nicht installiert oder Exception beim Auslesen

**Lösung:**
```bash
pip install screeninfo
# Neustart des Gateways
```

### Problem: Fenster werden nicht angezeigt

**Ursache:** Code hatte duplizierte Funktionsdefinitionen

**Lösung:** Datei `gui_controller.py` aktualisieren (bereits erledigt)

### Problem: Klicks auf dem falschen Monitor

**Ursache:** Koordinaten beziehen sich auf virtuellen Desktop

**Lösung:**
```python
# Prüfe auf welchem Monitor das Ziel ist
if target_x > 1920:
    print("Ziel ist auf dem rechten Monitor")
```

---

## Zusammenfassung

Der GUI Controller ermöglicht GABI, wie ein Mensch mit Windows zu interagieren:

- **Screenshots** für visuelle Analyse
- **Fenster-Tracking** für Übersicht
- **Maus & Tastatur** für Bedienung
- **Multi-Monitor** für komplexe Setups

Damit kann GABI theoretisch jede Windows-Anwendung bedienen, ohne spezielle APIs oder Integrationen.
