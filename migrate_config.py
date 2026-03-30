# test_migration_fixed.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("TESTE CONFIG-MIGRATION (FIXED)")
print("=" * 60)

# Test 1: Config
print("\n[1] Config import...")
try:
    from config import config
    print(f"   ✅ OK: {config.get('ollama.default_model')}")
except Exception as e:
    print(f"   ❌ {e}")

# Test 2: Auth (mit lazy import)
print("\n[2] Auth import...")
try:
    from gateway.auth import verify_api_key
    print("   ✅ Auth importiert")
except Exception as e:
    print(f"   ❌ {e}")

# Test 3: API Module
print("\n[3] API Module...")
try:
    from gateway.api.chat import chat_with_gabi
    print("   ✅ gateway.api.chat")
except Exception as e:
    print(f"   ❌ gateway.api.chat: {e}")

try:
    from gateway.api.gui import gui_status
    print("   ✅ gateway.api.gui")
except Exception as e:
    print(f"   ❌ gateway.api.gui: {e}")

print("\n" + "=" * 60)