# debug_imports.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("Step 1: Importiere config...")
import config
print(f"  ✅ config geladen")

print("Step 2: Prüfe config.get...")
model = config.config.get("ollama.default_model")
print(f"  ✅ config.get funktioniert: {model}")

print("Step 3: Importiere auth...")
try:
    import auth
    print(f"  ✅ auth geladen")
except Exception as e:
    print(f"  ❌ auth Fehler: {e}")
    import traceback
    traceback.print_exc()

print("Step 4: Teste verify_api_key...")
try:
    from auth import verify_api_key
    result = verify_api_key("test")
    print(f"  ✅ verify_api_key funktioniert: {result}")
except Exception as e:
    print(f"  ❌ verify_api_key Fehler: {e}")

print("\nFertig!")