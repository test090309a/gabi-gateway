import pyautogui
import os
from PIL import Image

def create_calc_template():
    print("1. Bitte öffne jetzt den Taschenrechner und platziere ihn sichtbar.")
    print("2. Der Screenshot wird in 5 Sekunden erstellt...")
    import time
    time.sleep(5)
    
    # Ganzen Schirm aufnehmen
    os.makedirs("assets", exist_ok=True)
    shot = pyautogui.screenshot()
    
    # Hinweis: Da ich deine genaue Position des Rechners nicht kenne, 
    # speichere ich erst das ganze Bild. 
    # DU musst es einmalig manuell zuschneiden oder mir sagen, 
    # wo der Rechner etwa ist.
    shot.save("assets/full_for_crop.png")
    print("✅ 'assets/full_for_crop.png' gespeichert.")
    print("Bitte öffne dieses Bild und schneide die Taste '7' aus.")
    print("Speichere den Ausschnitt als 'assets/calc_7.png'.")

if __name__ == "__main__":
    create_calc_template()