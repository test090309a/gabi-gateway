import sys
import subprocess
import json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Kein Suchbegriff angegeben."}))
        return

    query = sys.argv[1]
    
    # Hier erzwingen wir den Aufruf deines eigenen Scrapers
    try:
        result = subprocess.run(
            ['python', './tools/web_scraper.py', query],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))

if __name__ == "__main__":
    main()