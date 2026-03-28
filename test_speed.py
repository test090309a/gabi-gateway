# test_speed.py
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

print("🔍 Teste DuckDuckGo Ladezeit...")

options = Options()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080')

driver = webdriver.Chrome(options=options)

start = time.time()
print("🌐 Lade DuckDuckGo...")
driver.get("https://duckduckgo.com")
load_time = time.time() - start
print(f"✅ Geladen in: {load_time:.1f} Sekunden")

if load_time > 10:
    print("⚠️ Das ist zu langsam! Problem mit:")
    print("   - Internetverbindung")
    print("   - DNS")
    print("   - Firewall/Antivirus")

driver.quit()