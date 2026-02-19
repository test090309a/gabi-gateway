import time
import os
import torch
from gpu_screenshot import GPUScreenshot
from gui_controller import get_gui_controller

def run_calculator_bot():
    print("🤖 GABI Bot startet...")
    
    # Instanzen holen
    vision = GPUScreenshot()
    gui = get_gui_controller()
    
    # 1. Programm öffnen
    print("🧮 Öffne Taschenrechner...")
    gui.win_search_and_open("Calculator")
    time.sleep(2)  # Warten bis Fenster geladen ist
    
    # 2. Visuelle Suche via GPU
    template_path = os.path.join("assets", "calc_7.png")
    if not os.path.exists(template_path):
        print(f"❌ Fehler: {template_path} nicht gefunden! Bitte erstelle einen Screenshot der Taste.")
        return

    print(f"🔍 Suche Button '{template_path}' auf dem Bildschirm...")
    
    # Screenshot direkt in GPU-Speicher laden
    img_gpu, _ = vision.capture()
    
    # GPU-beschleunigtes Matching
    found, pos_index = vision.find_template_gpu(img_gpu, template_path, threshold=0.8)
    
    if found:
        # Die Position von einem flachen Index in X/Y umrechnen
        # (Dies ist eine Vereinfachung, da find_template_gpu aktuell nur den Max-Index liefert)
        # Für einen echten Klick nutzen wir hier die Koordinaten-Logik
        print(f"✅ Button gefunden! Index: {pos_index}")
        
        # In deinem aktuellen System nutzen wir die find_icon Funktion für die Klick-Koordinaten:
        result = gui.find_icon_on_screen(template_path)
        
        if result["success"]:
            x, y = result["position"]["x"], result["position"]["y"]
            print(f"🖱️ Bewege Maus zu ({x}, {y}) und klicke...")
            gui.safe_click(x, y)
        else:
            print("❌ Koordinaten-Bestimmung fehlgeschlagen.")
    else:
        print("❌ Button auf dem Bildschirm nicht erkannt.")

if __name__ == "__main__":
    run_calculator_bot()