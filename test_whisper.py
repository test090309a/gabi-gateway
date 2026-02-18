#!/usr/bin/env python3
"""Test-Skript fuer Whisper-Integration"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_whisper():
    print("[TEST] Teste Whisper-Integration...")
    try:
        from integrations.whisper_client import get_whisper_client

        whisper = get_whisper_client()
        print(f"   Client erstellt: {whisper.base_url}")

        available = whisper.is_available()
        print(f"   Verfuegbar: {available}")

        if available:
            models = whisper.get_models()
            print(f"   Modelle: {models}")
            print("[OK] Whisper-Integration funktioniert!")
            return True
        else:
            print("[WARN] Whisper-Server nicht verfuegbar (erwartet wenn nicht gestartet)")
            return True

    except Exception as e:
        print(f"[ERROR] Fehler: {e}")
        return False

if __name__ == "__main__":
    success = test_whisper()
    sys.exit(0 if success else 1)
