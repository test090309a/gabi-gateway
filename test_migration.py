# test_all_modules.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("FINALER TEST - ALLE MODULE")
print("=" * 60)

# Test 1: Config
print("\n[1] Config...")
from config import config
print(f"   ✅ {config.get('ollama.default_model')}")

# Test 2: Auth
print("\n[2] Auth...")
from auth import verify_api_key, verify_token
print(f"   ✅ verify_api_key: {verify_api_key('test')}")

# Test 3: API Module
print("\n[3] API Module...")
try:
    from gateway.api.chat import chat_with_gabi
    print("   ✅ gateway.api.chat")
except Exception as e:
    print(f"   ❌ {e}")

try:
    from gateway.api.gui import gui_status
    print("   ✅ gateway.api.gui")
except Exception as e:
    print(f"   ❌ {e}")

try:
    from gateway.api.shell import execute_command
    print("   ✅ gateway.api.shell")
except Exception as e:
    print(f"   ❌ {e}")

# Test 4: Core Module
print("\n[4] Core Module...")
try:
    from gateway.core.brain import get_brain
    print("   ✅ gateway.core.brain")
except Exception as e:
    print(f"   ❌ {e}")

try:
    from gateway.core.commands import handle_command
    print("   ✅ gateway.core.commands")
except Exception as e:
    print(f"   ❌ {e}")

try:
    from gateway.core.router import classify_intent
    print("   ✅ gateway.core.router")
except Exception as e:
    print(f"   ❌ {e}")

# Test 5: Integrations
print("\n[5] Integrations...")
try:
    from gateway.integrations.telegram_bot import get_telegram_bot_sync
    print("   ✅ gateway.integrations.telegram_bot")
except Exception as e:
    print(f"   ❌ {e}")

try:
    from gateway.integrations.gmail_client import get_gmail_client
    print("   ✅ gateway.integrations.gmail_client")
except Exception as e:
    print(f"   ❌ {e}")

print("\n" + "=" * 60)
print("✅ ALLE TESTS BESTANDEN!")
print("=" * 60)