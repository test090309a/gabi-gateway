# test_webcam_gabi.py
import sys
import os
sys.path.insert(0, r'M:\projekte_2026\gabi-gateway')
os.chdir(r'M:\projekte_2026\gabi-gateway')

from gateway.integrations.gabi_vision import get_gabi_vision

vision = get_gabi_vision()
print("Vision Modul geladen")

result = vision.capture_webcam()
print(f"Ergebnis: {result}")

if result.get("success"):
    print(f"Bild gespeichert unter: {result.get('path')}")
    print(f"Base64 Länge: {len(result.get('base64', ''))}")
    
    # Prüfe ob die Datei existiert und Größe hat
    import os
    path = result.get('path')
    if path and os.path.exists(path):
        size = os.path.getsize(path)
        print(f"Dateigröße: {size} bytes")
        
        # Lade das Bild mit PIL und prüfe ob es schwarz ist
        from PIL import Image
        import numpy as np
        img = Image.open(path)
        img_array = np.array(img)
        print(f"Bildform: {img_array.shape}")
        print(f"Min-Wert: {img_array.min()}, Max-Wert: {img_array.max()}")
        if img_array.max() == 0:
            print("❌ BILD IST KOMPLETT SCHWARZ!")
        else:
            print("✅ BILD HAT INHALT!")
    else:
        print("❌ Datei nicht gefunden!")
else:
    print(f"Fehler: {result.get('error')}")