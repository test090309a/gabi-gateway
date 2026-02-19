import time
import os
import pyautogui
from gpu_screenshot import GPUScreenshot

def teach_calculator():
    print("🎓 GABI lernt jetzt den Taschenrechner...")
    os.makedirs("assets/calc", exist_ok=True)
    
    print("1. Öffne den Taschenrechner.")
    print("2. Halte die Maus nacheinander auf die Tasten, die ich gleich nenne.")
    time.sleep(3)

    tasten = ["7", "8", "9", "plus", "gleich"]
    
    for taste in tasten:
        print(f"👉 Bewege die Maus auf die Taste: [{taste}] und halte sie dort...")
        time.sleep(2)
        x, y = pyautogui.position()
        
        # Kleiner Ausschnitt (50x50 Pixel) um die Maus herum
        screenshot = pyautogui.screenshot(region=(x-25, y-25, 50, 50))
        path = f"assets/calc/btn_{taste}.png"
        screenshot.save(path)
        print(f"✅ Gelernt: {path}")

if __name__ == "__main__":
    teach_calculator()