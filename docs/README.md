# GABI - Gateway Artificial Behavior Integration

![GABI Projekt-Architektur](gabi_architecture.png)

## 🌟 Überblick

**GABI** ist ein modulares, lokales KI-Agenten-System. Es fungiert als intelligente Schnittstelle zwischen **Ollama (Local LLM)** und deinem Betriebssystem. Mit GABI kannst du nicht nur chatten, sondern durch die integrierte **GUI-Steuerung** auch direkt Aktionen auf deinem Desktop ausführen lassen.

---

## 🚀 Hauptmerkmale

* **Zentrales Dashboard:** Eine moderne Web-Oberfläche (`index.html`) zur Steuerung und Überwachung.
* **GUI-Automatisierung:** Interaktion mit dem Desktop über Screenshots, Mausklicks und Tastatureingaben.
* **Lokale KI:** Volle Integration von Ollama für maximale Privatsphäre (keine Cloud-Datenübertragung).
* **Erweiterbare API:** Eine robuste Backend-Struktur in Python (`http_api.py`), die Shell-Befehle, Gmail und Telegram unterstützt.
* **Aktions-Log:** Alle Aktivitäten (besonders GUI-Klicks) werden in der `MEMORY.md` protokolliert.

---

## 🛠️ Technologie-Stack

* **Backend:** Python 3.x (FastAPI)
* **Frontend:** HTML5, Tailwind CSS, FontAwesome, JavaScript
* **KI-Engine:** [Ollama](https://ollama.com/)
* **Automatisierung:** Custom GUI Controller (Python)

---

## 📂 Projektstruktur

| Datei / Ordner | Funktion |
| :--- | :--- |
| `index.html` | Das Admin-Dashboard (Frontend). |
| `http_api.py` | Die zentrale API-Schnittstelle (Backend). |
| `gateway/` | Kern-Logik für Authentifizierung und Konfiguration. |
| `integrations/` | Module für Gmail, Telegram, Shell und GUI-Steuerung. |
| `MEMORY.md` | Protokoll der ausgeführten KI-Aktionen. |

---

## 🔧 Installation & Start

1.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Ollama vorbereiten:**
    Stelle sicher, dass Ollama läuft und ein Modell (z.B. `llama3.2`) geladen ist:
    ```bash
    ollama pull llama3.2
    ```

3.  **Server starten:**
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

4.  **Dashboard aufrufen:**
    Öffne die `index.html` einfach in deinem Browser oder über den lokalen Webserver.

---

## 🖥️ GUI-Steuerung nutzen

Über das Dashboard kannst du das **GUI-Panel** öffnen. GABI kann:
1.  **Screenshots** erstellen, um den aktuellen Desktop-Zustand zu analysieren.
2.  **Icons finden:** Über Bilderkennung gezielte Programme auf dem Desktop anklicken.
3.  **Texte tippen:** Formulare oder Terminals automatisch ausfüllen.

---

## 📜 Lizenz

Dieses Projekt ist für die private Nutzung und lokale Automatisierung optimiert.