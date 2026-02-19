import time
import os
from PIL import ImageGrab
from gpu_screenshot import GPUScreenshot

def run_full_capture_test():
    print("🚀 Starte VOLLBILD-Erfassung...")
    vision = GPUScreenshot()
    
    # Ordner für Ergebnisse
    os.makedirs("assets", exist_ok=True)
    full_screenshot_path = os.path.join("assets", "real_fullscreen.png")

    # 1. Den echten Vollbild-Screenshot machen
    # Wir nutzen ImageGrab direkt für volle Auflösung ohne Skalierungsfehler
    print("📸 Erfasse 2560x1440 Pixel...")
    full_img = ImageGrab.grab(all_screens=False)
    full_img = full_img.convert("RGB")
    
    # Speichern des echten Full-Screens
    full_img.save(full_screenshot_path)
    w, h = full_img.size
    print(f"✅ Vollbild gespeichert: {w}x{h} Pixel")

    # 2. Benchmark auf der GPU
    print("⚡ Starte GPU-Verarbeitung des gesamten Bildes...")
    start_time = time.time()
    
    # Bild in den Grafikspeicher laden
    img_gpu, _ = vision.capture()
    
    # Wir suchen das soeben gespeicherte Vollbild in sich selbst 
    # (Härtetest für die GPU bei maximaler Pixelanzahl)
    found, pos = vision.find_template_gpu(img_gpu, full_screenshot_path, threshold=0.9)
    
    duration_ms = (time.time() - start_time) * 1000
    
    if found:
        print(f"✅ Erfolg! Vollbild-Match bei Position: {pos}")
    
    print(f"⏱️ Zeit für 3.6 Millionen Pixel: {duration_ms:.2f} ms")

if __name__ == "__main__":
    run_full_capture_test()