# debug_imports_detailed.py
import sys
import os
import time
import signal

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

def test_import(module_name, timeout=5):
    """Teste import mit timeout"""
    print(f"\nTeste {module_name}...", end=" ", flush=True)
    
    import threading
    
    result = {"success": False, "error": None}
    
    def import_module():
        try:
            __import__(module_name)
            result["success"] = True
        except Exception as e:
            result["error"] = e
    
    thread = threading.Thread(target=import_module)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        print(f"❌ TIMEOUT (> {timeout}s)")
        return False
    elif result["success"]:
        print("✅")
        return True
    else:
        print(f"❌ {result['error']}")
        return False

print("=" * 60)
print("DEBUG IMPORTS MIT TIMEOUT")
print("=" * 60)

# Teste config und auth zuerst
print("\n[1] Basis-Module:")
test_import("config", timeout=2)
test_import("auth", timeout=2)

# Teste jedes API-Modul einzeln
print("\n[2] API-Module:")
modules = [
    "gateway.api.whisper",
    "gateway.api.comfy",
    "gateway.api.gmail",
    "gateway.api.gui",
    "gateway.api.memory",
    "gateway.api.models_api",
    "gateway.api.shell",
    "gateway.api.som",
    "gateway.api.system",
    "gateway.api.telegram",
    "gateway.api.vision",
    "gateway.api.web",
    "gateway.api.chat",  # chat zuletzt
]

for module in modules:
    test_import(module, timeout=5)

print("\n" + "=" * 60)
print("FERTIG")