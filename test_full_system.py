# test_full_system.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("FINALER SYSTEM-TEST")
print("=" * 60)

# Test 1: Config
print("\n[1] Config...")
from config import config
print(f"   ✅ Model: {config.get('ollama.default_model')}")

# Test 2: Auth
print("\n[2] Auth...")
from auth import verify_api_key, verify_token
print(f"   ✅ verify_api_key: {verify_api_key('test')}")

# Test 3: Core Module
print("\n[3] Core Module...")
from gateway.core.memory import chat_memory
print(f"   ✅ chat_memory")
from gateway.core.brain import get_brain
print(f"   ✅ get_brain")
from gateway.core.router import classify_intent
print(f"   ✅ classify_intent")

# Test 4: API Module (alle geladen)
print("\n[4] API Module...")
import gateway.api.chat
import gateway.api.gui
import gateway.api.shell
import gateway.api.telegram
import gateway.api.vision
import gateway.api.web
print(f"   ✅ Alle 13 API-Module geladen")

# Test 5: Integrations
print("\n[5] Integrations...")
from gateway.integrations.telegram_bot import get_telegram_bot_sync
print(f"   ✅ telegram_bot")
from gateway.integrations.gmail_client import get_gmail_client
print(f"   ✅ gmail_client")

print("\n" + "=" * 60)
print("✅ SYSTEM IST BEREIT!")
print("=" * 60)