import os
import pyautogui
import keyboard
from PIL import Image

def gabi_universal_trainer():
    print("🎓 GABI Universal-Trainer")
    print("-------------------------")
    
    # 1. Ziel-Modul abfragen
    modul_name = input("Welches Programm/Modul möchtest du trainieren? (z.B. calc, excel, browser): ").strip()
    target_dir = f"assets/{modul_name}/"
    os.makedirs(target_dir, exist_ok=True)
    
    # 2. Tasten abfragen
    print("\nGib die Namen der Elemente ein, die GABI lernen soll (getrennt durch Komma).")
    print("Beispiel: login_button, username_field, submit")
    eingabe = input("Elemente: ")
    elemente = [e.strip() for e in eingabe.split(",")]

    print(f"\n🚀 Starte Training für [{modul_name}]")
    print("Anleitung: Maus auf das Element führen und 'S' drücken zum Speichern.")
    print("-------------------------------------------------------------------\n")

    for item in elemente:
        print(f"🎯 Bitte ziele auf: [{item}] und drücke 'S'...")
        
        # Warte auf Tastendruck 'S'
        keyboard.wait('s')
        
        x, y = pyautogui.position()
        
        # Aufnahme eines 60x60 Bereichs um die Maus
        screenshot = pyautogui.screenshot(region=(x-30, y-30, 60, 60))
        
        filename = f"btn_{item}.png"
        path = os.path.join(target_dir, filename)
        screenshot.save(path)
        
        print(f"✅ Erfasst: {path} bei ({x}, {y})")
        
        # Entprellen: Kurz warten, bis 'S' losgelassen wurde
        while keyboard.is_pressed('s'):
            pass

    print(f"\n🎉 Training für '{modul_name}' abgeschlossen!")
    print(f"Die Bilder liegen bereit in: {target_dir}")

if __name__ == "__main__":
    gabi_universal_trainer()