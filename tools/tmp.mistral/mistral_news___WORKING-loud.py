from playwright.sync_api import sync_playwright
import time
import json
from datetime import datetime
import sys
import os
import tempfile
import shutil

# ===== KONFIGURATION =====
HEADLESS_MODE = True
BROWSER_WIDTH = 1920
BROWSER_HEIGHT = 1080
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
TIMEOUT_NAVIGATION = 30000
TIMEOUT_WAIT_ANSWER = 30  # Länger für komplexe Antworten
DEBUG_MODE = False  # False = keine Dateien hinterlassen
TEMP_DIR = None  # Wird nur bei DEBUG_MODE=True gesetzt

# Selektoren
ACCEPT_BUTTON_SELECTORS = [
    "button:has-text('Accept')",
    "button:has-text('Akzeptieren')",
    "button:has-text('I agree')",
    "button:has-text('Zustimmen')",
    "button:has-text('Continue')",
    "button:has-text('Got it')",
    "[aria-label*='accept']",
    ".terms-accept-button",
    "#accept-terms"
]

INPUT_FIELD_SELECTORS = [
    "textarea",
    "input[type='text']",
    "[contenteditable='true']",
    "[role='textbox']",
    ".chat-input",
    "#chat-input",
    ".ProseMirror",
    "[data-testid='chat-input']"
]

ANSWER_SELECTORS = [
    ".message-assistant",
    ".assistant-message",
    "[data-testid='assistant-message']",
    ".prose",
    ".markdown",
    "div.whitespace-pre-wrap",
    ".message-bot",
    ".bot-message",
    ".ai-message"
]

def extract_full_conversation(page):
    """
    Extrahiert die komplette Konversation aus der Seite
    """
    messages = []
    
    # Verschiedene Ansätze für die Extraktion
    try:
        # Versuche alle Nachrichten-Elemente zu finden
        message_containers = page.locator("[class*='message'], [class*='Message'], .group, article").all()
        
        for container in message_containers[-10:]:  # Letzte 10 Nachrichten
            text = container.text_content()
            if text and len(text) > 20:
                # Versuche herauszufinden ob es User oder Assistant ist
                class_name = container.get_attribute("class") or ""
                is_user = "user" in class_name.lower() or "human" in class_name.lower()
                is_assistant = "assistant" in class_name.lower() or "bot" in class_name.lower() or "ai" in class_name.lower()
                
                role = "unknown"
                if is_user:
                    role = "user"
                elif is_assistant:
                    role = "assistant"
                
                messages.append({
                    "role": role,
                    "content": text.strip(),
                    "class": class_name[:50]  # Debug-Info
                })
    except Exception as e:
        print(f"⚠️ Fehler bei Extraktion: {e}")
    
    # Fallback: Einfach alles Textuelle sammeln
    if not messages:
        body_text = page.locator("body").text_content()
        # Versuche sinnvolle Abschnitte zu identifizieren
        paragraphs = [p for p in body_text.split("\n\n") if len(p) > 100]
        for p in paragraphs:
            messages.append({
                "role": "unknown",
                "content": p.strip()
            })
    
    return messages

def cleanup():
    """Räumt temporäre Dateien auf"""
    if TEMP_DIR and os.path.exists(TEMP_DIR):
        try:
            shutil.rmtree(TEMP_DIR)
            print("🧹 Temporäre Dateien gelöscht")
        except:
            pass

def get_mistral_response(query):
    """
    Hauptfunktion: Fragt Mistral und gibt JSON mit der Antwort zurück
    """
    global TEMP_DIR
    
    if DEBUG_MODE:
        TEMP_DIR = tempfile.mkdtemp(prefix="mistral_debug_")
        print(f"📁 Debug-Dateien in: {TEMP_DIR}")
    
    result = {
        "success": False,
        "query": query,
        "response": None,
        "conversation": [],
        "timestamp": datetime.now().isoformat(),
        "error": None
    }
    
    start_time = time.time()
    
    with sync_playwright() as p:
        browser = None
        try:
            # Browser mit temporärem Profil starten
            browser = p.chromium.launch(
                headless=HEADLESS_MODE,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            context = browser.new_context(
                viewport={'width': BROWSER_WIDTH, 'height': BROWSER_HEIGHT},
                user_agent=USER_AGENT,
                locale='de-DE'
            )
            
            # Automation verstecken
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = context.new_page()
            
            # Navigation
            print("🌐 Navigiere zu Mistral Chat...")
            page.goto("https://chat.mistral.ai", wait_until="networkidle", timeout=TIMEOUT_NAVIGATION)
            time.sleep(2)
            
            # Nutzungsbedingungen akzeptieren
            print("🔍 Akzeptiere Nutzungsbedingungen...")
            for selector in ACCEPT_BUTTON_SELECTORS:
                try:
                    button = page.locator(selector).first
                    if button.is_visible(timeout=2000):
                        button.click()
                        print(f"✅ Akzeptiert")
                        time.sleep(2)
                        break
                except:
                    continue
            
            # Frage eingeben
            print(f"📝 Frage: {query[:100]}...")
            input_found = False
            
            for selector in INPUT_FIELD_SELECTORS:
                try:
                    input_field = page.locator(selector).first
                    if input_field.is_visible(timeout=2000):
                        input_field.click()
                        input_field.fill(query)
                        input_field.press("Enter")
                        print(f"✅ Frage gesendet")
                        input_found = True
                        break
                except:
                    continue
            
            if not input_found:
                # Fallback: URL-Parameter
                page.goto(f"https://chat.mistral.ai/chat?q={query}", wait_until="networkidle")
            
            # Auf Antwort warten
            print(f"⏳ Warte auf Antwort...")
            
            # Progressiv warten und nach Antwort suchen
            max_wait = TIMEOUT_WAIT_ANSWER
            conversation = []
            last_length = 0
            stable_count = 0  # Zählt wie oft die Antwort gleich bleibt
            
            for i in range(max_wait):
                time.sleep(1)
                
                # Konversation extrahieren
                current_msgs = extract_full_conversation(page)
                if current_msgs:
                    conversation = current_msgs
                    
                    # Prüfen ob neue Nachrichten da sind
                    current_len = len(str(conversation))
                    if current_len > last_length + 50:
                        print(f"   Antwort wird länger... ({i+1}s)")
                        last_length = current_len
                        stable_count = 0
                    else:
                        stable_count += 1
                    
                    # Letzte Assistent-Nachricht finden
                    assistant_msgs = [m for m in conversation if m["role"] == "assistant"]
                    if assistant_msgs:
                        latest = assistant_msgs[-1]["content"]
                        # Wenn Antwort groß genug UND stabil (3 Sekunden keine Änderung)
                        if len(latest) > 300 and stable_count >= 3:
                            print(f"✅ Antwort erhalten ({len(latest)} Zeichen)")
                            break
                        
                        # Oder wenn sehr groß (wahrscheinlich vollständig)
                        if len(latest) > 1000:
                            print(f"✅ Umfangreiche Antwort erhalten ({len(latest)} Zeichen)")
                            break
            
            # Letzte Assistent-Nachricht als Hauptantwort
            assistant_msgs = [m for m in conversation if m["role"] == "assistant"]
            if assistant_msgs:
                result["response"] = assistant_msgs[-1]["content"]
            elif conversation:
                # Fallback: Letzte Nachricht
                result["response"] = conversation[-1]["content"]
            
            result["conversation"] = conversation
            result["success"] = result["response"] is not None
            
            # Debug-Dateien nur wenn gewünscht
            if DEBUG_MODE and TEMP_DIR:
                debug_file = os.path.join(TEMP_DIR, f"debug_{datetime.now().strftime('%H%M%S')}.html")
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(page.content())
                
                screenshot = os.path.join(TEMP_DIR, f"screenshot_{datetime.now().strftime('%H%M%S')}.png")
                page.screenshot(path=screenshot)
        
        except Exception as e:
            result["error"] = str(e)
            print(f"❌ Fehler: {e}")
        
        finally:
            if browser:
                browser.close()
            
            result["execution_time"] = round(time.time() - start_time, 2)
    
    # Cleanup
    if not DEBUG_MODE:
        cleanup()
    
    return result

def main():
    # Query aus Kommandozeile
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "Erkläre mir die neuesten Durchbrüche im Bereich Large Language Models"
    
    print(f"\n🚀 Starte Anfrage an Mistral...")
    print("="*60)  # Korrigiert: f= entfernt
    
    # Mistral befragen
    result = get_mistral_response(query)
    
    # JSON ausgeben
    print(f"\n📊 JSON-AUSGABE:\n")
    json_output = json.dumps(result, ensure_ascii=False, indent=2)
    print(json_output)
    
    # Antwort extra anzeigen
    if result["success"] and result["response"]:
        print(f"\n💬 EXTRAHIERTE ANTWORT:\n")
        print(result["response"])
        
        # Optional: In Datei speichern
        save_to_file = input(f"\n💾 Antwort in Datei speichern? (j/N): ").lower()
        if save_to_file == 'j':
            filename = f"mistral_antwort_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(json_output)
            print(f"✅ Gespeichert als: {filename}")
    else:
        print(f"\n❌ Keine Antwort erhalten")
        if result["error"]:
            print(f"Fehler: {result['error']}")

if __name__ == "__main__":
    main()