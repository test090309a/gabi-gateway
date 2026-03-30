# test_api_modules.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("TESTE API-MODULE EINZELN")
print("=" * 60)

# Zuerst config und auth laden
print("\n[1] Lade Basis-Module...")
from config import config
print(f"   ✅ config: {config.get('ollama.default_model')}")

from auth import verify_api_key
print(f"   ✅ auth: {verify_api_key('test')}")

# Dann jedes API-Modul einzeln testen
print("\n[2] Teste gateway.api.chat...")
try:
    import gateway.api.chat
    print("   ✅ gateway.api.chat")
except Exception as e:
    print(f"   ❌ {e}")
    import traceback
    traceback.print_exc()

print("\n[3] Teste gateway.api.gui...")
try:
    import gateway.api.gui
    print("   ✅ gateway.api.gui")
except Exception as e:
    print(f"   ❌ {e}")
    traceback.print_exc()

print("\n[4] Teste gateway.api.shell...")
try:
    import gateway.api.shell
    print("   ✅ gateway.api.shell")
except Exception as e:
    print(f"   ❌ {e}")
    traceback.print_exc()

print("\n[5] Teste gateway.api.telegram...")
try:
    import gateway.api.telegram
    print("   ✅ gateway.api.telegram")
except Exception as e:
    print(f"   ❌ {e}")
    traceback.print_exc()

print("\nFertig!")