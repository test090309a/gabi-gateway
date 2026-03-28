# test_selenium_direct.py
"""Direkter Selenium-Test mit garantierter Browser-Schließung"""

import time
import signal
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options

# Globale Referenz für Cleanup
driver = None

def cleanup():
    """Sauberes Schließen des Browsers"""
    global driver
    print("\n🧹 Cleanup: Schließe Browser...")
    if driver:
        try:
            driver.quit()
            print("✅ Browser geschlossen")
        except Exception as e:
            print(f"⚠️ Fehler beim Schließen: {e}")
    sys.exit(0)

# Signal-Handler für Ctrl+C
signal.signal(signal.SIGINT, lambda sig, frame: cleanup())
signal.signal(signal.SIGTERM, lambda sig, frame: cleanup())

print("🔍 Starte direkten Selenium-Test...")

try:
    # Chrome-Optionen
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    print("🌐 Starte Chrome...")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(15)
    driver.implicitly_wait(5)
    
    print("🌐 Lade Startpage...")
    driver.get("https://www.startpage.com")
    
    # Kurze Wartezeit
    time.sleep(2)
    
    print("\n🔍 Suche nach dem Suchfeld...")
    
    # Versuche verschiedene Selektoren mit WebDriverWait
    selectors = [
        "input[type='text']",
        "input[name='q']",
        "input[type='search']",
        "#q",
        ".search-form-input"
    ]
    
    search_input = None
    for selector in selectors:
        try:
            elem = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            print(f"  ✅ Gefunden mit: {selector}")
            print(f"     Name: {elem.get_attribute('name')}")
            print(f"     ID: {elem.get_attribute('id')}")
            print(f"     Class: {elem.get_attribute('class')}")
            search_input = elem
            break
        except TimeoutException:
            print(f"  ❌ Nicht gefunden: {selector}")
        except Exception as e:
            print(f"  ⚠️ Fehler bei {selector}: {e}")
    
    if search_input:
        # Suchbegriff eingeben
        search_term = "wetter in wien"
        print(f"\n📝 Gebe Suchbegriff ein: {search_term}")
        search_input.clear()
        search_input.send_keys(search_term)
        
        # Suche absenden
        print("⏎ Suche absenden...")
        search_input.submit()
        
        print("⏳ Warte auf Ergebnisse (max 10 Sekunden)...")
        
        # Warte auf Ergebnisse mit Timeout
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".result, .w-gl__result"))
            )
            print("✅ Ergebnisse gefunden!")
            
            # Extrahiere erste paar Ergebnisse
            results = driver.find_elements(By.CSS_SELECTOR, ".result, .w-gl__result")
            print(f"\n📊 {len(results)} Ergebnisse gefunden:")
            for i, result in enumerate(results[:5], 1):
                try:
                    title_elem = result.find_element(By.CSS_SELECTOR, "h3, .result__title")
                    title = title_elem.text[:80]
                    print(f"  {i}. {title}")
                except:
                    print(f"  {i}. [Kein Titel]")
                    
        except TimeoutException:
            print("⚠️ Timeout beim Warten auf Ergebnisse")
            # Screenshot für Debug
            try:
                driver.save_screenshot("debug_no_results.png")
                print("📸 Debug-Screenshot: debug_no_results.png")
            except:
                pass
    
    else:
        print("❌ Kein Suchfeld gefunden!")
        # Screenshot für Debug
        try:
            driver.save_screenshot("debug_no_searchfield.png")
            print("📸 Debug-Screenshot: debug_no_searchfield.png")
        except:
            pass
    
    print("\n" + "=" * 50)
    print("✅ Test abgeschlossen")
    print("Browser wird in 5 Sekunden geschlossen...")
    print("Drücke Ctrl+C für sofortiges Schließen")
    print("=" * 50)
    
    # Kurze Pause mit try/except für Cleanup
    try:
        for i in range(5, 0, -1):
            print(f"  {i}...", end=" ", flush=True)
            time.sleep(1)
        print()
    except KeyboardInterrupt:
        pass
    
except WebDriverException as e:
    print(f"\n❌ WebDriver Fehler: {e}")
    
except Exception as e:
    print(f"\n❌ Fehler: {e}")
    import traceback
    traceback.print_exc()

finally:
    # ===== GARANTIERTE BEREINIGUNG =====
    cleanup()