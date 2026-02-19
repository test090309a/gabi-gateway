# make-screenshot.py
# Um einen screenshot zu erstellen, ohne GUI-Steuerung

from integrations.lerne_blender_bedienen import execute
import time
import keyboard  # pip install keyboard

print("Drücke F8 um Blender-Screenshot zu machen...")
keyboard.wait('f8')
print("📸 Mache Screenshot...")
result = execute(action='screenshot')
print(f"✅ Screenshot: {result['filename']}")