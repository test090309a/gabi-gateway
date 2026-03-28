# test_selenium_direct.py
"""Direkter Selenium-Test ohne Gateway-Importe"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

print("🔍 Starte direkten Selenium-Test...")

# Chrome-Optionen
options = Options()
# options.add_argument('--headless')  # Auskommentiert für sichtbaren Browser
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080')

print("🌐 Starte Chrome...")
driver = webdriver.Chrome(options=options)

try:
    print("🌐 Lade Startpage...")
    driver.get("https://www.startpage.com")
    
    time.sleep(3)
    
    print("\n🔍 Suche nach dem Suchfeld...")
    
    # Versuche verschiedene Selektoren
    selectors = [
        "input[name='q']",
        "input[type='search']",
        "input[type='text']",
        "form input",
        "input"
    ]
    
    search_input = None
    for selector in selectors:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            print(f"  ✅ Gefunden mit: {selector}")
            print(f"     Name: {elem.get_attribute('name')}")
            print(f"     ID: {elem.get_attribute('id')}")
            print(f"     Class: {elem.get_attribute('class')}")
            search_input = elem
            break
        except:
            print(f"  ❌ Nicht gefunden: {selector}")
    
    if search_input:
        # Suchbegriff eingeben
        search_term = "wetter in wien"
        print(f"\n📝 Gebe Suchbegriff ein: {search_term}")
        search_input.clear()
        search_input.send_keys(search_term)
        
        # Suche absenden
        print("⏎ Suche absenden...")
        search_input.submit()
        
        print("⏳ Warte auf Ergebnisse...")
        time.sleep(5)
        
        # Prüfe ob Ergebnisse da sind
        page_text = driver.page_source.lower()
        if "wetter" in page_text or "wien" in page_text:
            print("✅ Ergebnisse gefunden!")
        else:
            print("⚠️ Keine Ergebnisse sichtbar")
    else:
        print("❌ Kein Suchfeld gefunden!")
    
    print("\n📸 Browser bleibt offen für 30 Sekunden...")
    print("Du kannst jetzt manuell suchen oder die Seite inspizieren.")
    time.sleep(30)
    
finally:
    print("\n🔚 Schließe Browser...")
    driver.quit()
    print("✅ Done")