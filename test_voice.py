# test_voice.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("TESTE VOICE SETTINGS")
print("=" * 60)

# 1. Config laden
print("\n[1] Config laden...")
from config import config
print(f"   ✅ Config geladen")

# 2. Voice Settings aus config
print("\n[2] Voice Settings aus config.get('voice_settings'):")
voice_settings = config.get("voice_settings")
print(f"   {voice_settings}")

# 3. Einzelne Werte
print("\n[3] Einzelne Werte:")
print(f"   vad_threshold: {config.get('voice_settings.vad_threshold')}")
print(f"   min_speech_duration: {config.get('voice_settings.min_speech_duration')}")
print(f"   silence_timeout: {config.get('voice_settings.silence_timeout')}")
print(f"   max_record_time: {config.get('voice_settings.max_record_time')}")

# 4. Whisper Client initialisieren
print("\n[4] Whisper Client initialisieren...")
from gateway.integrations.whisper_client import get_whisper_client

try:
    client = get_whisper_client()
    print(f"   ✅ Client erstellt")
    print(f"   Client voice_settings: {client.voice_settings}")
    print(f"   silence_timeout: {client.voice_settings.get('silence_timeout')}")
except Exception as e:
    print(f"   ❌ Fehler: {e}")
    import traceback
    traceback.print_exc()

# 5. Whisper Server Status
print("\n[5] Whisper Server Status...")
try:
    status = client.is_available()
    print(f"   Server verfügbar: {status}")
    if status:
        models = client.get_models()
        print(f"   Modelle: {models}")
except Exception as e:
    print(f"   ❌ Fehler: {e}")

print("\n" + "=" * 60)
print("FERTIG")