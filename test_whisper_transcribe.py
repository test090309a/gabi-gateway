# test_whisper_transcribe.py
import sys
import os

root_dir = r'M:\projekte_2026\gabi-gateway'
sys.path.insert(0, root_dir)
os.chdir(root_dir)

print("=" * 60)
print("TESTE WHISPER DIREKT")
print("=" * 60)

from gateway.integrations.whisper_client import get_whisper_client

client = get_whisper_client()
print(f"✅ Client: {client.voice_settings}")

# Prüfe, ob der Server antwortet
print("\n[1] Server Status...")
available = client.is_available()
print(f"   Server verfügbar: {available}")

if available:
    print("\n[2] Teste Transkription mit Test-Datei...")
    # Hier könntest du eine Test-Audio-Datei transkribieren
    # test_file = "test_audio.wav"
    # result = client.transcribe_file(test_file, language="de")
    # print(f"   Ergebnis: {result}")
    print("   (Keine Test-Datei vorhanden)")
else:
    print("   ❌ Server nicht erreichbar!")

print("\n" + "=" * 60)