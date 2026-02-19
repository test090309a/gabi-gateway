import os
import time
import pyautogui
from gpu_screenshot import GPUScreenshot

def auto_scan_calculator():
    print("🧠 GABI startet automatische Grid-Erkennung...")
    vision = GPUScreenshot()
    
    # Pfade
    anchor_path = "assets/calc_7.png"
    target_dir = "assets/calc/"
    os.makedirs(target_dir, exist_ok=True)

    if not os.path.exists(anchor_path):
        print(f"❌ Anker-Bild {anchor_path} fehlt!")
        return

    # 1. Finde die '7' als Referenzpunkt auf dem Screen
    img_gpu, _ = vision.capture()
    found, coords = vision.find_template_gpu(img_gpu, anchor_path)

    if not found:
        print("❌ Konnte Taste '7' nicht auf dem Bildschirm finden. Ist der Rechner offen?")
        return

    x7, y7 = coords
    print(f"📍 Ankerpunkt '7' gefunden bei: {coords}")

    # 2. Grid-Abstände (Standard Windows Rechner bei 100% Skalierung)
    # Diese Werte sind Schätzwerte für das Raster
    dx = 80  # Horizontaler Abstand zwischen Tastenmitten
    dy = 60  # Vertikaler Abstand zwischen Tastenmitten

    # Definition des Grids basierend auf der Position der '7'
    grid = {
        "8": (x7 + dx, y7),
        "9": (x7 + 2*dx, y7),
        "4": (x7, y7 + dy),
        "5": (x7 + dx, y7 + dy),
        "6": (x7 + 2*dx, y7 + dy),
        "1": (x7, y7 + 2*dy),
        "plus": (x7 + 3*dx, y7 + 2*dy),
        "gleich": (x7 + 3*dx, y7 + 3*dy)
    }

    # 3. Automatisch Screenshots der Tasten machen
    print("📸 Extrahiere Tasten-Templates...")
    for name, (cx, cy) in grid.items():
        # Kleinen Ausschnitt um die berechnete Koordinate speichern
        screenshot = pyautogui.screenshot(region=(cx-25, cy-25, 50, 50))
        path = f"{target_dir}btn_{name}.png"
        screenshot.save(path)
        print(f"✅ Gelernt: {name} an Position ({cx}, {cy})")

    print("\n🎉 Lernen abgeschlossen! Du kannst 'gabi_math_bot.py' jetzt starten.")

if __name__ == "__main__":
    auto_scan_calculator()